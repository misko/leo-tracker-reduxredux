#!/usr/bin/env python3
"""Run the bounded DS13 activity-persistence diagnostic."""

from __future__ import annotations

import csv
import argparse
import hashlib
import json
import subprocess
import time
import os
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from activity_model import ModelConfig, assignment_probability, decode_lanes

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
import sys
sys.path.insert(0, str(HERE.parent))
from common import assignment_record, load_scan as load_common_scan
SCANS = ("scan-fw-911c4e5db9243281", "scan-fw-ffa1cc19d8d7c09f")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def summarize_path(groups, path):
    lane_changes = 0
    for lane in sorted({(g["receiver"], g["channel"]) for g in groups}):
        steps = [step for group, step in zip(groups, path)
                 if (group["receiver"], group["channel"]) == lane]
        lane_changes += sum(a["mask"] != b["mask"] for a, b in zip(steps, steps[1:]))
    return {
        "positive_groups": len(groups),
        "assigned_rows": int(sum(len(step["pairs"]) for step in path)),
        "groups_with_multiple_targets": int(sum(len(step["pairs"]) > 1 for step in path)),
        "activity_mask_changes": int(lane_changes),
        "active_target_group_counts": dict(sorted(Counter(
            target for step in path for target in range(groups[0]["scores"].shape[1])
            if step["mask"] & (1 << target)).items())),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rf_variant = os.environ.get("DS13_RF_VARIANT", "sealed-default")
    started = time.monotonic()
    base_cfg = ModelConfig()
    sigma_hz = 200.0
    clutter_density = 2 / (1 / 4.4e-6)
    output_rows = []
    control_rows = []
    scan_receipts = []
    source_files = []
    for label, scan in zip(("A", "B"), SCANS):
        data = load_common_scan(label)
        arrays = data["arrays"]
        detection_probability = data["detection_probability"]
        source_files.extend(Path(p) for p in data["provenance"])
        native_residual = data["native_residual_hz"]
        groups = [{**group, "scores": data["log_gain"][group["rows"]],
                   "visible": np.any(data["visible"][group["rows"]], axis=0)}
                  for group in data["groups"]]
        # Active-but-unassigned targets contribute their actual missed-detection
        # likelihood; edge gains are already relative to that baseline.
        cfg = replace(base_cfg, miss_score=float(np.log1p(-detection_probability)),
                      detection_probability=detection_probability)
        persistent = decode_lanes(groups, cfg, persistence=True)
        disabled = decode_lanes(groups, cfg, persistence=False)
        for group, step in zip(groups, persistent):
            for local_row, target in step["pairs"]:
                row = int(group["rows"][local_row])
                output_rows.append(assignment_record(data, row, target,
                    assignment_probability(group['scores'], local_row, target,
                                           cfg.miss_score, cfg.clutter_score)))
        for group, step in zip(groups, disabled):
            for local_row, target in step["pairs"]:
                row = int(group["rows"][local_row])
                control_rows.append(assignment_record(data, row, target,
                    assignment_probability(group['scores'], local_row, target,
                                           cfg.miss_score, cfg.clutter_score)))
        scan_receipts.append({
            "scan": label,
            "session": scan,
            "rows": int(len(arrays["times_s"])),
            "catalog_numbers": np.asarray(arrays["catalog_numbers"]).astype(int).tolist(),
            "detection_probability": detection_probability,
            "exact_alias_duplicate_rows_excluded": len(data["duplicate_rows"]),
            "persistent": summarize_path(groups, persistent),
            "persistence_disabled_control": summarize_path(groups, disabled),
            "path_mask_disagreement_groups": int(sum(a["mask"] != b["mask"] for a, b in zip(persistent, disabled))),
        })

    csv_path = output_dir / "assignments.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("scan", "row_index", "catalog_number",
            "receiver", "channel", "time_s", "residual_hz", "probability"))
        writer.writeheader()
        writer.writerows(output_rows)
    control_path = output_dir / "assignments-persistence-disabled.csv"
    with control_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("scan", "row_index", "catalog_number",
            "receiver", "channel", "time_s", "residual_hz", "probability"))
        writer.writeheader()
        writer.writerows(control_rows)
    test = subprocess.run(
        [str(REPO / ".venv/bin/python"), "-m", "unittest", "-v", "test_activity_model.py"],
        cwd=HERE, text=True, capture_output=True, check=False,
    )
    receipt = {
        "schema": "ds13-multitarget-activity-diagnostic/v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "rf_variant": rf_variant,
        "runtime_seconds": time.monotonic() - started,
        "settings": {**base_cfg.__dict__, "miss_score": "per scan log(1-pdet)",
                     "native_residual_sigma_hz": sigma_hz,
                     "clutter_density_per_hz": clutter_density,
                     "edge_bound_native_hz": 5 * sigma_hz,
                     "decoder": "per-RX/channel bounded factorial Viterbi beam; exact within-group matching",
                     "control": "same inputs/settings with elapsed-time persistence disabled"},
        "evidence": "Shared native baseline edge gain: logit(pdet) + log Normal(native-scaled frozen O-M residual; 0, 200 Hz) - log(2/(1/4.4e-6) Hz); edges beyond 5 sigma excluded. Archived posterior is not reused as independent evidence.",
        "scans": scan_receipts,
        "tests": {"returncode": test.returncode, "stdout": test.stdout, "stderr": test.stderr},
        "limitations": [
            "The archive is positive-only and has no complete opportunity ledger. Results are conditional on observed positive groups; absent rows are not misses.",
            "Residual Gaussian scale and uniform clutter width are heuristic, not calibrated native acquisition likelihoods. Assignment probability is a local logistic margin, not a calibrated posterior.",
            "The active-set-dependent positive-group normalizer is included using clutter rate 2 and scan-specific pdet. The reported assignment probability remains only a local logistic margin, not a calibrated FHMM posterior.",
            "The persistent Viterbi beam is bounded (48 paths and at most one activity-bit toggle between consecutive positive groups in each RX/channel lane). Within-group matching is exact. The disabled control optimizes every group independently.",
            "Orbit, timing, receiver, and RF nuisance predictions are frozen from the source archive. This is neither held-out validation nor localization validation.",
            ("This is the sealed/default frozen replay; matched fitted-c and zero-c fixed-position arms are exported separately."
             if rf_variant == "sealed-default" else
             f"This is the {rf_variant} matched fixed-position RF arm. It measures frequency-fit/activity effects only and cannot establish position accuracy."),
            "Peak assignment is exclusive within each source group: at most one satellite per row and at most one row per satellite. Multiple satellites may coexist in one group/lane.",
        ],
        "artifacts": {"assignments.csv": {"sha256": digest(csv_path), "rows": len(output_rows)},
                      "assignments-persistence-disabled.csv": {"sha256": digest(control_path), "rows": len(control_rows)}},
        "sources": {str(p.resolve()): digest(p) for p in sorted(set(source_files))},
    }
    receipt_path = output_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"receipt": str(receipt_path), "rows": len(output_rows),
                      "runtime_seconds": receipt["runtime_seconds"], "tests": test.returncode}))


if __name__ == "__main__":
    main()
