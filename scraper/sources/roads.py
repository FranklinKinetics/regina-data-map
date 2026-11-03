"""City of Regina Road Centerline (open data, ArcGIS MapServer layer).

Only used as a visual reference layer on the map, so it is fetched
separately from the permit pipeline and refreshed monthly by the builder.
"""
import json
from pathlib import Path

import requests

URL = "https://opengis.regina.ca/arcgis/rest/services/OpenData/RoadCenterline/MapServer/0/query"
PAGE = 1000
FIELDS = "FULL_NAME,ROAD_FUNC,HWYNUMBER"


def fetch_roads() -> dict:
    features = []
    offset = 0
    while True:
        resp = requests.get(
            URL,
            params={"where": "1=1", "outFields": FIELDS, "outSR": "4326", "f": "geojson",
                    "resultOffset": offset, "resultRecordCount": PAGE, "orderByFields": "OBJECTID"},
            timeout=120,
        )
        resp.raise_for_status()
        batch = resp.json().get("features", [])
        features += batch
        if len(batch) < PAGE:
            break
        offset += PAGE
    return {"type": "FeatureCollection", "features": features}


def load_or_fetch(path: Path, max_age_days: int = 30) -> dict:
    import time

    if path.exists() and (time.time() - path.stat().st_mtime) < max_age_days * 86400:
        return json.loads(path.read_text(encoding="utf-8"))
    fc = fetch_roads()
    expected = requests.get(URL, params={"where": "1=1", "returnCountOnly": "true", "f": "json"}, timeout=60).json()["count"]
    if len(fc["features"]) != expected:
        raise RuntimeError(f"roads: fetched {len(fc['features'])} segments but the service reports {expected}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fc), encoding="utf-8")
    return fc
