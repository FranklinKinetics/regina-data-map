# Regina Data Map

A free interactive map of building permits, zoning and neighbourhood numbers for Regina, Saskatchewan. Made by Franklin Kinetics (franklinkinetics.com).

This repository keeps the map's data fresh. Every Friday morning it downloads the latest government data, checks it, rebuilds the map and publishes it on GitHub Pages. Copies of the map that people have downloaded ask this page for newer data when they are opened online, and use the data inside the file when they are not.

## What is on the map

Government open data only:

- **City of Regina open data:** building permits, zoning, streets, addresses, proposed development notices. Contains information licensed under the Open Government Licence - City of Regina.
- **Statistics Canada:** population estimates, components of population change and the 2021 Census of Population. Adapted from Statistics Canada, Tables 17-10-0155-01 and 17-10-0149-01 and the 2021 Census of Population. This does not constitute an endorsement by Statistics Canada of this product.
- **Canada Mortgage and Housing Corporation:** Rental Market Survey (rents and vacancy).

No company, applicant or owner names are published here. Names in the City's permit file are removed before anything is saved to this repository.

## How the weekly refresh works

`.github/workflows/refresh.yml` runs these steps, and stops at the first one that fails, which leaves the last good version live:

1. `python -m scraper.run` downloads the data and runs the checks (counts and dollar totals must reconcile with the City's own files; no suspicious drops or swings).
2. `python -m scripts.build_lab_map` builds the map file and `latest-v1.json`, the data file that downloaded maps look for.
3. A sanity check confirms the new data file looks right.
4. `python -m scripts.prune_state` removes applicant names and trims the saved state, which is then committed back here for next week's comparison (this is how rezonings are spotted).
5. The map and `latest-v1.json` are published to GitHub Pages.

To run it by hand: open the **Actions** tab, choose **Refresh Regina Data Map**, press **Run workflow**.

## Notes

- `latest-v1.json` is versioned. If the map's design changes in a way old copies can't read, new data goes to a new file name and old copies keep working with the last version they understand.
- Information, not advice; may contain errors. Not affiliated with the City of Regina.
