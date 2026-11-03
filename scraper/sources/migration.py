"""Fetch components of Regina's population change from Statistics Canada's
Web Data Service (WDS) API -- Table 17-10-0149-01, "Components of population
change by census metropolitan area and census agglomeration". Breaks down
*why* population is changing (births, deaths, immigration, migration),
rather than just the total from population.py.
"""
import requests

WDS_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods"
PRODUCT_ID = 17100149
REGINA_GEO = 34  # Regina (CMA), Saskatchewan

# component member id -> the field name we store it under
COMPONENTS = {
    1: "Births",
    2: "Deaths",
    3: "Immigrants",
    8: "Net Interprovincial Migration",
    9: "Net Intraprovincial Migration",
}


def _coordinate(component_id: int) -> str:
    # Geography.Component.Gender(Total).AgeGroup(All ages).0.0.0.0.0.0
    return f"{REGINA_GEO}.{component_id}.1.1.0.0.0.0.0.0"


def fetch_migration() -> list[dict]:
    payload = [
        {"productId": PRODUCT_ID, "coordinate": _coordinate(cid), "latestN": 15}
        for cid in COMPONENTS
    ]
    resp = requests.post(WDS_URL, json=payload, timeout=30)
    resp.raise_for_status()
    results = resp.json()

    by_year: dict[int, dict] = {}
    for entry in results:
        if entry["status"] != "SUCCESS":
            raise RuntimeError(f"StatCan WDS request failed: {entry}")
        obj = entry["object"]
        # Match the response back to its component by the coordinate it
        # actually carries -- confirmed necessary against real data: the API
        # does not reliably preserve request order in the response array.
        component_id = int(obj["coordinate"].split(".")[1])
        field = COMPONENTS[component_id]
        for point in obj["vectorDataPoint"]:
            year = int(point["refPerRaw"][:4])
            by_year.setdefault(year, {"Year": year})[field] = int(point["value"])

    return [by_year[y] for y in sorted(by_year)]
