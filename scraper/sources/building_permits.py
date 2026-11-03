"""Fetch and normalize the City of Regina Building Permit Report.

The report is published as one XLSX per calendar year. This fetches the
current year plus the previous one so a rolling 12-month view is possible,
then keeps only permits issued inside a trailing window (WINDOW_DAYS).

Source quirks handled here (all observed in real files, not assumed):
- Sheet name differs between years ("WBR - Redacted" in 2026, "Query Results"
  in 2025), so the first sheet is read.
- The cost column is "Estimated Cost of Construction" in 2026 but "Cost of
  Construction" in 2025 (see COLUMN_ALIASES).
- Cost can be a non-numeric placeholder ("-"); it is coerced to null, not zero.
"""
import io
from datetime import date, timedelta

import pandas as pd
import requests

CKAN_PACKAGE_URL = "https://openregina.ca/api/3/action/package_show"
DATASET_ID = "building-permit-report"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; regina-transparency/0.1)"}
WINDOW_DAYS = 400  # ~13 months, so "last 12 months" is always fully covered

COLUMN_ALIASES = {
    "Cost of Construction": "Estimated Cost of Construction",
}

EXPECTED_COLUMNS = [
    "Permit Number",
    "Permit Application Type",
    "Date Issued",
    "Building Use",
    "Work Class",
    "Estimated Cost of Construction",
    "Number of Units",
    "Number of Stories",
    "Stats Can # of Units Lost",
    "Location",
    "LocType",
    "Subdivision Code",
    "Name",
    "Contact Type Description",
    "Construction Type",
]


def _resources_for_years(years: list[int]) -> list[dict]:
    resp = requests.get(
        CKAN_PACKAGE_URL, params={"id": DATASET_ID}, headers=HEADERS, timeout=30
    )
    resp.raise_for_status()
    resources = resp.json()["result"]["resources"]
    found = []
    for year in years:
        match = next(
            (r for r in resources if str(year) in r["name"] and r["format"] == "XLSX"), None
        )
        if match is None:
            raise RuntimeError(f"No XLSX resource found for year {year}")
        found.append({"year": year, **match})
    return found


def _load_year(resource: dict) -> pd.DataFrame:
    resp = requests.get(resource["url"], headers=HEADERS, timeout=120)
    resp.raise_for_status()
    df = pd.read_excel(io.BytesIO(resp.content), sheet_name=0)
    df = df.rename(columns=COLUMN_ALIASES)
    missing = set(EXPECTED_COLUMNS) - set(df.columns)
    if missing:
        raise RuntimeError(
            f"Building Permit Report {resource['year']} is missing expected columns: {missing}"
        )
    return df[EXPECTED_COLUMNS].assign(**{"Report Year": resource["year"]})


def fetch_permits(today: date | None = None) -> tuple[list[dict], dict]:
    """Return (rows inside the trailing window, source metadata).

    The metadata records full-file row counts and cost totals per year so a
    run can be reconciled against the published source.
    """
    today = today or date.today()
    resources = _resources_for_years([today.year, today.year - 1])

    frames, source_meta = [], []
    for res in resources:
        df = _load_year(res)
        cost = pd.to_numeric(df["Estimated Cost of Construction"], errors="coerce")
        source_meta.append(
            {
                "resource": res["name"],
                "file": res["url"].rsplit("/", 1)[-1],
                "source_last_modified": res.get("last_modified"),
                "rows_in_file": int(len(df)),
                "cost_total_in_file": float(cost.sum()),
                "non_numeric_cost_rows": int(cost.isna().sum()),
                "first_issued": df["Date Issued"].min().date().isoformat(),
                "last_issued": df["Date Issued"].max().date().isoformat(),
            }
        )
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)
    df["Estimated Cost of Construction"] = pd.to_numeric(
        df["Estimated Cost of Construction"], errors="coerce"
    )
    cutoff = pd.Timestamp(today - timedelta(days=WINDOW_DAYS))
    df = df[df["Date Issued"] >= cutoff].copy()
    df["Date Issued"] = df["Date Issued"].dt.strftime("%Y-%m-%d")

    meta = {
        "window_days": WINDOW_DAYS,
        "rows_in_window": int(len(df)),
        "cost_total_in_window": float(df["Estimated Cost of Construction"].sum()),
        "files": source_meta,
    }
    return df.to_dict(orient="records"), meta
