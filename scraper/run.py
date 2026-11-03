"""Entry point for one full pipeline run: fetch -> normalize -> geocode ->
verify -> diff -> snapshot. Intended to be run on a schedule (weekly, to
match the Building Permit Report's Thursday update cadence).

Exits non-zero if verification fails, so a scheduled run shows as a failure
and nothing gets committed as if it succeeded.
"""
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path

from scraper.enrich import enrich_points
from scraper.geocode import geocode_all
from scraper.parcel_match import find_containing_parcel
from scraper.privacy import business_name
from scraper.address_points import fetch_address_index
from scraper.snapshot import diff_features, load_latest, write_snapshot
from scraper.zoning_changes import detect_changes, load_applications, merge_events
from scraper.sources.building_permits import fetch_permits
from scraper.sources.migration import fetch_migration
from scraper.sources.population import fetch_population
from scraper.sources.proposed_development import fetch_proposed_development, primary_geocode_target
from scraper.sources.rental_market import fetch_rental_market
from scraper.sources.zoning import fetch_zoning
from scraper.verify import (
    VerificationError,
    check_geocode_success_rate,
    check_no_duplicate_keys,
    check_reconciles_to_source,
    check_no_wild_swing,
    check_not_suspicious_drop,
    check_proposed_development_entries,
    check_time_series_entries,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Change-stamp fields in the zoning layer that tick without any real rezoning
# (confirmed: ~4 parcels/day get a new UPDATE_DATE; 327 of 328 "changed"
# records between July and October were this noise).
ZONING_BOOKKEEPING_FIELDS = frozenset({"GIS.Zoning.UPDATE_DATE", "GIS.Zoning.UPDATE_USER"})


def _clean(value):
    """NaN isn't valid JSON; normalize to None."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _permits_to_geojson(rows: list[dict], geocoded: dict, extras: dict) -> dict:
    features = []
    for row in rows:
        point = geocoded.get(row["Location"])
        geometry = {"type": "Point", "coordinates": [point["lon"], point["lat"]]} if point else None
        properties = {k: _clean(v) for k, v in row.items()}
        # Individuals' names are dropped at ingest; only business names are kept.
        properties["Applicant"] = business_name(properties.pop("Name", None))
        properties["Applicant Type"] = properties.pop("Contact Type Description", None)
        properties["Approximate Location"] = bool(point and point.get("approximate"))
        properties["Geocode Method"] = point["method"] if point else None
        properties.update(extras.get(row["Location"], {}))
        features.append({"type": "Feature", "geometry": geometry, "properties": properties})
    return {"type": "FeatureCollection", "features": features}


def run_permits(zoning_fc: dict) -> dict:
    print("Fetching Building Permit Report (current + previous year)...")
    rows, meta = fetch_permits()
    permit_numbers = [r["Permit Number"] for r in rows]
    check_no_duplicate_keys(permit_numbers, "Building Permit Report")

    permits_dir = DATA_DIR / "permits"
    previous_fc = load_latest(permits_dir)
    previous_count = len(previous_fc["features"]) if previous_fc else None
    check_not_suspicious_drop(len(rows), previous_count, "Building Permit Report")

    addresses = [r["Location"] for r in rows]
    neighbourhoods = {r["Location"]: r["Subdivision Code"] for r in rows if r["Subdivision Code"]}
    print(f"Geocoding {len(set(addresses))} unique addresses (City address points first)...")
    geocoded = geocode_all(addresses, neighbourhoods)
    check_geocode_success_rate(addresses, geocoded)
    methods = {}
    for r in rows:
        m = (geocoded.get(r["Location"]) or {}).get("method", "none")
        methods[m] = methods.get(m, 0) + 1
    print(f"  geocode methods (permit rows): {methods}")

    print("Joining permits to zoning, community association, ward and parcel...")
    extras = enrich_points(geocoded, zoning_fc)

    new_fc = _permits_to_geojson(rows, geocoded, extras)
    props = [f["properties"] for f in new_fc["features"]]
    check_reconciles_to_source(
        len(props), sum(p["Estimated Cost of Construction"] or 0 for p in props), meta, "Building Permit Report"
    )

    diff = diff_features(previous_fc, new_fc, key_fn=lambda f: f["properties"]["Permit Number"])
    write_snapshot(permits_dir, new_fc)
    print(f"Permits: {diff.summary()}")
    joined = sum(1 for p in props if str(p["Join Quality"]).startswith("joined"))
    return {
        "permits_in_window": len(props),
        "permit_cost_total_in_window": round(sum(p["Estimated Cost of Construction"] or 0 for p in props)),
        "geocode_methods": methods,
        "rows_joined_to_zoning_parcel_area": joined,
        "source": meta,
        "diff": {"added": len(diff.added), "changed": len(diff.changed), "removed": len(diff.removed)},
    }


def run_zoning() -> tuple[dict, dict]:
    print("Fetching Zoning and Land Use layer...")
    new_fc = fetch_zoning()
    object_ids = [f["properties"]["GIS.Zoning.OBJECTID"] for f in new_fc["features"]]
    check_no_duplicate_keys(object_ids, "Zoning and Land Use")

    zoning_dir = DATA_DIR / "zoning"
    previous_fc = load_latest(zoning_dir)
    previous_count = len(previous_fc["features"]) if previous_fc else None
    check_not_suspicious_drop(len(new_fc["features"]), previous_count, "Zoning and Land Use")

    diff = diff_features(
        previous_fc,
        new_fc,
        key_fn=lambda f: f["properties"]["GIS.Zoning.OBJECTID"],
        ignore_fields=ZONING_BOOKKEEPING_FIELDS,
    )
    write_snapshot(zoning_dir, new_fc)
    print(f"Zoning: {diff.summary()}")

    # Real rezonings: compare against the newest snapshot from an EARLIER day
    # (so re-running on the same day is idempotent), and trace each one back
    # to the application that preceded it.
    earlier = sorted(p for p in (zoning_dir / "snapshots").glob("*.geojson") if p.stem < date.today().isoformat())
    events_total = new_events = 0
    if earlier:
        baseline_fc = json.loads(earlier[-1].read_text(encoding="utf-8"))
        applications = load_applications(DATA_DIR / "proposed_development")
        events = detect_changes(baseline_fc, new_fc, applications, fetch_address_index(), earlier[-1].stem)
        before = len(json.loads((DATA_DIR / "zoning_changes" / "events.json").read_text(encoding="utf-8"))) if (DATA_DIR / "zoning_changes" / "events.json").exists() else 0
        merged = merge_events(DATA_DIR / "zoning_changes" / "events.json", events)
        events_total, new_events = len(merged), len(merged) - before
        print(f"Zoning changes vs {earlier[-1].stem}: {len(events)} real rezonings detected ({new_events} new to the archive)")
    return new_fc, {
        "zoning_districts": len(new_fc["features"]),
        "diff_ignoring_bookkeeping": {"added": len(diff.added), "changed": len(diff.changed), "removed": len(diff.removed)},
        "rezoning_events_total": events_total,
        "rezoning_events_new": new_events,
    }


def _proposed_development_to_geojson(entries: list[dict], geocoded: dict) -> dict:
    features = []
    for entry in entries:
        target = primary_geocode_target(entry["Address"])
        coords = geocoded.get(target)
        properties = {k: _clean(v) for k, v in entry.items()}
        properties["Approximate Location"] = bool(coords and coords.get("approximate"))

        geometry = None
        parcel_apn = None
        if coords and coords.get("method") == "city_address_point":
            parcel = find_containing_parcel(coords["lon"], coords["lat"], entry.get("Description"))
            if parcel:
                geometry = parcel["geometry"]
                parcel_apn = parcel["properties"].get("APN")
            else:
                geometry = {"type": "Point", "coordinates": [coords["lon"], coords["lat"]]}
        elif coords:
            geometry = {"type": "Point", "coordinates": [coords["lon"], coords["lat"]]}
        properties["Matched Parcel APN"] = parcel_apn
        properties["Geocode Method"] = coords.get("method") if coords else None

        features.append({"type": "Feature", "geometry": geometry, "properties": properties})
    return {"type": "FeatureCollection", "features": features}


def run_proposed_development() -> None:
    print("Fetching Proposed Development notices...")
    entries = fetch_proposed_development()
    check_proposed_development_entries(entries)

    file_numbers = [e["File Number"] for e in entries]
    check_no_duplicate_keys(file_numbers, "Proposed Development")

    targets = [primary_geocode_target(e["Address"]) for e in entries]
    print(f"Geocoding {len(set(targets))} addresses...")
    geocoded = geocode_all(targets)
    geocoded_count = sum(1 for t in targets if geocoded.get(t))
    print(
        f"Geocoded {geocoded_count}/{len(targets)} "
        "(no hard threshold here -- list is too small for a percentage to be meaningful)"
    )

    print("Matching each application to its property parcel...")
    proposed_dir = DATA_DIR / "proposed_development"
    previous_fc = load_latest(proposed_dir)
    new_fc = _proposed_development_to_geojson(entries, geocoded)
    matched = sum(1 for f in new_fc["features"] if f["properties"]["Matched Parcel APN"])
    print(f"Matched {matched}/{len(entries)} to a single property parcel")

    diff = diff_features(previous_fc, new_fc, key_fn=lambda f: f["properties"]["File Number"])
    write_snapshot(proposed_dir, new_fc)
    print(f"Proposed Development: {diff.summary()}")


def _flat_entries_to_geojson(entries: list[dict]) -> dict:
    """For non-spatial entries (annual city-wide stats) -- reuses the same
    FeatureCollection/diff/snapshot machinery as the geospatial sources
    (already handles null geometry fine for ungeocoded rows) rather than a
    separate storage format."""
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": None, "properties": {k: _clean(v) for k, v in e.items()}}
            for e in entries
        ],
    }


def run_population() -> None:
    print("Fetching Statistics Canada population estimates...")
    entries = fetch_population()
    check_time_series_entries(entries, ["Year", "Population"], "Population")
    check_no_duplicate_keys([e["Year"] for e in entries], "Population")
    check_no_wild_swing(entries, "Population", "Population")

    population_dir = DATA_DIR / "population"
    previous_fc = load_latest(population_dir)
    new_fc = _flat_entries_to_geojson(entries)
    diff = diff_features(previous_fc, new_fc, key_fn=lambda f: f["properties"]["Year"])
    write_snapshot(population_dir, new_fc)
    print(f"Population: {diff.summary()}")


def run_rental_market() -> None:
    print("Fetching CMHC rental market data...")
    entries = fetch_rental_market()
    check_time_series_entries(entries, ["Year", "Vacancy Rate", "Average Rent"], "Rental Market")
    check_no_duplicate_keys([e["Year"] for e in entries], "Rental Market")
    check_no_wild_swing(entries, "Average Rent", "Rental Market")

    rental_dir = DATA_DIR / "rental_market"
    previous_fc = load_latest(rental_dir)
    new_fc = _flat_entries_to_geojson(entries)
    diff = diff_features(previous_fc, new_fc, key_fn=lambda f: f["properties"]["Year"])
    write_snapshot(rental_dir, new_fc)
    print(f"Rental Market: {diff.summary()}")


def run_migration() -> None:
    print("Fetching Statistics Canada components of population change...")
    entries = fetch_migration()
    check_time_series_entries(
        entries, ["Year", "Births", "Deaths", "Immigrants"], "Migration Components"
    )
    check_no_duplicate_keys([e["Year"] for e in entries], "Migration Components")
    # Births/Deaths track total population closely and shouldn't swing hard
    # year over year. Deliberately NOT applied to Immigrants (checked against
    # real data: it moved 57% between 2010-2011 alone, and >65% in the 2022
    # immigration surge -- genuinely volatile on this small a base, subject to
    # federal policy shifts, not a signal of a parsing error) or either net
    # migration field (can cross zero, where relative change is meaningless).
    for field in ("Births", "Deaths"):
        check_no_wild_swing(entries, field, "Migration Components")

    migration_dir = DATA_DIR / "migration"
    previous_fc = load_latest(migration_dir)
    new_fc = _flat_entries_to_geojson(entries)
    diff = diff_features(previous_fc, new_fc, key_fn=lambda f: f["properties"]["Year"])
    write_snapshot(migration_dir, new_fc)
    print(f"Migration Components: {diff.summary()}")


def _log_run(stats: dict) -> None:
    """Append one line per run so counts/totals can be audited over time."""
    entry = {"run_at": datetime.now().isoformat(timespec="seconds"), **stats}
    with open(DATA_DIR / "run_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + chr(10))


def main() -> int:
    stats: dict = {}
    try:
        run_proposed_development()  # first: its snapshot archive feeds rezoning-change tracing
        zoning_fc, stats["zoning"] = run_zoning()
        stats["permits"] = run_permits(zoning_fc)
        run_population()
        run_rental_market()
        run_migration()
    except VerificationError as e:
        print(f"VERIFICATION FAILED: {e}", file=sys.stderr)
        return 1
    _log_run(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
