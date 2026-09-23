#!/usr/bin/env python3
"""Inventory causal orbit-phase history for recent blind catalogues.

This is a truth-free coverage audit.  It applies the already frozen causal
rate predictor to every member of each supplied causal catalogue and records
explicit zero-phase fallbacks where the required predecessor is unavailable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records, parse_element_sets

NS_HOUR = 3_600_000_000_000


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def tle_key(text: str) -> tuple[str, ...]:
    return tuple(
        line.strip() for line in text.splitlines() if line.strip().startswith(("1 ", "2 "))
    )


def sequence_before(records: list[dict], cutoff_ns: int) -> list[dict]:
    eligible = [
        row
        for row in records
        if row["epoch_utc_ns"] < cutoff_ns and row["first_collected_utc_ns"] < cutoff_ns
    ]
    by_epoch: dict[int, dict] = {}
    for row in eligible:
        previous = by_epoch.get(row["epoch_utc_ns"])
        if previous is None or row["first_collected_utc_ns"] > previous["first_collected_utc_ns"]:
            by_epoch[row["epoch_utc_ns"]] = row
    return [by_epoch[key] for key in sorted(by_epoch)]


def history_support(records: list[dict], current_text: str, cutoff_ns: int) -> dict:
    # Match the target-phase generator: an element remains causally available
    # after collection even when a later same-epoch revision also exists.
    sequence = [
        row
        for row in records
        if row["epoch_utc_ns"] < cutoff_ns and row["first_collected_utc_ns"] < cutoff_ns
    ]
    current_key = tle_key(current_text)
    current = next((row for row in sequence if tle_key(row["text"]) == current_key), None)
    if current is None:
        return {"status": "current-causal-element-absent", "predicted_phase_fallback_s": 0.0}
    prior = [row for row in sequence if row["epoch_utc_ns"] < current["epoch_utc_ns"]]
    if not prior:
        return {"status": "no-predecessor", "predicted_phase_fallback_s": 0.0}
    previous = max(prior, key=lambda row: (row["epoch_utc_ns"], row["first_collected_utc_ns"]))
    gap_h = (current["epoch_utc_ns"] - previous["epoch_utc_ns"]) / NS_HOUR
    if not 1 <= gap_h <= 72:
        return {
            "status": "predecessor-gap-outside-1-to-72-hours",
            "gap_h": gap_h,
            "predicted_phase_fallback_s": 0.0,
        }
    return {
        "status": "supported",
        "gap_h": gap_h,
        "previous_epoch_utc_ns": previous["epoch_utc_ns"],
        "previous_first_collected_utc_ns": previous["first_collected_utc_ns"],
        "current_epoch_utc_ns": current["epoch_utc_ns"],
        "current_first_collected_utc_ns": current["first_collected_utc_ns"],
    }


def load_histories(reader: TleArchiveReader, wanted: set[int], last_capture_ns: int):
    histories: dict[int, dict[str, dict]] = defaultdict(dict)
    snapshots = [s for s in reader.list_snapshots() if s.collected_utc_ns < last_capture_ns]
    for snapshot in snapshots:
        for record in parse_element_set_records(reader.read(snapshot)):
            if record.satellite_number not in wanted:
                continue
            prior = histories[record.satellite_number].get(record.text)
            if prior is None or snapshot.collected_utc_ns < prior["first_collected_utc_ns"]:
                catalogue = parse_element_sets(record.text)
                histories[record.satellite_number][record.text] = {
                    "text": record.text,
                    "epoch_utc_ns": int(catalogue.element_epoch_utc_ns()[0]),
                    "first_collected_utc_ns": snapshot.collected_utc_ns,
                    "snapshot_digest": snapshot.digest,
                }
    return {key: list(value.values()) for key, value in histories.items()}, snapshots


def canonical_digest(value: dict) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
    )


def validate_prior(prior: dict, first_capture_ns: int) -> dict:
    """Reject a learned prior that could contain target-session information."""
    frozen = prior["frozen_model"]
    if int(frozen["training_cutoff_utc_ns"]) >= first_capture_ns:
        raise ValueError("orbit prior training cutoff must precede every capture")
    winner = frozen["winner"]
    sigma = float(winner["validation_rms_rate_error_s_h"])
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError("orbit rate prior sigma must be finite and positive")
    return winner


def run(evidence: Path, archive: Path, prior_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(output)
    inventory_path = evidence / "inventory.json"
    inventory = json.loads(inventory_path.read_text())
    if inventory.get("known_position_used") or inventory.get("prior_matched_norads_used"):
        raise ValueError("truth-free blind evidence inventory required")
    sessions = []
    wanted: set[int] = set()
    for item in inventory["scans"]:
        path = evidence / "evidence" / f"{item['session_id']}.json"
        document = json.loads(path.read_text())
        authority = document["inventory"]
        tle_path = path.parent / authority["tle_file"]
        if (
            Path(authority["tle_file"]).name != authority["tle_file"]
            or digest(tle_path) != authority["tle_digest"]
        ):
            raise ValueError("catalogue authority mismatch")
        records = parse_element_set_records(tle_path.read_text())
        by_norad = {row.satellite_number: row.text for row in records}
        if len(by_norad) != len(records):
            raise ValueError("catalogue contains duplicate NORAD")
        wanted.update(by_norad)
        sessions.append((item, path, tle_path, by_norad))
    prior = json.loads(prior_path.read_text())
    winner = validate_prior(prior, min(int(item["reference_utc_ns"]) for item, *_ in sessions))
    last_capture = max(int(item["reference_utc_ns"]) for item, *_ in sessions)
    histories, snapshots = load_histories(TleArchiveReader(archive), wanted, last_capture)
    counts: dict[str, int] = defaultdict(int)
    rows = []
    for item, path, tle_path, catalogue in sessions:
        status_rows = []
        for norad, text in sorted(catalogue.items()):
            support = history_support(histories.get(norad, []), text, int(item["reference_utc_ns"]))
            counts[support["status"]] += 1
            status_rows.append({"norad": norad, **support})
        rows.append(
            {
                "session_id": item["session_id"],
                "reference_utc_ns": item["reference_utc_ns"],
                "evidence_digest": digest(path),
                "catalogue_digest": digest(tle_path),
                "catalogue_size": len(catalogue),
                "status_counts": {
                    key: sum(row["status"] == key for row in status_rows)
                    for key in sorted({row["status"] for row in status_rows})
                },
                "candidates": status_rows,
            }
        )
    result = {
        "schema": "recent-full-catalogue-causal-phase-history-audit/v1",
        "truth_accessed": False,
        "inference_performed": False,
        "phase_state_audit_performed": False,
        "fallback_policy": "zero predicted phase for unsupported candidate history",
        "prior": {
            "source": str(prior_path),
            "digest": digest(prior_path),
            "training_cutoff_utc_ns": prior["frozen_model"]["training_cutoff_utc_ns"],
            "winner": winner,
            "unchanged_rate_prior_sigma_s_h": winner["validation_rms_rate_error_s_h"],
        },
        "authority": {
            "evidence_inventory": str(inventory_path),
            "evidence_inventory_digest": digest(inventory_path),
            "tle_archive_root": str(archive),
            "archive_snapshot_count_before_last_capture": len(snapshots),
            "archive_first_collected_utc_ns": snapshots[0].collected_utc_ns,
            "archive_last_collected_utc_ns": snapshots[-1].collected_utc_ns,
        },
        "candidate_occurrence_counts": dict(sorted(counts.items())),
        "unique_catalogue_norad_count": len(wanted),
        "sessions": rows,
    }
    result["content_digest"] = canonical_digest(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--tle-archive", type=Path, required=True)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.evidence, args.tle_archive, args.prior, args.output)


if __name__ == "__main__":
    main()
