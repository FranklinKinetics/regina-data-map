"""Detect real rezonings by comparing two zoning snapshots, and link each to
the rezoning application (if any) that preceded it.

Why this exists: the City's zoning layer stamps an UPDATE_DATE on ~4 parcels
a day regardless of any real change (327 of 328 "changed" records between
July and October were that noise), so the layer's own change stamps can't be
used. Real rezonings show up as (a) a brand-new zoning polygon whose
location used to be a different zone, (b) a polygon that grew into land that
used to be a different zone, or (c) a bylaw number appearing on a polygon.

Applications are matched by geography: the application's address point must
fall inside (or within ~25 m of) the changed polygon. Match confidence is
reported, never assumed.
"""
import json
from datetime import date
from pathlib import Path

import numpy as np
from shapely.geometry import Point, shape

from scraper.address_points import normalize_address
from scraper.enrich import COMMUNITY_ASSOCIATIONS_URL, WARDS_URL, AreaLookup, _fetch_features
from scraper.sources.proposed_development import primary_geocode_target

ZONE = "GIS.Zoning.ZONING"
ZONE_DESC = "GIS.Zoning.ZONING_DESC"
BYLAW = "GIS.Zoning.BYLAW_NUMBER"
OBJECT_ID = "GIS.Zoning.OBJECTID"
M2_PER_DEG2 = 111_000 * 70_600  # Regina's latitude
MIN_GROWTH_M2 = 100  # ignore sub-100 m^2 slivers from coordinate-precision noise
MATCH_BUFFER_DEG = 0.00025  # ~25 m


def load_applications(proposed_dir: Path) -> dict[str, dict]:
    """Every rezoning/discretionary application ever seen, from all archived
    snapshots (applications drop off the City's page once decided, so the
    archive is what lets a later bylaw be traced back to its application)."""
    apps: dict[str, dict] = {}
    for path in sorted((proposed_dir / "snapshots").glob("*.geojson")):
        for f in json.loads(path.read_text(encoding="utf-8"))["features"]:
            p = f["properties"]
            apps[p["File Number"]] = {**p, "last_seen_snapshot": path.stem}
    return apps


def _nearest_address(index: dict, lon: float, lat: float) -> str | None:
    names = list(index)
    coords = np.array([index[n] for n in names])
    d = (coords[:, 0] - lon) ** 2 * 0.5 + (coords[:, 1] - lat) ** 2
    return names[int(np.argmin(d))].title()


def detect_changes(
    old_fc: dict, new_fc: dict, applications: dict[str, dict], address_index: dict, baseline: str
) -> list[dict]:
    old_by_id = {f["properties"][OBJECT_ID]: f for f in old_fc["features"] if f.get("geometry")}
    new_by_id = {f["properties"][OBJECT_ID]: f for f in new_fc["features"] if f.get("geometry")}
    old_lookup = AreaLookup(old_fc["features"])
    areas = AreaLookup(_fetch_features(COMMUNITY_ASSOCIATIONS_URL))
    wards = AreaLookup(_fetch_features(WARDS_URL))

    app_points = {}
    for file_number, app in applications.items():
        hit = address_index.get(normalize_address(primary_geocode_target(app["Address"])))
        if hit:
            app_points[file_number] = Point(*hit)

    candidates = []  # (zoning_to, bylaw, description, geometry-of-change, polygon_id, kind)
    for pid, f in new_by_id.items():
        props = f["properties"]
        geom = shape(f["geometry"])
        if pid not in old_by_id:
            candidates.append((props[ZONE], props.get(BYLAW), props.get(ZONE_DESC), geom, pid, "new zoning polygon"))
            continue
        old_props = old_by_id[pid]["properties"]
        if old_props.get(ZONE) != props.get(ZONE):
            candidates.append((props[ZONE], props.get(BYLAW), props.get(ZONE_DESC), geom, pid, "zone code changed"))
            continue
        grown = geom.difference(shape(old_by_id[pid]["geometry"]))
        if not grown.is_empty and grown.area * M2_PER_DEG2 >= MIN_GROWTH_M2:
            candidates.append((props[ZONE], props.get(BYLAW), props.get(ZONE_DESC), grown, pid, "polygon expanded"))
        elif props.get(BYLAW) and props.get(BYLAW) != old_props.get(BYLAW):
            candidates.append((props[ZONE], props.get(BYLAW), props.get(ZONE_DESC), geom, pid, "bylaw number added"))

    events = []
    for zone_to, bylaw, desc, geom, pid, kind in candidates:
        point = geom.representative_point()
        old_zone_props = old_lookup.lookup(point.x, point.y) or {}
        zone_from = old_zone_props.get(ZONE)
        if kind in ("new zoning polygon", "polygon expanded") and zone_from == zone_to:
            continue  # re-drawn boundary, same zone -- not a rezoning

        matched = []
        for file_number, pt in app_points.items():
            if geom.buffer(MATCH_BUFFER_DEG).contains(pt):
                app = applications[file_number]
                matched.append(
                    {
                        "file_number": file_number,
                        "address": app["Address"],
                        "application_type": app["Application Type"],
                        "description": app["Description"],
                    }
                )
        events.append(
            {
                "event_id": f"zoning-{pid}",
                "kind": kind,
                "zoning_from": zone_from,
                "zoning_to": zone_to,
                "zoning_to_description": (desc or "").strip(),
                "bylaw_number": bylaw,
                "community_association": (areas.lookup(point.x, point.y) or {}).get("NAME"),
                "ward": (wards.lookup(point.x, point.y) or {}).get("NAME"),
                "lon": round(point.x, 6),
                "lat": round(point.y, 6),
                "nearest_address": _nearest_address(address_index, point.x, point.y),
                "approx_area_m2": round(geom.area * M2_PER_DEG2),
                "linked_applications": matched,
                "baseline_snapshot": baseline,
                "first_detected": date.today().isoformat(),
            }
        )
    return events


def merge_events(path: Path, new_events: list[dict]) -> list[dict]:
    """Cumulative, de-duplicated event archive (a rezoning is recorded once,
    on the first run that sees it)."""
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    known = {e["event_id"] for e in existing}
    merged = existing + [e for e in new_events if e["event_id"] not in known]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged
