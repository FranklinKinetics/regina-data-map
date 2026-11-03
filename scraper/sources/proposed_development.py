"""Fetch and parse the City of Regina "Proposed Development" public notices.

Unlike the Building Permit Report and Zoning feed, this isn't on the CKAN
open-data portal (open.regina.ca) -- it's a hand-authored page on the main
city site, so it's HTML scraping rather than a clean API. Confirmed
server-rendered (no JS needed) and its table structure directly against the
live page before writing this.
"""
import re

import requests
from bs4 import BeautifulSoup

URL = "https://www.regina.ca/business-development/land-property-development/planning/proposed-development/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; regina-transparency/0.1)"}


def _parse_detail_row(td, address: str) -> dict:
    # Screen-reader-only "Opens in new window" spans get inlined by get_text()
    # otherwise, polluting the Status/link text.
    for sr in td.find_all(class_="screen-reader-only"):
        sr.decompose()

    full_text = td.get_text(" ", strip=True)
    match = re.search(r"File Number:\s*([A-Za-z0-9]+)", full_text)
    file_number = match.group(1) if match else None

    ul = td.find("ul")
    lis = ul.find_all("li") if ul else []

    plain_texts = []
    public_notice_url = None
    site_plan_url = None
    status = None
    comments_open = False

    for li in lis:
        li_text = li.get_text(" ", strip=True)
        link = li.find("a")
        if li_text.startswith("Status:"):
            status = li_text[len("Status:") :].strip()
            comments_open = "due by" in status.lower()
        elif link:
            href = link.get("href", "")
            full_url = href if href.startswith("http") else f"https://www.regina.ca{href}"
            if "public notice" in li_text.lower():
                public_notice_url = full_url
            elif "site and building" in li_text.lower():
                site_plan_url = full_url
        else:
            plain_texts.append(li_text)

    return {
        "File Number": file_number,
        "Address": address,
        "Application Type": plain_texts[0] if plain_texts else None,
        "Description": plain_texts[1] if len(plain_texts) > 1 else None,
        "Status": status,
        "Comments Open": comments_open,
        "Public Notice URL": public_notice_url,
        "Site Plan URL": site_plan_url,
    }


def primary_geocode_target(address: str) -> str:
    """Some entries join two civic numbers on one street with " & "
    (e.g. "1202 & 1212 Retallack Street") -- the last token carries the full
    "number + street name", which is good enough for an approximate pin.
    """
    if " & " in address:
        address = address.split(" & ")[-1]
    return f"{address}, Regina, Saskatchewan"


def fetch_proposed_development() -> list[dict]:
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    target_table = next(
        (t for t in soup.find_all("table") if "File Number" in t.get_text()), None
    )
    if target_table is None:
        return []

    entries = []
    pending_address = None
    for row in target_table.find_all("tr"):
        td = row.find("td")
        if td is None:
            continue
        text = td.get_text(" ", strip=True)
        if "File Number" in text:
            if pending_address:
                entries.append(_parse_detail_row(td, pending_address))
            pending_address = None
        else:
            strong = td.find("strong")
            pending_address = strong.get_text(strip=True) if strong else text

    return entries
