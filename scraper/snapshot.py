"""Diff a new GeoJSON pull against the last snapshot and write history.

Snapshots are plain files committed to git — the commit history on data/
is the change log. latest.geojson (what the map reads) is only overwritten
after the caller's verification has passed.
"""
import json
from datetime import date
from pathlib import Path
from typing import Callable


class DiffResult:
    def __init__(self, added: list, changed: list, removed: list, total: int):
        self.added = added
        self.changed = changed
        self.removed = removed
        self.total = total

    def summary(self) -> str:
        return (
            f"total={self.total} added={len(self.added)} "
            f"changed={len(self.changed)} removed={len(self.removed)}"
        )


def load_latest(dir_path: Path) -> dict | None:
    latest_path = dir_path / "latest.geojson"
    if not latest_path.exists():
        return None
    return json.loads(latest_path.read_text(encoding="utf-8"))


def diff_features(
    previous_fc: dict | None,
    new_fc: dict,
    key_fn: Callable[[dict], str],
    ignore_fields: frozenset = frozenset(),
) -> DiffResult:
    """`ignore_fields` are bookkeeping properties that change without the
    underlying fact changing (e.g. the zoning layer's UPDATE_DATE, which was
    found to tick ~4 parcels/day regardless of any real rezoning)."""
    old_by_key = {key_fn(f): f for f in (previous_fc["features"] if previous_fc else [])}
    new_by_key = {key_fn(f): f for f in new_fc["features"]}

    added = [k for k in new_by_key if k not in old_by_key]
    removed = [k for k in old_by_key if k not in new_by_key]
    def material(feature: dict) -> dict:
        return {k: v for k, v in feature["properties"].items() if k not in ignore_fields}

    changed = [
        k
        for k in new_by_key
        if k in old_by_key and material(new_by_key[k]) != material(old_by_key[k])
    ]

    return DiffResult(added, changed, removed, total=len(new_by_key))


def write_snapshot(dir_path: Path, new_fc: dict) -> None:
    snapshots_dir = dir_path / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    dated_path = snapshots_dir / f"{date.today().isoformat()}.geojson"
    dated_path.write_text(json.dumps(new_fc, indent=2), encoding="utf-8")

    latest_path = dir_path / "latest.geojson"
    latest_path.write_text(json.dumps(new_fc, indent=2), encoding="utf-8")
