"""Tidy the saved state before it is committed back to the repo.

    python -m scripts.prune_state

- The permit history file (data/permit_history) has no applicant or owner names in it by construction.
- Small tables and the zoning layer keep just the newest two snapshots: the zoning one is the
  baseline the next run compares against to spot rezonings.
- Proposed-development snapshots are all kept (the rezoning tracer reads that archive).
- Roads are re-downloaded when needed, so they are not stored.
"""
import shutil
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
KEEP_TWO = ["zoning", "population", "rental_market", "migration"]


def main() -> int:
    shutil.rmtree(DATA / "permits", ignore_errors=True)  # the pipeline here never writes it; make sure no applicant names are ever kept
    for name in KEEP_TWO:
        for old in sorted((DATA / name / "snapshots").glob("*.geojson"))[:-2]:
            old.unlink()
    shutil.rmtree(DATA / "roads", ignore_errors=True)
    print("state pruned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
