"""Join geocoded points to zoning district, community association, ward and
property parcel (all City of Regina open data), so every permit carries the
planning context around it.

Joins are only made for points from the City's own address layer. Points
from the OpenStreetMap fallback were found to be unreliable (some were
kilometres off), and neighbourhood-centroid points are deliberately
approximate -- joining either to a boundary would produce confident-looking
but wrong zoning/parcel answers, so they get no join and are flagged.
"""
import json

import requests
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

COMMUNITY_ASSOCIATIONS_URL = "https://opengis.regina.ca/arcgis/rest/services/OpenData/CommunityAssociations/MapServer/0/query"
WARDS_URL = "https://opengis.regina.ca/arcgis/rest/services/OpenData/Wards/MapServer/0/query"
PARCELS_URL = "https://opengis.regina.ca/arcgis/rest/services/OpenData/Parcels/MapServer/0/query"
PARCEL_BATCH = 300

JOINABLE_METHOD = "city_address_point"


class AreaLookup:
    """Point-in-polygon lookup over a set of GeoJSON features."""

    def __init__(self, features: list[dict]):
        self._geoms = [shape(f["geometry"]) for f in features if f.get("geometry")]
        self._props = [f["properties"] for f in features if f.get("geometry")]
        self._tree = STRtree(self._geoms)

    def lookup(self, lon: float, lat: float) -> dict | None:
        hits = self._tree.query(Point(lon, lat), predicate="intersects")
        if len(hits) == 0:
            return None
        return self._props[int(hits[0])]


def _fetch_features(url: str) -> list[dict]:
    resp = requests.get(
        url, params={"where": "1=1", "outFields": "*", "outSR": "4326", "f": "geojson"}, timeout=60
    )
    resp.raise_for_status()
    return resp.json()["features"]


def _parcel_matches(points: dict[str, tuple[float, float]]) -> dict[str, dict]:
    """Batch point-in-parcel: one multipoint query per PARCEL_BATCH points,
    then an exact local containment test to map each point to its parcel."""
    results: dict[str, dict] = {}
    keys = list(points)
    for start in range(0, len(keys), PARCEL_BATCH):
        batch = keys[start : start + PARCEL_BATCH]
        geometry = json.dumps(
            {"points": [list(points[k]) for k in batch], "spatialReference": {"wkid": 4326}}
        )
        resp = requests.post(
            PARCELS_URL,
            data={
                "geometry": geometry,
                "geometryType": "esriGeometryMultipoint",
                "inSR": "4326",
                "outSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "APN,ACRES,ZONING,SM_AREA",
                "f": "geojson",
            },
            timeout=120,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if not features:
            continue
        geoms = [shape(f["geometry"]) for f in features]
        tree = STRtree(geoms)
        for key in batch:
            lon, lat = points[key]
            hits = tree.query(Point(lon, lat), predicate="intersects")
            if len(hits):
                results[key] = features[int(hits[0])]["properties"]
    return results


def enrich_points(points: dict[str, dict], zoning_fc: dict) -> dict[str, dict]:
    """points: {key: {"lon","lat","method"}}  ->  {key: extra properties}"""
    zoning = AreaLookup(zoning_fc["features"])
    associations = AreaLookup(_fetch_features(COMMUNITY_ASSOCIATIONS_URL))
    wards = AreaLookup(_fetch_features(WARDS_URL))

    joinable = {
        k: (p["lon"], p["lat"])
        for k, p in points.items()
        if p and p.get("method") == JOINABLE_METHOD
    }
    parcels = _parcel_matches(joinable)

    extras: dict[str, dict] = {}
    for key, point in points.items():
        if key not in joinable:
            extras[key] = {
                "Zoning Code": None,
                "Zoning Description": None,
                "Community Association": None,
                "Ward": None,
                "Parcel APN": None,
                "Parcel Acres": None,
                "Join Quality": "not joined (approximate location)" if point else "not joined (no location)",
            }
            continue

        lon, lat = joinable[key]
        z = zoning.lookup(lon, lat) or {}
        ca = associations.lookup(lon, lat) or {}
        ward = wards.lookup(lon, lat) or {}
        parcel = parcels.get(key) or {}

        zone_code = z.get("GIS.Zoning.ZONING")
        parcel_zone = parcel.get("ZONING")
        if zone_code and parcel_zone:
            quality = "joined" if zone_code == parcel_zone else "joined (zoning layers disagree)"
        else:
            quality = "joined (partial)"

        extras[key] = {
            "Zoning Code": zone_code,
            "Zoning Description": z.get("GIS.ZONING_CODE_2019.DESCRIPTION") or z.get("GIS.Zoning.ZONING_DESC"),
            "Community Association": ca.get("NAME"),
            "Ward": ward.get("NAME"),
            "Parcel APN": parcel.get("APN"),
            "Parcel Acres": parcel.get("ACRES"),
            "Join Quality": quality,
        }
    return extras
