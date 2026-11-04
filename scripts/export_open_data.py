"""Write the open data files that people can download and use in their own tools.

    python -m scripts.export_open_data [input.json] [output_folder]

Reads the finished map data (lab-02/latest-v1.json) and writes, into site/data/ by default:

  permits.csv           every building permit since January 2020, one row each (opens in Excel, Sheets, R, pandas)
  permits.geojson       the same permits that have a map location, as points (for GIS and web maps)
  rezonings.json        rezonings spotted by comparing the City's zoning maps over time
  applications.json     the City's current Proposed Development applications
  context.json          Regina population, rents, vacancy and population change (Statistics Canada, CMHC)
  data-dictionary.json  what every column means, plus the caveats and the licence
  index.html            a plain download page

No applicant, owner or company names exist in this data. Permits are places and projects, not people.
"""
import csv
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COLUMNS = [
    ("permit_id", "id", "The City's permit number. Unique."),
    ("date_issued", "d", "Date the permit was issued (YYYY-MM-DD). A permit number that the City lists more than once is kept once, on its first issue date."),
    ("address", "a", "Street address of the property."),
    ("neighbourhood", "n", "Neighbourhood name from the City's permit report."),
    ("community_association", "ca", "City community association the address falls in (from the City's boundary layer). Blank if none."),
    ("zoning_code", "z", "Zoning district code at the address in the City's CURRENT zoning layer. For an older permit this is today's zone, not necessarily the zone at the time."),
    ("work_group", "g", "Our grouping of the type of work: new-homes, new-multi, new-commercial, commercial-reno, suites, home-work, other."),
    ("permit_type", "t", "The City's permit application type, for example 'Renovation/Alteration' or 'Multi-Unit Dwelling 3+ Units'."),
    ("building_use", "u", "The City's building use code, for example RES or COM. Blank if not given."),
    ("declared_value", "v", "The applicant's declared construction value in dollars (whole dollars). An estimate made when applying. Not an appraisal, a sale price or the final cost."),
    ("new_units", "units", "Number of dwelling units the City lists on the permit (0 when not applicable)."),
    ("latitude", "lat", "WGS84 latitude of the matched City address point. Blank when the address could not be matched (about 3% of permits)."),
    ("longitude", "lon", "WGS84 longitude of the matched City address point. Blank when the address could not be matched."),
]

CAVEATS = [
    "Permits are listed when issued. A permit means work is approved to begin. It does not mean the work is finished or that it will cost the declared amount.",
    "Declared values are the applicant's own estimates. A few very large permits can dominate any total.",
    "About 3% of permits could not be matched to a City address point and have no coordinates.",
    "Older permits are placed using today's City address points, zoning layer and community areas.",
    "Some permit numbers appear more than once in the City's yearly files (about 20 in six years); each is counted once, on its first issue date.",
    "The City publishes weekly, so the newest days are missing.",
    "Rezonings are found by comparing the City's own zoning maps over time and only go back to the first snapshot (see meta in rezonings.json).",
    "No names of people or companies are included.",
]


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "lab-02" / "latest-v1.json"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "site" / "data"
    d = json.loads(src.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    meta, permits = d["meta"], d["permits"]

    with (out / "permits.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([c[0] for c in COLUMNS])
        for p in permits:
            w.writerow(["" if p.get(c[1]) is None else p[c[1]] for c in COLUMNS])

    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
              "properties": {c[0]: p.get(c[1]) for c in COLUMNS if c[1] not in ("lat", "lon")}} for p in permits if p.get("lon") is not None]
    (out / "permits.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    (out / "rezonings.json").write_text(json.dumps({"first_snapshot": meta["asof"].get("rezoning_baseline"), "rezonings": d["rezonings"]}, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "applications.json").write_text(json.dumps({"snapshot": meta["asof"]["applications"], "applications": d["applications"]}, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "context.json").write_text(json.dumps({
        "population": {"source": "Statistics Canada, Table 17-10-0155-01 (July 1 estimates, Regina)", "rows": d["series"]["population"]},
        "rent": {"source": "CMHC Rental Market Survey, Regina (average rent of purpose-built rentals, October; vacancy rate in per cent)", "rows": d["series"]["rent"]},
        "population_change": {"source": "Statistics Canada, Table 17-10-0149-01 (Regina area)", "rows": d["series"]["migration"]},
    }, indent=1), encoding="utf-8")
    (out / "data-dictionary.json").write_text(json.dumps({
        "built": meta["built"], "permits_issued_from": meta["asof"]["permits_start"], "permits_issued_through": meta["latest"], "permit_count": len(permits),
        "licence": meta["attribution"] + " Statistics Canada and CMHC figures: see the sources named in context.json.",
        "columns": {c[0]: c[2] for c in COLUMNS}, "work_groups": {g["key"]: g["label"] for g in meta["groups"]}, "caveats": CAVEATS,
    }, indent=1, ensure_ascii=False), encoding="utf-8")

    rows = "".join(f'<tr><td><a href="{n}">{n}</a></td><td>{html.escape(t)}</td></tr>' for n, t in [
        ("permits.csv", "Every permit since January 2020, one row each (spreadsheet-friendly)"),
        ("permits.geojson", "The permits that have a map location, as points"),
        ("rezonings.json", "Rezonings spotted in the City's zoning maps"),
        ("applications.json", "The City's current Proposed Development applications"),
        ("context.json", "Regina population, rents, vacancy and population change"),
        ("data-dictionary.json", "What every column means, the caveats and the licence")])
    (out / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Regina Data Map: open data</title>'
        '<style>body{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;color:#211F21}td{padding:.35rem .8rem .35rem 0;vertical-align:top}</style>'
        f"<h1>Regina Data Map: open data</h1><p>Free files behind the map, rebuilt every Friday. Permits issued {meta['asof']['permits_start']} to {meta['latest']} ({len(permits):,} permits).</p>"
        f"<table>{rows}</table><h2>Before you use it</h2><ul>" + "".join(f"<li>{html.escape(c)}</li>" for c in CAVEATS) +
        f"</ul><p>{html.escape(meta['attribution'])} Statistics Canada and CMHC figures come from the sources named in context.json. Made by Franklin Kinetics, Regina. Not affiliated with the City of Regina. Information, not advice; may contain errors.</p>",
        encoding="utf-8")
    print(f"wrote {len(list(out.iterdir()))} files to {out}")


if __name__ == "__main__":
    main()
