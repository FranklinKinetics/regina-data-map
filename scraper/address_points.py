"""Authoritative geocoding from the City of Regina's own Address Point layer
(OpenData/Address MapServer, ~87k points with exact coordinates).

This is the primary geocoder. Checked against real permits it matched 98.6%
of recent addresses -- including brand-new streets the free OpenStreetMap
geocoder couldn't find at all -- and the OSM geocoder was found to place
some addresses kilometres from their true location (e.g. 120 Broad Street).
OSM/Nominatim (geocode.py) is kept only as a fallback for the few misses.
"""
import re

import requests

QUERY_URL = "https://opengis.regina.ca/arcgis/rest/services/OpenData/Address/MapServer/0/query"
PAGE_SIZE = 1000


def normalize_address(raw: str) -> str:
    """'1700 ELPHINSTONE STREET, Unit:G, REGINA, SK S4P2Z6' -> '1700 ELPHINSTONE STREET'.

    Permits sometimes list several addresses joined with ' | ' (first is used),
    and condo/unit permits carry a 'Unit:X' suffix the address layer doesn't key on.
    """
    address = str(raw).split(" | ")[0]
    address = re.sub(r",?\s*Unit:[^,]+", "", address)
    address = re.split(r",\s*REGINA", address, flags=re.I)[0]
    return re.sub(r"\s+", " ", address).strip().upper()


def fetch_address_index() -> dict[str, tuple[float, float]]:
    """Return {normalized street address: (lon, lat)} for the whole city."""
    index: dict[str, tuple[float, float]] = {}
    offset = 0
    while True:
        resp = requests.get(
            QUERY_URL,
            params={
                "where": "1=1",
                "outFields": "FULLADDRESS,LONGITUDE,LATITUDE",
                "returnGeometry": "false",
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "orderByFields": "OBJECTID",
            },
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
        features = payload.get("features", [])
        for f in features:
            a = f["attributes"]
            if a.get("FULLADDRESS") and a.get("LONGITUDE") is not None:
                index.setdefault(a["FULLADDRESS"].upper().strip(), (a["LONGITUDE"], a["LATITUDE"]))
        if not features or not payload.get("exceededTransferLimit"):
            break
        offset += PAGE_SIZE
    return index
