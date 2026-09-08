#!/usr/bin/env python3
"""Separate within-probe agreement, temporal sampling loss, and unresolved RF flags."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from tools.evaluate_native_presence_budgets import associated
from tools.freeze_native_presence_holdout import selection
from tools.qualify_native_presence import digest, write_json


def validate_one(probe, row, policy):
    actual = row["result"]
    if (
        row["provenance"] != probe["provenance"]
        or row["probe"] != probe["file"]
        or actual["device_counter"] != probe["device_counter"]
        or actual["rate_hz"] != probe["rate_hz"]
        or actual["edge"] != int(probe["edge"] == "upper")
        or actual["format"] != 2
    ):
        raise ValueError("holdout identity mismatch")
    positive = [c for c in probe["oracle_candidates"] if c["margin"] >= 0.025]
    detected = [
        c for c in actual["candidates"] if c["fractional_complete"] and c["margin"] >= 0.025
    ]
    matched = any(associated(a, b, probe["rate_hz"], policy) for a in detected for b in positive)
    if (
        row["reference_positive"] != bool(positive)
        or row["detected"] != bool(detected)
        or row["matched_reference"] != matched
    ):
        raise ValueError("holdout accounting disagrees with candidate evidence")


def metrics(rows):
    rates = {}
    for rate in (2500000, 5000000):
        selected = [r for r in rows if r["result"]["rate_hz"] == rate]

        def counts(values):
            positive = [r for r in values if r["reference_positive"]]
            return {
                "probes": len(values),
                "reference_positive": len(positive),
                "reference_positive_detected": sum(r["detected"] for r in positive),
                "reference_associated": sum(r["matched_reference"] for r in positive),
                "unresolved_additional_flags": sum(
                    r["detected"] and not r["reference_positive"] for r in values
                ),
            }

        groups = defaultdict(list)
        for r in selected:
            groups[(r["provenance"]["session_id"], r["provenance"]["visit"])].append(r)
        positive_visits = [
            group for group in groups.values() if any(r["reference_positive"] for r in group)
        ]
        schedules = []
        for offsets in ([0], [0, 40, 100], list(range(0, 120, 20))):
            windows = [
                [r for r in group if r["provenance"]["probe_offset_ms"] in offsets]
                for group in positive_visits
            ]
            schedules.append(
                {
                    "offsets_ms": offsets,
                    "reference_positive_visits_anywhere": len(positive_visits),
                    "reference_seen_at_scheduled_windows": sum(
                        any(r["reference_positive"] for r in w) for w in windows
                    ),
                    "native_reference_associated_at_scheduled_windows": sum(
                        any(r["matched_reference"] for r in w) for w in windows
                    ),
                    "native_flag_at_scheduled_windows_including_unresolved": sum(
                        any(r["detected"] for r in w) for w in windows
                    ),
                }
            )
        rates[str(rate)] = {
            "first_window": counts(
                [r for r in selected if r["provenance"]["probe_offset_ms"] == 0]
            ),
            "all_windows": counts(selected),
            "temporal_schedules": schedules,
            "sessions": {
                s: counts([r for r in selected if r["provenance"]["session_id"] == s])
                for s in sorted({r["provenance"]["session_id"] for r in selected})
            },
        }
    return rates


def summarize(directory: Path, output: Path):
    if any(output.resolve().is_relative_to(Path(p)) for p in ("/mnt/qnap01", "/srv/bulk/leo")):
        raise ValueError("summary output cannot be beneath archive storage")
    frozen = json.loads((directory / "freeze.json").read_text())
    inputs = json.loads((directory / "inputs.json").read_text())
    rows = json.loads((directory / "results.json").read_text())
    protocol = frozen["protocol"]
    expected = {
        (s["session_id"], v, o)
        for s in protocol["sessions"]
        for v in selection(protocol)
        for o in protocol["probe_offsets_ms"]
    }
    keys = [
        (
            p["provenance"]["session_id"],
            p["provenance"]["visit"],
            p["provenance"]["probe_offset_ms"],
        )
        for p in inputs
    ]
    if len(keys) != len(expected) or set(keys) != expected or len(rows) != len(inputs):
        raise ValueError("incomplete or duplicate holdout inventory")
    lookup = {p["file"]: p for p in inputs}
    if len(lookup) != len(inputs) or len({r["probe"] for r in rows}) != len(rows):
        raise ValueError("duplicate holdout filenames")
    # This is the frozen detector's association policy, not a fitted tolerance.
    policy = {"maximum_cfo_difference_hz": 8000, "maximum_circular_epoch_difference_us": 2}
    for row in rows:
        validate_one(lookup[row["probe"]], row, policy)
    write_json(
        output,
        {
            "schema": "org.leo.research.arm-presence-holdout-summary/v1",
            "inputs_sha256": digest(directory / "inputs.json"),
            "results_sha256": digest(directory / "results.json"),
            "freeze_sha256": digest(directory / "freeze.json"),
            "rates": metrics(rows),
            "misses": [r["probe"] for r in rows if r["reference_positive"] and not r["detected"]],
            "different_cfo_or_timing": [
                r["probe"]
                for r in rows
                if r["reference_positive"] and r["detected"] and not r["matched_reference"]
            ],
            "limitations": (
                "Four held-out scans, not independent Starlink truth. Six non-overlapping windows "
                "tile selected visits; this is not continuous detection. Additional RF flags "
                "remain unresolved, not false-alarm labels."
            ),
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    summarize(args.directory, args.output)


if __name__ == "__main__":
    main()
