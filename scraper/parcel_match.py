"""Match a geocoded point to the actual property parcel (lot) it falls on.

This deliberately does NOT use the Zoning and Land Use layer -- checked
against real data and its polygons are zoning *districts* (one polygon per
contiguous area sharing a zoning code, e.g. ~155 hectares / 2km across for a
single match), not individual lots. The City's Parcels service
("ASSESSMENT_REGIONS" -- the ownership/tax parcel fabric, ~72,800 features
citywide) is the real per-lot dataset: confirmed real matches come back at
0.07-0.23 acres, i.e. an actual single property.
"""
import re

import requests
from shapely.geometry import Point, shape

QUERY_URL = "https://opengis.regina.ca/arcgis/rest/services/OpenData/Parcels/MapServer/0/query"
SEARCH_RADIUS_DEGREES = 0.001  # ~100m -- wide enough to always catch the true parcel as a candidate

# Geocoding isn't pixel-perfect; a point can land just outside its own
# parcel's boundary. Only close gaps this small, and only when doing so
# doesn't contradict the application: checked against real data, a ~24m-away
# candidate had zoning "I" (Industrial) when the application said it was
# rezoning "from MH" -- a genuinely wrong parcel, not just an imprecise one.
NEAR_TOLERANCE_METERS = 15


def _parse_from_zoning_code(description: str | None) -> str | None:
    """Extract the current zoning code a "Zoning Bylaw Amendment" description
    states it's rezoning *from* (e.g. "from RU - Residential Urban Zone to
    RH..." -> "RU"). Other application types don't state one -- returns None.
    """
    match = re.search(r"from\s+([A-Z]{1,4}(?:-[A-Z0-9]+)?)\s*[-–]", description or "")
    return match.group(1) if match else None


def find_containing_parcel(lon: float, lat: float, description: str | None = None) -> dict | None:
    """Return the GeoJSON Feature for the parcel at (lon, lat), or None if
    no parcel can be confidently matched."""
    envelope = (
        f"{lon - SEARCH_RADIUS_DEGREES},{lat - SEARCH_RADIUS_DEGREES},"
        f"{lon + SEARCH_RADIUS_DEGREES},{lat + SEARCH_RADIUS_DEGREES}"
    )
    resp = requests.get(
        QUERY_URL,
        params={
            "geometry": envelope,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "f": "geojson",
        },
        timeout=30,
    )
    resp.raise_for_status()
    candidates = resp.json().get("features", [])

    point = Point(lon, lat)
    exact = [f for f in candidates if shape(f["geometry"]).contains(point)]
    if exact:
        return exact[0]

    expected_code = _parse_from_zoning_code(description)
    by_distance = sorted(candidates, key=lambda f: shape(f["geometry"]).distance(point))
    for feature in by_distance:
        dist_m = shape(feature["geometry"]).distance(point) * 111_000
        if dist_m > NEAR_TOLERANCE_METERS:
            break
        if expected_code and feature["properties"].get("ZONING") != expected_code:
            continue
        return feature

    return None
