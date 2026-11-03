"""Fetch CMHC's Rental Market Survey historical summary for Regina.

Server-rendered HTML table at a stable, parameterized URL -- confirmed via
plain `requests` (no JS needed), so this is a straightforward parse rather
than a scrape of a JS-rendered app.
"""
import requests
from bs4 import BeautifulSoup

URL = "https://www03.cmhc-schl.gc.ca/hmip-pimh/en/TableMapChart/TableMatchingCriteria"
PARAMS = {
    "GeographyType": "CensusSubDivision",
    "GeographyId": "4706027",  # Regina (CY), Saskatchewan
    "CategoryLevel1": "Primary Rental Market",
    "CategoryLevel2": "Summary Statistics",
    "RowField": "TIMESERIES",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; regina-transparency/0.1)"}


def _parse_number(text: str) -> float | None:
    text = text.replace(",", "").strip()
    if not text or text in ("**", "++"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fetch_rental_market() -> list[dict]:
    resp = requests.get(URL, params=PARAMS, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    table = soup.find("table")
    if table is None:
        return []

    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if not cells or "October" not in cells[0]:
            continue  # header row or a non-data row
        year = int(cells[0].split()[0])
        rows.append(
            {
                "Year": year,
                "Vacancy Rate": _parse_number(cells[1]),
                "Average Rent": _parse_number(cells[5]),
                "Units": _parse_number(cells[11]),
            }
        )
    return rows
