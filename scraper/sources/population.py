"""Fetch Regina population estimates from Statistics Canada's Web Data
Service (WDS) API -- Table 17-10-0155-01, "Population estimates, July 1, by
census subdivision, 2021 boundaries". Official annual estimates, not a scrape.
"""
import requests

WDS_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods"
PRODUCT_ID = 17100155
REGINA_COORDINATE = "2955.0.0.0.0.0.0.0.0.0"  # Regina (CY), Saskatchewan


def fetch_population() -> list[dict]:
    resp = requests.post(
        WDS_URL,
        json=[{"productId": PRODUCT_ID, "coordinate": REGINA_COORDINATE, "latestN": 15}],
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()[0]
    if payload["status"] != "SUCCESS":
        raise RuntimeError(f"StatCan WDS request failed: {payload}")

    points = payload["object"]["vectorDataPoint"]
    return [
        {
            "Year": int(p["refPerRaw"][:4]),
            "Population": int(p["value"]),
            "Release Date": p["releaseTime"][:10],
        }
        for p in points
    ]
