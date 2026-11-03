#!/usr/bin/env python3
"""Consolidate exact source/time/CFO duplicates without reference-track input."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


OBSERVATION_HEADER = [
    "candidate_id", "source_group_id", "receiver_id", "channel", "edge",
    "actual_rf_hz", "support_start_utc_ns", "support_center_utc_ns",
    "support_end_utc_ns", "measured_cfo_hz", "exact_score", "control_score",
    "margin",
]
MAP_HEADER = [
    "candidate_id", "source_group_id", "visit", "receiver_id", "probe_index",
    "candidate_rank", "epoch_kind", "detector_side",
]


def read(path: Path, expected: list[str]) -> list[list[str]]:
    with path.open(newline="", encoding="ascii") as source:
        rows = list(csv.reader(source, delimiter="\t"))
    if not rows or rows[0] != expected:
        raise ValueError(f"unsupported header: {path}")
    width = len(expected)
    if any(len(row) != width for row in rows[1:]):
        raise ValueError(f"malformed row: {path}")
    return rows[1:]


def weight(row: list[str]) -> float:
    control = float(row[11])
    margin = float(row[12])
    if not math.isfinite(control) or not math.isfinite(margin):
        raise ValueError("non-finite score")
    return min(max(margin, 0.0) / max(control, 0.02), 16.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--output-observations", type=Path, required=True)
    parser.add_argument("--output-source-map", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    for output in (args.output_observations, args.output_source_map, args.receipt):
        if output.exists():
            raise ValueError(f"refusing to overwrite {output}")

    observations = read(args.observations, OBSERVATION_HEADER)
    source_rows = read(args.source_map, MAP_HEADER)
    source_by_candidate = {row[0]: row for row in source_rows}
    if len(source_by_candidate) != len(source_rows):
        raise ValueError("duplicate source-map candidate")
    if set(source_by_candidate) != {row[0] for row in observations}:
        raise ValueError("source map and observation identities differ")

    best: dict[tuple[str, str, str], list[str]] = {}
    for row in observations:
        key = (row[1], row[7], row[9])
        previous = best.get(key)
        if previous is None or (-weight(row), row[0]) < (-weight(previous), previous[0]):
            best[key] = row
    selected = {row[0] for row in best.values()}
    filtered = [row for row in observations if row[0] in selected]
    filtered_map = [row for row in source_rows if row[0] in selected]

    for path, header, rows in (
        (args.output_observations, OBSERVATION_HEADER, filtered),
        (args.output_source_map, MAP_HEADER, filtered_map),
    ):
        with path.open("x", newline="", encoding="ascii") as target:
            writer = csv.writer(target, delimiter="\t", lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
    args.receipt.write_text(json.dumps({
        "schema": "leo-source-only-exact-duplicate-filter/v1",
        "key": ["source_group_id", "support_center_utc_ns", "measured_cfo_hz"],
        "selection": "maximum production evidence weight, then lexical candidate_id",
        "input_rows": len(observations),
        "output_rows": len(filtered),
        "removed_rows": len(observations) - len(filtered),
        "reference_tracks_used": False,
    }, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
