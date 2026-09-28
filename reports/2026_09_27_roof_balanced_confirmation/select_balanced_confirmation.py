"""Freeze/cache a second disjoint roof cohort through the existing public selector."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
FIRST = HERE.parent / "2026_09_27_roof_geometry_confirmation"
DIRECTION = HERE.parent / "2026_09_27_roof_direction_subset"
sys.path.insert(0, str(FIRST))
import select_confirmation as prior
_SELECT_EARLIEST_READY = prior.select_earliest_ready


METADATA_CUTOFF_UTC_NS = 1790489303000000000


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def combined_development() -> dict:
    original_path = DIRECTION / "evaluation_manifest.json"
    first_path = FIRST / "manifest.json"
    original_bytes = original_path.read_bytes()
    first_bytes = first_path.read_bytes()
    original = json.loads(original_bytes)
    first = json.loads(first_bytes)
    sessions = original["sessions"] + first["sessions"]
    ids = [item["pose"]["session_id"] for item in sessions]
    if len(ids) != 14 or len(set(ids)) != 14:
        raise ValueError("combined exclusion cohort must contain 14 unique sessions")
    return {
        "sessions": sessions,
        "selection": "Combined original ten development and first four confirmation sessions; exclusion provenance only.",
        "source_manifest_sha256": {
            str(original_path): digest(original_bytes),
            str(first_path): digest(first_bytes),
        },
    }


def select_after_combined(rows: list[dict], combined: dict, cutoff_utc_ns: int,
                          count: int = 4):
    ids = {item["pose"]["session_id"] for item in combined["sessions"]}
    after = max(item["pose"]["capture_start_earliest_utc_ns"]
                for item in combined["sessions"])
    selected, accounting = _SELECT_EARLIEST_READY(
        rows, ids, after, cutoff_utc_ns, count=count)
    if any(row["session_id"] in ids or row["capture_start_utc_ns"] <= after
           for row in selected):
        raise ValueError("selector returned a non-disjoint or non-later session")
    return selected, accounting


def configure_prior() -> None:
    prior.HERE = HERE
    prior.DEVELOPMENT_MANIFEST = HERE / "combined_development_manifest.json"
    prior.METADATA_CUTOFF_UTC_NS = METADATA_CUTOFF_UTC_NS


def freeze() -> None:
    combined_path = HERE / "combined_development_manifest.json"
    if combined_path.exists() or (HERE / "manifest.json").exists():
        raise FileExistsError("balanced confirmation freeze artifacts already exist")
    combined = combined_development()
    # Verify the wrapper policy itself before delegating public readiness checks.
    original_selector = prior.select_earliest_ready
    prior.select_earliest_ready = lambda rows, ids, after, cutoff, count=4: select_after_combined(
        rows, combined, cutoff, count)
    combined_path.write_text(json.dumps(combined, indent=2, allow_nan=False) + "\n")
    configure_prior()
    try:
        prior.freeze(METADATA_CUTOFF_UTC_NS)
    finally:
        prior.select_earliest_ready = original_selector


def cache() -> None:
    configure_prior()
    prior.cache_inputs()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "cache"))
    arguments = parser.parse_args()
    freeze() if arguments.action == "freeze" else cache()
