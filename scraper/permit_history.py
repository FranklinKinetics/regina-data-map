"""Every published building permit since 2020, matched to the City's address points,
for the Lab map's date slider.

Only exact City address-point matches are drawn on the map (OpenStreetMap fallbacks
were found to be unreliable), so this step skips OpenStreetMap entirely: a permit
whose address isn't in the City's address layer is kept for the totals and charts but
has no map location. Older addresses (since demolished or renumbered) miss more often
than recent ones, so the match rate is reported per year and only a collapse fails the run.
"""
import json
import math
from pathlib import Path

from scraper.address_points import fetch_address_index, normalize_address
from scraper.enrich import COMMUNITY_ASSOCIATIONS_URL, AreaLookup, _fetch_features
from scraper.sources.building_permits import fetch_permit_history
from scraper.verify import VerificationError, check_no_duplicate_keys, check_not_suspicious_drop, check_reconciles_to_source

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MIN_MATCH_RATE = 0.80  # across all years; recent years are ~98%, early years lower


def _clean(v):
    return None if isinstance(v, float) and math.isnan(v) else v


def run_permit_history(zoning_fc: dict) -> dict:
    print("Fetching permit history (every year the City publishes)...")
    rows, meta = fetch_permit_history()
    check_no_duplicate_keys([r["Permit Number"] for r in rows], "Permit history")

    out_path = DATA_DIR / "permit_history" / "latest.geojson"
    previous = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else None
    check_not_suspicious_drop(len(rows), len(previous["features"]) if previous else None, "Permit history")

    index = fetch_address_index()
    zoning, areas = AreaLookup(zoning_fc["features"]), AreaLookup(_fetch_features(COMMUNITY_ASSOCIATIONS_URL))
    features, by_year = [], {}
    for r in rows:
        hit = index.get(normalize_address(r["Location"])) if r.get("Location") else None
        props = {k: _clean(v) for k, v in r.items() if k != "Report Year"}
        props["Geocode Method"] = "city_address_point" if hit else None
        z = zoning.lookup(*hit) if hit else None
        a = areas.lookup(*hit) if hit else None
        props["Zoning Code"] = (z or {}).get("GIS.Zoning.ZONING")
        props["Community Association"] = (a or {}).get("NAME")
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(hit[0], 6), round(hit[1], 6)]} if hit else None, "properties": props})
        y = by_year.setdefault(r["Date Issued"][:4], [0, 0]); y[0] += 1; y[1] += 1 if hit else 0

    rate = sum(v[1] for v in by_year.values()) / max(1, len(rows))
    print("  matched to a City address point, by year: " + ", ".join(f"{y} {100 * v[1] / v[0]:.0f}%" for y, v in sorted(by_year.items())))
    if rate < MIN_MATCH_RATE:
        raise VerificationError(f"Permit history: only {rate:.1%} of permits matched a City address point (needs {MIN_MATCH_RATE:.0%})")
    check_reconciles_to_source(
        len(features), sum(f["properties"]["Estimated Cost of Construction"] or 0 for f in features), meta, "Permit history")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    print(f"Permit history: {len(features)} permits, {meta['first_year']} to {max(r['Date Issued'] for r in rows)}")
    return {"permits": len(features), "match_rate": round(rate, 4), "by_year_match": {y: round(v[1] / v[0], 4) for y, v in sorted(by_year.items())}, "source": meta}
