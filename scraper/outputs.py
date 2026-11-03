"""Turn the latest pipeline data into what readers see: neighbourhood
summaries, the compact map dataset, and the weekly Build Watch digest data.

Everything here reads the verified snapshots under data/; nothing is fetched.
All dollar figures are the *declared* estimated cost of construction on the
permit, not what was eventually spent.
"""
import json
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

from shapely.geometry import mapping, shape

from scraper.trades import TRADES, trades_for

DATA = Path(__file__).resolve().parent.parent / "data"
WINDOW_DAYS = 365  # inclusive of the latest permit date
MAP_SIMPLIFY_DEG = 0.0003  # ~25 m; zoning overlay is context, not a survey

GROUPS = [
    ("new-homes", "New homes"),
    ("new-multi", "New apartments and townhouses"),
    ("new-commercial", "New commercial, industrial, institutional"),
    ("commercial-reno", "Commercial and institutional renovations"),
    ("suites", "Suites and basements"),
    ("home-work", "Other home work"),
    ("other", "Demolition and other"),
]
GROUP_LABEL = dict(GROUPS)


def permit_group(p: dict) -> str:
    t = p["Permit Application Type"]
    use = p.get("Building Use")
    if t in ("Single/Semi-Detached Dwelling 1-2 units", "Backyard/Laneway Suite"):
        return "new-homes"
    if t == "Multi-Unit Dwelling 3+ Units":
        return "new-multi"
    if t == "New Commercial":
        return "new-commercial"
    if t in ("Renovation/Alteration", "Addition") and use != "Residential":
        return "commercial-reno"
    if t in ("Secondary Suite", "Basement Development"):
        return "suites"
    if t == "Demolition" or t.startswith("Tent"):
        return "other"
    if use == "Residential":
        return "home-work"
    return "other"


# Plain-language zoning, grouped for the map legend. The City's layer mixes
# two code schemes (the 2019 bylaw "R1" style and the newer RN/RL/RU/RH set),
# so codes are mapped to a shared category.
ZONE_CATEGORY = {
    **{c: "Residential" for c in ("R1", "RN", "RL", "RU", "RH", "RMH")},
    **{c: "Mixed-use and commercial" for c in ("MH", "ML", "MLM", "OA")},
    **{c: "Industrial" for c in ("IL", "IH", "IP", "DCD-WH")},
    **{c: "Public and institutional" for c in ("PS", "I")},
    "UH": "Urban holding (future development)",
}
ZONE_NAME = {
    "R1": "Residential Detached", "RN": "Residential Neighbourhood", "RL": "Residential Low-Rise",
    "RU": "Residential Urban", "RH": "Residential High-Rise", "RMH": "Residential Mobile Home",
    "MH": "Mixed High-Rise", "ML": "Mixed Low-Rise", "MLM": "Mixed Large Market", "OA": "Office Area",
    "IL": "Industrial Light", "IH": "Industrial Heavy", "IP": "Prestige Industrial",
    "PS": "Public Service", "I": "Institutional", "UH": "Urban Holding",
    "C": "Contract zone (site-specific rules)", "RW": "Railway",
}


def zone_category(code: str | None) -> str:
    if not code:
        return "Other"
    if code.startswith("DCD"):
        return "Direct control district"
    return ZONE_CATEGORY.get(code, "Other")


def pretty_address(raw: str | None) -> str:
    if not raw:
        return ""
    street = raw.split(",")[0].strip()
    return " ".join(w.capitalize() for w in street.split())  # "12TH AVENUE" -> "12th Avenue"


def _plottable(r: dict) -> bool:
    """Only points matched to the City's own address layer are shown on the
    map: OpenStreetMap fallback points were found to be unreliable (one landed
    ~250 km away) and neighbourhood-centroid points are deliberately vague."""
    return r["lon"] is not None and r.get("Geocode Method") == "city_address_point"


def load_permits(path: Path | None = None, with_trades: bool = True) -> tuple[list[dict], date, dict]:
    fc = json.loads((path or DATA / "permits" / "latest.geojson").read_text(encoding="utf-8"))
    rows = []
    for f in fc["features"]:
        p = dict(f["properties"])
        p["Permit Application Type"] = p.get("Permit Application Type") or "Unknown"
        coords = f["geometry"]["coordinates"] if f.get("geometry") else None
        p["lon"], p["lat"] = (coords if coords else (None, None))
        p["cost"] = p.get("Estimated Cost of Construction") or 0.0
        p["date"] = datetime.strptime(p["Date Issued"], "%Y-%m-%d").date()
        p["group"] = permit_group(p)
        p["address"] = pretty_address(p.get("Location"))
        p["neighbourhood"] = p.get("Subdivision Code") or "Unassigned"
        if with_trades:
            p["trades"] = trades_for(p)
        rows.append(p)
    last = max(r["date"] for r in rows)
    meta = {"source_rows": len(rows), "latest_permit_date": last.isoformat()}
    return rows, last, meta


def load_permit_history() -> tuple[list[dict], date, dict]:
    """Every permit since 2020 (see scraper/permit_history.py), shaped like load_permits()."""
    return load_permits(DATA / "permit_history" / "latest.geojson", with_trades=False)


def window(rows: list[dict], last: date, days: int = WINDOW_DAYS) -> list[dict]:
    start = last - timedelta(days=days - 1)
    return [r for r in rows if start <= r["date"] <= last]


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def neighbourhood_summaries(rows: list[dict]) -> list[dict]:
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["neighbourhood"], []).append(r)
    out = []
    for name, rs in by.items():
        located = [r for r in rs if _plottable(r)]
        top = max(rs, key=lambda r: r["cost"])
        total = sum(r["cost"] for r in rs)
        new_units = sum(
            r.get("Number of Units") or 0
            for r in rs
            if r["group"] in ("new-homes", "new-multi") and r["Permit Application Type"] != "Backyard/Laneway Suite"
        )
        out.append(
            {
                "name": name,
                "permits": len(rs),
                "value": round(total),
                "median": round(_median([r["cost"] for r in rs])),
                "new_units": int(new_units),
                "top_project": {
                    "address": top["address"],
                    "type": top["Permit Application Type"],
                    "value": round(top["cost"]),
                },
                "top_share": round(top["cost"] / total, 3) if total else 0,
                "lon": round(sum(r["lon"] for r in located) / len(located), 5) if located else None,
                "lat": round(sum(r["lat"] for r in located) / len(located), 5) if located else None,
            }
        )
    return sorted(out, key=lambda n: -n["value"])


def map_permits(rows: list[dict]) -> list[dict]:
    """Compact records for the map page. Permits without a City address-point
    location are kept (lon/lat null) so neighbourhood totals still reconcile;
    the page counts them but does not draw them."""
    out = []
    for r in rows:
        ok = _plottable(r)
        out.append(
            {
                "id": r["Permit Number"],
                "lon": round(r["lon"], 5) if ok else None,
                "lat": round(r["lat"], 5) if ok else None,
                "d": r["Date Issued"],
                "g": r["group"],
                "t": r["Permit Application Type"],
                "u": r.get("Building Use"),
                "v": round(r["cost"]),
                "a": r["address"],
                "n": r["neighbourhood"],
                "z": r.get("Zoning Code"),
                "b": r.get("Applicant"),
                "bt": r.get("Applicant Type"),
                "units": int(r.get("Number of Units") or 0),
            }
        )
    return out


def zoning_overlay() -> dict:
    fc = json.loads((DATA / "zoning" / "latest.geojson").read_text(encoding="utf-8"))
    feats = []
    for f in fc["features"]:
        if not f.get("geometry"):
            continue
        props = f["properties"]
        code = props.get("GIS.Zoning.ZONING") or ""
        geom = shape(f["geometry"]).simplify(MAP_SIMPLIFY_DEG, preserve_topology=True)
        if geom.is_empty:
            continue
        gm = mapping(geom)
        gm["coordinates"] = _round_coords(gm["coordinates"])
        feats.append(
            {
                "type": "Feature",
                "geometry": gm,
                "properties": {
                    "c": code,
                    "cat": zone_category(code),
                    "name": props.get("GIS.ZONING_CODE_2019.DESCRIPTION") or ZONE_NAME.get(code) or (props.get("GIS.Zoning.ZONING_DESC") or "").strip(),
                    "plain": props.get("GIS.ZONING_CODE_2019.DEVELOPMENT_TYPE"),
                },
            }
        )
    return {"type": "FeatureCollection", "features": feats}


ROAD_TIER = {
    "HWY": "major", "EXPRESSWAY": "major", "ARTERIAL": "major", "RAMP": "major",
    "COLLECTOR": "collector",
    "LOCAL": "local", "PRIVATE": "local", "SERVICE ROAD": "local", "GRAVEL": "local", "UNPAVED": "local",
}  # rural grid, township, range and road-allowance lines are left out
ROAD_SIMPLIFY_DEG = 0.00003  # ~3 m
LABELLED_TIERS = ("major", "collector")


def _street_name(raw: str) -> str:
    return " ".join(w.capitalize() for w in raw.split())


def road_overlay(fc: dict, clip: tuple[float, float, float, float]) -> dict:
    """Street lines in three tiers plus one label point per named major or
    collector street (midpoint of its longest segment)."""
    from shapely.geometry import box, shape as _shape

    clip_box = box(*clip)  # highways run for kilometres into the countryside; keep the city and its edge

    tiers: dict[str, list] = {"major": [], "collector": [], "local": []}
    longest: dict[tuple[str, str], tuple[float, tuple[float, float]]] = {}
    for f in fc["features"]:
        if not f.get("geometry"):
            continue
        props = f["properties"]
        tier = ROAD_TIER.get(props.get("ROAD_FUNC") or "")
        if not tier:
            continue
        geom = _shape(f["geometry"]).intersection(clip_box)
        if geom.is_empty:
            continue
        geom = geom.simplify(ROAD_SIMPLIFY_DEG)
        parts = list(geom.geoms) if geom.geom_type in ("MultiLineString", "GeometryCollection") else [geom]
        parts = [pt for pt in parts if pt.geom_type == "LineString"]
        for part in parts:
            if part.is_empty or len(part.coords) < 2:
                continue
            tiers[tier].append([[round(x, 5), round(y, 5)] for x, y in part.coords])
            name = props.get("FULL_NAME")
            if tier in LABELLED_TIERS and name and name.strip():
                key = (tier, name.strip())
                if key not in longest or part.length > longest[key][0]:
                    mid = part.interpolate(0.5, normalized=True)
                    longest[key] = (part.length, (round(mid.x, 5), round(mid.y, 5)))
    labels = [{"n": _street_name(name), "t": tier, "x": pt[0], "y": pt[1]} for (tier, name), (_, pt) in longest.items()]
    return {"tiers": tiers, "labels": labels}


def _round_coords(c):
    if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
        return [round(c[0], 5), round(c[1], 5)]
    return [_round_coords(x) for x in c]


def rezoning_events() -> list[dict]:
    path = DATA / "zoning_changes" / "events.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def open_applications() -> list[dict]:
    fc = json.loads((DATA / "proposed_development" / "latest.geojson").read_text(encoding="utf-8"))
    out = []
    for f in fc["features"]:
        p = f["properties"]
        # the pipeline stores the matched parcel polygon (or the address point)
        pt = shape(f["geometry"]).representative_point() if f.get("geometry") else None
        out.append({**p, "lon": round(pt.x, 6) if pt else None, "lat": round(pt.y, 6) if pt else None})
    return out


def citywide(rows: list[dict]) -> dict:
    costs = [r["cost"] for r in rows]
    by_group = {}
    for key, label in GROUPS:
        rs = [r for r in rows if r["group"] == key]
        by_group[key] = {"label": label, "permits": len(rs), "value": round(sum(r["cost"] for r in rs))}
    return {
        "permits": len(rows),
        "value": round(sum(costs)),
        "median": round(_median(costs)),
        "by_group": by_group,
    }


# ---------------------------------------------------------------- digest

def _period(rows: list[dict], start: date, end: date) -> list[dict]:
    return [r for r in rows if start <= r["date"] <= end]


def digest_data(rows: list[dict], last: date, days: int = 7) -> dict:
    """The week's numbers, compared with the week before. `rows` is every
    permit in the pipeline window (400 days), so 4-week context is available."""
    start = last - timedelta(days=days - 1)
    prior_start, prior_end = start - timedelta(days=days), start - timedelta(days=1)
    this_week = _period(rows, start, last)
    prior = _period(rows, prior_start, prior_end)
    four_week = _period(rows, last - timedelta(days=days * 4 - 1), last)

    def agg(rs):
        return {"permits": len(rs), "value": round(sum(r["cost"] for r in rs)), "median": round(_median([r["cost"] for r in rs]))}

    def lead(r, trade=None):
        return {
            "permit": r["Permit Number"],
            "date": r["Date Issued"],
            "address": r["address"],
            "neighbourhood": r["neighbourhood"],
            "type": r["Permit Application Type"],
            "use": r.get("Building Use"),
            "work_class": r.get("Work Class"),
            "value": round(r["cost"]),
            "units": int(r.get("Number of Units") or 0),
            "zone": r.get("Zoning Code"),
            "zone_name": ZONE_NAME.get(r.get("Zoning Code") or ""),
            "applicant": r.get("Applicant"),
            "applicant_type": r.get("Applicant Type"),
            "group": r["group"],
            "reason": r["trades"].get(trade) if trade else None,
        }

    by_trade = {}
    for key, spec in TRADES.items():
        leads = sorted((r for r in this_week if key in r["trades"]), key=lambda r: -r["cost"])
        prior_leads = [r for r in prior if key in r["trades"]]
        four = [r for r in four_week if key in r["trades"]]
        hoods: dict[str, list[float]] = {}
        for r in leads:
            hoods.setdefault(r["neighbourhood"], []).append(r["cost"])
        by_trade[key] = {
            "label": spec["label"],
            "leads": [lead(r, key) for r in leads],
            "count": len(leads),
            "value": round(sum(r["cost"] for r in leads)),
            "prior_count": len(prior_leads),
            "four_week_avg": round(len(four) / 4, 1),
            "hoods": sorted(({"name": k, "count": len(v), "value": round(sum(v))} for k, v in hoods.items()), key=lambda h: (-h["count"], -h["value"])),
        }

    group_rows = []
    for key, label in GROUPS:
        a = [r for r in this_week if r["group"] == key]
        b = [r for r in prior if r["group"] == key]
        group_rows.append({"key": key, "label": label, "permits": len(a), "value": round(sum(r["cost"] for r in a)), "prior_permits": len(b)})

    return {
        "week_start": start.isoformat(),
        "week_end": last.isoformat(),
        "prior_start": prior_start.isoformat(),
        "prior_end": prior_end.isoformat(),
        "this_week": agg(this_week),
        "prior_week": agg(prior),
        "four_week_avg_permits": round(len(four_week) / 4, 1),
        "four_week_avg_value": round(sum(r["cost"] for r in four_week) / 4),
        "groups": group_rows,
        "top_projects": [lead(r) for r in sorted(this_week, key=lambda r: -r["cost"])[:6]],
        "by_trade": by_trade,
    }
