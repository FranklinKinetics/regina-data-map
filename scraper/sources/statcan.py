"""Shared request helper for Statistics Canada's Web Data Service (WDS).

StatCan's WDS is sometimes slow or briefly down (the 2026-11-27 refresh
failed on a 30-second read timeout), so each request gets a longer wait and
a few tries before giving up.
"""
import time

import requests

WDS_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods"
TIMEOUT_SECONDS = 90
RETRY_WAITS = (15, 60)  # seconds between attempts: 3 attempts in all


def _is_retryable(e: requests.RequestException) -> bool:
    if isinstance(e, (requests.ConnectionError, requests.Timeout)):
        return True
    # Server-side errors are worth retrying; a 4xx means the request itself is wrong.
    return isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code >= 500


def post_wds(payload: list[dict]) -> list[dict]:
    """POST to WDS. Raises requests.RequestException if every attempt fails."""
    for wait in (*RETRY_WAITS, None):
        try:
            resp = requests.post(WDS_URL, json=payload, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if wait is None or not _is_retryable(e):
                raise
            print(f"  StatCan request failed ({type(e).__name__}); retrying in {wait}s...")
            time.sleep(wait)
