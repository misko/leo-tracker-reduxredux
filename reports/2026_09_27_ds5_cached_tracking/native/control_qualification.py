#!/usr/bin/env python3
"""Constructed-control check for full and partial known-state score semantics."""

from __future__ import annotations

import json
import sys
from contextlib import ExitStack
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DATASET = ROOT / "reports/2026_09_26_ds5_server_eval/dataset"
sys.path.insert(0, str(HERE))

from known_state import sha256  # noqa: E402
from known_state_v2 import NativeKnownStateV2, build_library_v2  # noqa: E402


def challenge_state(case, receiver):
    truth = case["truth"]
    spec = truth["receivers"][receiver]
    if truth["starlink_model_present"]:
        return (
            spec["window"],
            spec["epoch_samples"] + spec["fractional_delay_samples"],
            spec["cfo_hz"],
        )
    seed = spec["seed"]
    cfo = spec.get("carrier_hz")
    if cfo is None:
        cfo = (seed * 137) % 800_001 - 400_000
    return seed % 6, (seed * 0.731) % (case["rate_hz"] / 750.0), cfo


def run(output: Path):
    manifest_path = DATASET / "cases.json"
    cases = [
        case
        for case in json.loads(manifest_path.read_text())["cases"]
        if case["split"] == "control" and case["rate_hz"] in (2_500_000, 5_000_000)
    ]
    library = build_library_v2()
    rows = []
    with ExitStack() as stack:
        workspaces = {}
        for case in cases:
            key = case["rate_hz"], case["edge"]
            if key not in workspaces:
                workspaces[key] = stack.enter_context(NativeKnownStateV2(*key, library))
            path = (DATASET / case["raw_npy"]["path"]).resolve()
            if sha256(path) != case["raw_npy"]["sha256"].removeprefix("sha256:"):
                raise ValueError("control IQ provenance mismatch")
            iq = np.load(path, allow_pickle=False)
            for rx in range(2):
                window, epoch, cfo = challenge_state(case, rx)
                count = case["rate_hz"] // 50
                selected = iq[window * count : (window + 1) * count, rx, :]
                variants = {
                    str(frame_limit): workspaces[key].measure(
                        selected, epoch, cfo, frame_limit=frame_limit
                    )
                    for frame_limit in (16, 4, 2)
                }
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "kind": case["truth"]["kind"],
                        "model_present": case["truth"]["starlink_model_present"],
                        "rate_hz": case["rate_hz"],
                        "edge": case["edge"],
                        "rx": rx,
                        "challenge_window": window,
                        "challenge_epoch_samples": epoch,
                        "challenge_cfo_hz": cfo,
                        "variants": variants,
                    }
                )
    summary = {}
    for frame_limit in (16, 4, 2):
        label = str(frame_limit)
        summary[label] = {}
        for kind in ("pilot", "noise", "tone"):
            subset = [row for row in rows if row["kind"] == kind]
            summary[label][kind] = {
                "receiver_cases": len(subset),
                "strict_trusted_gates": sum(
                    row["variants"][label]["margin"] > 0.025
                    and row["variants"][label]["cfo_innovation_within_8khz"]
                    and not row["variants"][label]["needs_reacquire"]
                    for row in subset
                ),
            }
    receipt = {
        "schema": "org.leo.research.known-state-v2-controls/v1",
        "status": "constructed_controls_not_calibrated_classifier_rates",
        "dataset_cases_sha256": sha256(manifest_path),
        "library_sha256": sha256(library),
        "source_sha256": sha256(Path(__file__)),
        "rows": rows,
        "summary": summary,
        "negative_challenge": "one deterministic stale-state-like window/timing/CFO per receiver",
    }
    with output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run(HERE / "control_qualification.json")
