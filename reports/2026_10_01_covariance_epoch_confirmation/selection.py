"""Freeze a disjoint, chronology-only confirmation panel from authority manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = ROOT / "reports/2026_09_30_sacramento_model_comparison/selection.json"
AUTHORITIES = {
    "DS9": ROOT / "reports/2026_09_28_ds9_post_ds8/manifest.json",
    "DS10": ROOT / "reports/2026_09_29_ds10_post_ds9/local/manifest.json",
    "DS11": ROOT / "reports/2026_09_30_ds11_post_ds10/local/manifest.json",
}
COUNTS = {"DS9": 11, "DS10": 11, "DS11": 10}
REQUIRED = {
    "session_id",
    "manifest_sha256",
    "capture_start_utc_ns",
    "capture_end_utc_ns",
    "utc_qualified",
    "exclusion_reasons",
}


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def interval(row: dict[str, Any]) -> tuple[int, int]:
    start = int(row.get("capture_start_earliest_utc_ns", row["capture_start_utc_ns"]))
    end = int(row["capture_end_utc_ns"])
    if end < start:
        raise ValueError(f"negative capture interval for {row['session_id']}")
    return start, end


def overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return max(left[0], right[0]) <= min(left[1], right[1])


def quantile_indices(size: int, count: int) -> list[int]:
    if count < 2 or size < count:
        raise ValueError(f"cannot select {count} chronological quantiles from {size} rows")
    indices = [index * (size - 1) // (count - 1) for index in range(count)]
    if len(set(indices)) != count:
        raise AssertionError("quantile selection is not unique")
    return indices


def build() -> dict[str, Any]:
    prior = json.loads(PRIOR.read_text())
    result: dict[str, Any] = {
        "schema": "covariance-epoch-confirmation-panel/v1",
        "counts": COUNTS,
        "selection_policy": (
            "For each dataset, validate complete authority-manifest rows, exclude every "
            "capture whose closed recording interval overlaps the prior panel, sort the "
            "remaining rows by capture start and session ID, and take fixed floor-indexed "
            "temporal quantiles. No signal, fit, optimizer, or geographic outcome is read."
        ),
        "retrospective_exposure": {
            "status": "known_after_exploratory_panel",
            "statement": (
                "The M2 and M4 choice followed review of the 2026-09-30 panel. This is a "
                "disjoint historical-corpus confirmation cohort, not a prospective study; "
                "cohort membership uses only authority metadata and prior recording intervals."
            ),
            "prior_selection_path": str(PRIOR),
            "prior_selection_sha256": digest(PRIOR),
        },
        "authorities": {},
        "eligibility": {},
        "selected": {},
    }
    all_selected_intervals: list[tuple[str, tuple[int, int]]] = []
    for dataset, authority_path in AUTHORITIES.items():
        captures = json.loads(authority_path.read_text())["captures"]
        prior_rows = prior["selected"][dataset]
        prior_ids = {row["session_id"] for row in prior_rows}
        prior_intervals = [(row["session_id"], interval(row)) for row in prior_rows]
        eligible: list[tuple[int, dict[str, Any]]] = []
        excluded_prior_ids: list[str] = []
        excluded_overlap_ids: list[str] = []
        seen: set[str] = set()
        for authority_index, row in enumerate(captures):
            missing = REQUIRED - row.keys()
            if missing:
                raise ValueError(f"{dataset} authority row {authority_index} lacks {sorted(missing)}")
            session_id = row["session_id"]
            if session_id in seen:
                raise ValueError(f"duplicate authority session {session_id}")
            seen.add(session_id)
            if row["utc_qualified"] is not True or row["exclusion_reasons"] != []:
                raise ValueError(f"authority contains ineligible capture {session_id}")
            recording_interval = interval(row)
            overlap_ids = [old_id for old_id, old_interval in prior_intervals
                           if overlaps(recording_interval, old_interval)]
            if session_id in prior_ids:
                excluded_prior_ids.append(session_id)
            if overlap_ids:
                excluded_overlap_ids.append(session_id)
                continue
            eligible.append((authority_index, row))
        eligible.sort(key=lambda item: (int(item[1]["capture_start_utc_ns"]), item[1]["session_id"]))
        chosen = []
        for eligible_index in quantile_indices(len(eligible), COUNTS[dataset]):
            authority_index, row = eligible[eligible_index]
            chosen_row = row | {
                "authority_index": authority_index,
                "eligible_index": eligible_index,
                "unit_id": f"{dataset}-F{authority_index + 1:03d}",
            }
            chosen.append(chosen_row)
            all_selected_intervals.append((chosen_row["unit_id"], interval(chosen_row)))
        result["authorities"][dataset] = {
            "path": str(authority_path),
            "sha256": digest(authority_path),
            "capture_count": len(captures),
        }
        result["eligibility"][dataset] = {
            "authority_count": len(captures),
            "prior_panel_session_count": len(prior_ids),
            "excluded_prior_session_ids": sorted(excluded_prior_ids),
            "excluded_interval_overlap_count": len(excluded_overlap_ids),
            "excluded_interval_overlap_session_ids": sorted(excluded_overlap_ids),
            "eligible_complete_nonoverlapping_count": len(eligible),
            "selected_count": len(chosen),
        }
        result["selected"][dataset] = chosen
    prior_all = [(row["session_id"], interval(row))
                 for rows in prior["selected"].values() for row in rows]
    for unit_id, selected_interval in all_selected_intervals:
        collisions = [session_id for session_id, prior_interval in prior_all
                      if overlaps(selected_interval, prior_interval)]
        if collisions:
            raise AssertionError(f"{unit_id} overlaps prior recordings {collisions}")
    return result


def main() -> None:
    output = HERE / "selection.json"
    with output.open("x") as stream:
        json.dump(build(), stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
