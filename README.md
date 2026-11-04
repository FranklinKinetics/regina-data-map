# Regina Data Map

A free interactive map of building permits, zoning and neighbourhood numbers for Regina, Saskatchewan. Made by Franklin Kinetics (franklinkinetics.com).

This repository keeps the map's data fresh. Every Friday morning it downloads the latest government data, checks it, rebuilds the map and publishes it on GitHub Pages. Copies of the map that people have downloaded ask this page for newer data when they are opened online, and use the data inside the file when they are not.

## What is on the map

Government open data only:

- **City of Regina open data:** every building permit the City has published since January 2020 (shown with a date slider and a two-date picker), zoning, streets, addresses, proposed development notices. Contains information licensed under the Open Government Licence - City of Regina.
- **Statistics Canada:** population estimates, components of population change and the 2021 Census of Population. Adapted from Statistics Canada, Tables 17-10-0155-01 and 17-10-0149-01 and the 2021 Census of Population. This does not constitute an endorsement by Statistics Canada of this product.
- **Canada Mortgage and Housing Corporation:** Rental Market Survey (rents and vacancy).

No company, applicant or owner names are published here. Names in the City's permit file are removed before anything is saved to this repository.

## Live map, and make it your own

* **Browse it:** https://franklinkinetics.github.io/regina-data-map/ (no download, works on a phone).
* **Save a copy:** the live map has a **Save a copy of this map** button (Explore tab, "Take it with you"). The saved file is the whole map in one page: open it in a browser, edit it in a text editor or with an AI assistant, host it anywhere. It keeps checking this site for newer data when it is online.
* **Fork it:** click **Fork** on GitHub to get your own copy of the whole pipeline (weekly data refresh, map build, your own live page). The code is MIT-licensed ([`LICENSE`](LICENSE)); the data keeps its own licences, so keep the attribution the map shows.

## Use the data yourself

* **Download files** (no sign-up, no code): `https://franklinkinetics.github.io/regina-data-map/data/` has `permits.csv`, `permits.geojson`, `rezonings.json`, `applications.json`, `context.json`, `tax-rates.csv` (City property tax rates by year since 2019) and a `data-dictionary.json`. Rebuilt every Friday.
* **Change the words on the map** (stories, facts, opening message) without a new download: see [`CONTENT-GUIDE.md`](CONTENT-GUIDE.md).
* **Property tax rates** come from the City's yearly Property Tax Bylaw, typed into `config/tax-rates.json`. Add the new year each spring (instructions at the end of the guide above).

## How the weekly refresh works

`.github/workflows/refresh.yml` runs these steps, and stops at the first one that fails, which leaves the last good version live:

1. `python -m scraper.run` downloads the data and runs the checks (counts and dollar totals must reconcile with the City's own files; no suspicious drops or swings; at least 80% of permits must match a City address point). The permit history is rebuilt in full each week from the City's yearly files, 2020 to today.
2. `python -m scripts.build_lab_map` builds the map file and `latest-v1.json`, the data file that downloaded maps look for.
3. A sanity check confirms the new data file looks right.
4. `python -m scripts.prune_state` removes applicant names and trims the saved state, which is then committed back here for next week's comparison (this is how rezonings are spotted).
5. The map, `latest-v1.json` and the download files in `data/` are published to GitHub Pages.

The same refresh also runs whenever `config/lab-content.json` (the words on the map) or the map's code changes.

To run it by hand: open the **Actions** tab, choose **Refresh Regina Data Map**, press **Run workflow**.

## Notes

- `latest-v1.json` is versioned. If the map's design changes in a way old copies can't read, new data goes to a new file name and old copies keep working with the last version they understand.
- Information, not advice; may contain errors. Not affiliated with the City of Regina.
