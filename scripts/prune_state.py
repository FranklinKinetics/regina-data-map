"""Tidy the saved state before it is committed back to the repo.

    python -m scripts.prune_state

- Permit applicant names never leave the runner: they are removed from the saved permit file.
- Old permit snapshots are deleted (only the latest is kept, for the drop check).
- Small tables and the zoning layer keep just the newest two snapshots: the zoning one is the
  baseline the next run compares against to spot rezonings.
- Proposed-development snapshots are all kept (the rezoning tracer reads that archive).
- Roads are re-downloaded when needed, so they are not stored.
"""
import json
import shutil
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
KEEP_TWO = ["zoning", "population", "rental_market", "migration"]


def main() -> int:
    permits = DATA / "permits" / "latest.geojson"
    fc = json.loads(permits.read_text(encoding="utf-8"))
    for f in fc["features"]:
        f["properties"].pop("Applicant", None)
        f["properties"].pop("Applicant Type", None)
    permits.write_text(json.dumps(fc), encoding="utf-8")
    shutil.rmtree(DATA / "permits" / "snapshots", ignore_errors=True)
    for name in KEEP_TWO:
        for old in sorted((DATA / name / "snapshots").glob("*.geojson"))[:-2]:
            old.unlink()
    shutil.rmtree(DATA / "roads", ignore_errors=True)
    left = sum(1 for f in fc["features"] if "Applicant" in f["properties"])
    if left:
        print(f"applicant names still present on {left} permits", file=sys.stderr)
        return 1
    print("state pruned; applicant names removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
