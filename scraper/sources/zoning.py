"""Fetch the City of Regina Zoning and Land Use ArcGIS REST layer."""
import requests

QUERY_URL = "https://opengis.regina.ca/arcgis/rest/services/OpenData/ZoningAndLandUse/MapServer/0/query"
PAGE_SIZE = 1000
OBJECTID_FIELD = "GIS.Zoning.OBJECTID"

EXPECTED_PROPERTIES = [
    OBJECTID_FIELD,
    "GIS.Zoning.GLOBALID",
    "GIS.Zoning.ZONING",
    "GIS.Zoning.ZONING_DESC",
    "GIS.Zoning.LAND_U",
    "GIS.Zoning.LAND_DENSITY",
    "GIS.Zoning.UPDATE_DATE",
    "GIS.Zoning.BYLAW_NUMBER",
]


def _reported_count() -> int:
    resp = requests.get(
        QUERY_URL,
        params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["count"]


def fetch_zoning() -> dict:
    """Page through the zoning layer and return one merged GeoJSON FeatureCollection."""
    features = []
    offset = 0
    while True:
        resp = requests.get(
            QUERY_URL,
            params={
                "where": "1=1",
                "outFields": "*",
                "f": "geojson",
                "resultRecordCount": PAGE_SIZE,
                "resultOffset": offset,
            },
            timeout=60,
        )
        resp.raise_for_status()
        page = resp.json()
        page_features = page["features"]
        features.extend(page_features)
        if not page_features or not page.get("exceededTransferLimit"):
            break
        offset += PAGE_SIZE

    if features:
        missing = set(EXPECTED_PROPERTIES) - set(features[0]["properties"])
        if missing:
            raise RuntimeError(f"Zoning layer is missing expected fields: {missing}")

    reported = _reported_count()
    if len(features) != reported:
        raise RuntimeError(
            f"Paginated fetch returned {len(features)} features but service reports {reported}"
        )

    return {"type": "FeatureCollection", "features": features}
