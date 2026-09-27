#!/usr/bin/env python3
"""Development real-IQ oracle-seed microbenchmark; explicitly noncausal."""

from __future__ import annotations

import hashlib
import json
import statistics
import sys
from contextlib import ExitStack
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DATASET = ROOT / "reports/2026_09_26_ds5_server_eval/dataset"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(HERE), str(DEPLOY), str(DEPLOY / "src")]

from known_state import NativeKnownState, build_library, sha256  # noqa: E402
from tools.presence_dwell import NativeDwell, unpack  # noqa: E402


def load_iq(case):
    path = (DATASET / case["raw_npy"]["path"]).resolve()
    expected = case["raw_npy"]["sha256"].removeprefix("sha256:")
    if not path.is_relative_to(DATASET) or sha256(path) != expected:
        raise ValueError("development IQ provenance mismatch")
    values = np.load(path, allow_pickle=False)
    if values.dtype != np.dtype("<i2") or values.shape != (
        case["rate_hz"] * 120 // 1000,
        2,
        2,
    ):
        raise ValueError("development IQ geometry mismatch")
    return values


def run(output: Path):
    manifest_path = DATASET / "cases.json"
    manifest = json.loads(manifest_path.read_text())
    cases = [
        case
        for case in manifest["cases"]
        if case["split"] == "dev" and case["rate_hz"] in (2_500_000, 5_000_000)
    ]
    library = build_library()
    rows = []
    with ExitStack() as stack:
        workspaces = {}
        for case in cases:
            rate, edge = case["rate_hz"], case["edge"]
            key = rate, edge
            if key not in workspaces:
                workspaces[key] = (
                    stack.enter_context(NativeDwell(library, rate, edge, 512)),
                    stack.enter_context(NativeKnownState(rate, edge, library)),
                )
            blind, known = workspaces[key]
            iq = load_iq(case)
            for rx in range(2):
                dwell = np.ascontiguousarray(iq[:, rx, :])
                baseline = unpack(blind.run(dwell, maximum=1, seeded=False))
                confirmation = baseline["confirmations"][0]
                positives = [
                    candidate
                    for candidate in confirmation["candidates"][
                        : confirmation["candidate_count"]
                    ]
                    if candidate["fractional_complete"] and candidate["margin"] > 0.025
                ]
                if not positives:
                    continue
                candidate = positives[0]
                window_index = baseline["rank"]["order"][0]
                window = rate // 50
                selected = np.ascontiguousarray(
                    dwell[window_index * window : (window_index + 1) * window]
                )
                predicted_epoch = candidate["epoch"] + candidate["fractional_offset_samples"]
                predicted_cfo = candidate["tracking_cfo_hz"]
                for _ in range(10):
                    known.measure(selected, predicted_epoch, predicted_cfo)
                measures = [
                    known.measure(selected, predicted_epoch, predicted_cfo) for _ in range(100)
                ]
                first = measures[0]
                if any(
                    (row["exact_score"], row["control_score"], row["tracking_cfo_hz"])
                    != (first["exact_score"], first["control_score"], first["tracking_cfo_hz"])
                    for row in measures[1:]
                ):
                    raise ValueError("known-state real-IQ output was not deterministic")
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "session_id": case["session_id"],
                        "visit_index": case["visit_index"],
                        "rate_hz": rate,
                        "edge": edge,
                        "rx": rx,
                        "window_index": window_index,
                        "seed_source": "same-visit-blind-result_oracle_noncausal",
                        "blind_candidate": candidate,
                        "known_state": first,
                        "median_total_cpu_ms": statistics.median(
                            row["total_cpu_ms"] for row in measures
                        ),
                        "median_total_wall_ms": statistics.median(
                            row["total_wall_ms"] for row in measures
                        ),
                    }
                )
    receipt = {
        "schema": "org.leo.research.known-state-real-oracle-microbenchmark/v1",
        "status": "same_visit_oracle_seed_microbenchmark_not_causal_tracking",
        "dataset_cases_sha256": sha256(manifest_path),
        "library_sha256": sha256(library),
        "script_sha256": sha256(Path(__file__)),
        "rows": rows,
        "summary": {
            "oracle_seeded_receiver_cases": len(rows),
            "strict_margin_passes": sum(row["known_state"]["margin"] > 0.025 for row in rows),
            "trusted_cfo_innovations": sum(
                row["known_state"]["cfo_innovation_within_8khz"] for row in rows
            ),
            "median_cpu_ms": statistics.median(row["median_total_cpu_ms"] for row in rows)
            if rows
            else None,
        },
        "limitations": [
            "seeds come from the same visit's completed blind result and are not prospective",
            "raw fast scoring omits blind-path tone conditioning and energy support selection",
            "real observations are unlabeled; blind positives are diagnostic references",
        ],
    }
    with output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(receipt["summary"], indent=2))


if __name__ == "__main__":
    run(HERE / "real_oracle_microbenchmark.json")
