"""Build the public Lab map: one self-contained HTML file, government open data only.

    python -m scripts.build_lab_map

Reads the verified snapshots under data/ (run `python -m scraper.run` first to refresh them)
and writes lab-02/regina-data-map.html plus lab-02/product-facts.json (the live numbers,
for writing the product page).

What goes in (all from governments, nothing scraped):
  City of Regina open data   building permits, zoning districts, streets, proposed development
                             notices, rezonings (found by comparing the City's own zoning snapshots)
  Statistics Canada          population estimates (17-10-0155), components of change (17-10-0149),
                             2021 Census income and shelter cost, estimated per community association
  CMHC                       Rental Market Survey: average rent and vacancy for Regina

What stays out on purpose: company names, applicant and owner names, any company or contact data,
anything from a private source. Permits are shown by address and type only.
"""
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scraper import outputs as o  # noqa: E402
from scraper.sources.roads import load_or_fetch as load_roads  # noqa: E402

OUT = ROOT / os.environ.get("LAB_OUT_DIR", "lab-02")
OUT.mkdir(parents=True, exist_ok=True)
TEMPLATES = ROOT / "templates"
CONFIG = json.loads((ROOT / "config" / "site.json").read_text(encoding="utf-8"))
CA_SIMPLIFY_DEG = 0.0004


def _embed(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")


def _titlecase(s: str) -> str:
    return " ".join(w.capitalize() if w.lower() not in {"of", "and"} else w.lower() for w in (s or "").replace("/", " / ").split()).replace(" / ", "/")


def _latest_snapshot(folder: str) -> str:
    snaps = sorted((ROOT / "data" / folder / "snapshots").glob("*"))
    return snaps[-1].stem if snaps else ""


def permits(window_rows: list[dict]) -> list[dict]:
    """Compact permit records. Applicant and owner names are never included."""
    out = []
    for r in window_rows:
        ok = o._plottable(r)
        out.append({
            "id": r["Permit Number"], "lon": round(r["lon"], 5) if ok else None, "lat": round(r["lat"], 5) if ok else None,
            "d": r["Date Issued"], "g": r["group"], "t": r["Permit Application Type"], "u": r.get("Building Use"), "v": round(r["cost"]),
            "a": r["address"], "n": r["neighbourhood"], "ca": (r.get("Community Association") or "").title() if r.get("Community Association") else "",
            "z": r.get("Zoning Code"), "units": int(r.get("Number of Units") or 0),
        })
    out.sort(key=lambda p: p["d"])
    return out


def community_layer() -> dict:
    """2021 Census figures per community association (estimated by the City-data prep script from Statistics Canada dissemination areas)."""
    fc = json.loads((ROOT / "data" / "community_prosperity" / "2021_by_community_association.geojson").read_text(encoding="utf-8"))
    feats = []
    for f in fc["features"]:
        p = f["properties"]
        g = shape(f["geometry"]).simplify(CA_SIMPLIFY_DEG, preserve_topology=True)
        gm = mapping(g)
        gm["coordinates"] = o._round_coords(gm["coordinates"])
        feats.append({"type": "Feature", "geometry": gm, "properties": {
            "name": _titlecase(p["Community Association"]), "key": p["Community Association"].title(), "pop": p.get("Estimated Population (2021)"),
            "income": p.get("Median Household Income"), "shelter": p.get("Pct Spending 30 Plus On Shelter"),
        }})
    return {"type": "FeatureCollection", "features": feats}


def series(folder: str) -> list[dict]:
    fc = json.loads((ROOT / "data" / folder / "latest.geojson").read_text(encoding="utf-8"))
    return sorted((f["properties"] for f in fc["features"]), key=lambda p: p["Year"])


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rows_all, last, _ = o.load_permit_history()  # every permit since 2020; the map's date controls pick the slice
    mp = permits(rows_all)
    zoning = o.zoning_overlay()
    ca = community_layer()
    events = [{
        "lat": e["lat"], "lon": e["lon"], "from": e["zoning_from"], "to": e["zoning_to"], "to_desc": e["zoning_to_description"], "address": e["nearest_address"],
        "area": _titlecase(e["community_association"] or ""), "bylaw": e["bylaw_number"], "detected": e["first_detected"], "baseline": e["baseline_snapshot"],
        "apps": [{"file": a["file_number"], "type": a["application_type"], "desc": a["description"]} for a in e["linked_applications"]],
    } for e in o.rezoning_events()]
    apps = [{"file": a["File Number"], "address": a["Address"], "type": a["Application Type"], "desc": a["Description"], "status": a["Status"],
             "open": bool(a.get("Comments Open")), "notice": a.get("Public Notice URL"), "lon": a["lon"], "lat": a["lat"]} for a in o.open_applications()]
    drawn = [p for p in mp if p["lon"] is not None]
    xs, ys = [p["lon"] for p in drawn], [p["lat"] for p in drawn]
    pad_x, pad_y = (max(xs) - min(xs)) * 0.05, (max(ys) - min(ys)) * 0.05
    bounds = [round(min(xs) - pad_x, 4), round(min(ys) - pad_y, 4), round(max(xs) + pad_x, 4), round(max(ys) + pad_y, 4)]
    roads = o.road_overlay(load_roads(ROOT / "data" / "roads" / "latest.geojson"), (bounds[0] - 0.05, bounds[1] - 0.03, bounds[2] + 0.05, bounds[3] + 0.03))
    ramp_words = re.compile(r"(onr|offr|crsrd|cnr|entr|ex|ramp|connector)", re.I)  # highway ramps and cross-road tags clutter the map
    roads["labels"] = [lb for lb in roads["labels"] if not ramp_words.search(lb["n"])]
    pop, rent, mig = series("population"), series("rental_market"), series("migration")
    first = min(r["date"] for r in rows_all)
    meta = {
        "latest": last.isoformat(), "built": date.today().isoformat(), "bounds": bounds, "groups": [{"key": k, "label": v} for k, v in o.GROUPS],
        "attribution": CONFIG["attribution"],
        "asof": {
            "permits": last.isoformat(), "permits_start": first.isoformat(), "zoning": _latest_snapshot("zoning"), "applications": _latest_snapshot("proposed_development"),
            "population": pop[-1]["Release Date"], "population_year": pop[-1]["Year"], "rent_year": rent[-1]["Year"], "migration_year": mig[-1]["Year"],
        },
        "schema": 1, "unplotted": sum(1 for p in mp if p["lon"] is None), "total_permits": len(mp),
    }
    data = {"meta": meta, "permits": mp, "zoning": zoning, "communities": ca, "roads": roads, "rezonings": events, "applications": apps,
            "series": {"population": [{"y": p["Year"], "v": p["Population"]} for p in pop],
                       "rent": [{"y": r["Year"], "rent": r["Average Rent"], "vac": r["Vacancy Rate"]} for r in rent],
                       "migration": [{"y": m["Year"], "births": m["Births"], "deaths": m["Deaths"], "imm": m["Immigrants"], "inter": m["Net Interprovincial Migration"]} for m in mig]}}
    html = (TEMPLATES / "lab_map.html").read_text(encoding="utf-8")
    html = html.replace("/*__LEAFLET_CSS__*/", (TEMPLATES / "vendor" / "leaflet.css").read_text(encoding="utf-8"))
    html = html.replace("/*__LEAFLET_JS__*/", (TEMPLATES / "vendor" / "leaflet.js").read_text(encoding="utf-8"))
    html = html.replace("/*__DATA__*/", _embed(data))
    # Where a saved copy of the map looks for newer data. Blank until the data host exists (set LAB_DATA_URL, or "data_url" in config/site.json).
    data_url = os.environ.get("LAB_DATA_URL", CONFIG.get("data_url", ""))
    html = html.replace("/*__DATA_URL__*/", data_url)
    (OUT / "latest-v1.json").write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    path = OUT / "regina-data-map.html"
    path.write_text(html, encoding="utf-8")
    total = sum(p["v"] for p in mp)
    from datetime import timedelta
    year_start = (last - timedelta(days=364)).isoformat()
    year = [p for p in mp if p["d"] >= year_start]
    facts = {
        "built": meta["built"], "permits_through": meta["latest"], "history_starts": first.isoformat(),
        "permits_since_history_start": len(mp), "declared_value_since_history_start": total,
        "permits_last_12_months": len(year), "declared_value_last_12_months": sum(p["v"] for p in year),
        "neighbourhoods": len({p["n"] for p in year}), "rezonings_detected": len(events), "open_applications": len(apps),
        "applications_comment_open": sum(1 for a in apps if a["open"]), "population_latest": pop[-1], "rent_latest": rent[-1], "as_of": meta["asof"],
        "size_mb": round(path.stat().st_size / 1e6, 2),
    }
    (OUT / "product-facts.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")
    print(f"{path} ({path.stat().st_size / 1e6:.2f} MB)")
    print(json.dumps(facts, indent=1))


if __name__ == "__main__":
    main()
