#!/usr/bin/env python3
"""Normalize the sealed historical DS1 timing arms without refitting them."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path):
    seal = path.with_suffix(".sha256")
    if not seal.exists() or seal.read_text().strip().split()[0] != digest(path).split(":", 1)[1]:
        raise ValueError(f"missing or invalid seal: {path}")
    return json.loads(path.read_text())


def row(arm, partition, group, provenance, model=None):
    failed = arm.get("failure")
    return {
        "schema": "ds1-timing-ablation-row/v1",
        "partition": partition,
        "group_id": group,
        "scan_count": arm.get("scan_count", arm.get("view_scan_count")),
        "prior": arm.get("prior"),
        "model": model or arm.get("model", "regularized_global_plus_scan_epoch"),
        "scale_s": arm.get("scale_s"),
        "status": "input_failure" if failed else "completed",
        "global_tau_s": arm.get("global_tau_s"),
        "training_capped_rms_hz": arm.get("training_capped800_rmse_hz"),
        "training_uncapped_rms_hz": arm.get("training_uncapped_rmse_hz"),
        "penalized_objective_rms_hz": arm.get("penalized_objective_rmse_hz"),
        "latitude_deg": arm.get("latitude_deg"),
        "longitude_deg": arm.get("longitude_deg"),
        "track_count": arm.get("track_count"),
        "tau_boundary_count": arm.get("tau_boundary_count"),
        "visibility_failure_count": arm.get("visibility_failure_count"),
        "stopping_rule_satisfied": arm.get("stopping_rule_satisfied"),
        "fixed_identity": True,
        "held_used_for_fit": False,
        "truth_used_for_fit": False,
        "failure_session_id": arm.get("failed_session_id"),
        "failure_summary": ("counter-continuity authority unavailable" if failed else None),
        "provenance": provenance,
    }


def attach_evaluation(item, evaluated):
    """Attach only post-seal fields; inference bindings remain independently bound."""
    item["post_seal_held_capped_rms_hz"] = evaluated.get(
        "held_capped_rms_hz", evaluated.get("reserved_capped800_rmse_hz")
    )
    item["post_seal_held_uncapped_rms_hz"] = evaluated.get(
        "held_uncapped_rms_hz", evaluated.get("reserved_uncapped_rmse_hz")
    )
    item["post_seal_reference_error_km"] = evaluated.get("reference_error_km")
    item["post_seal_evaluation_attached"] = True
    return item


def main():
    dataset = json.loads((ROOT / "reports/2026_09_24_ds1/dataset.json").read_text())
    case_index = {(x["partition"], x["group_id"], x["scan_count"]): x for x in dataset["cases"]}
    sources = {
        "first_train_global": ROOT
        / "reports/2026_09_23_long_global_epoch_position/results/inference.json",
        "first_train_global_evaluation": ROOT
        / "reports/2026_09_23_long_global_epoch_position/results/results.json",
        "first_train_scan": ROOT
        / "reports/2026_09_23_long_full8h_shared_epoch_position/results/inference.json",
        "first_train_scan_evaluation": ROOT
        / "reports/2026_09_23_long_full8h_shared_epoch_position/results/results.json",
        "second_train": ROOT
        / "reports/2026_09_23_second_train_epoch_replication/results/results.json",
        "validation": ROOT / "reports/2026_09_23_frozen_validation/timing/inference.json",
        "validation_evaluation": ROOT / "reports/2026_09_23_frozen_validation/results.json",
        "test": ROOT / "reports/2026_09_23_final_test_global_epoch/timing/inference.json",
        "test_evaluation": ROOT / "reports/2026_09_23_final_test_global_epoch/results.json",
    }
    payloads = {name: sealed(path) for name, path in sources.items()}
    rows = []
    for inferred, evaluated in zip(
        payloads["first_train_global"]["arms"],
        payloads["first_train_global_evaluation"]["arms"],
        strict=True,
    ):
        rows.append(
            attach_evaluation(
                row(
                    inferred,
                    "train",
                    "20260921_00",
                    "first_train_global",
                    "fixed_identity_shared_global_tau",
                ),
                evaluated,
            )
        )
    for inferred, evaluated in zip(
        payloads["first_train_scan"]["arms"],
        payloads["first_train_scan_evaluation"]["arms"],
        strict=True,
    ):
        rows.append(
            attach_evaluation(
                row(
                    inferred,
                    "train",
                    "20260921_00",
                    "first_train_scan",
                    "regularized_global_plus_scan_epoch",
                ),
                evaluated,
            )
        )
    for a in payloads["second_train"]["arms"]:
        rows.append(
            attach_evaluation(
                row(
                    a,
                    "train",
                    "20260921_16",
                    "second_train",
                    "fixed_identity_shared_global_tau"
                    if a["model"] == "global"
                    else "regularized_global_plus_scan_epoch",
                ),
                a,
            )
        )
    validation_eval = {
        (x["group"], x["model"], x["scale_s"], x["view_scan_count"], x["prior"]): x
        for x in payloads["validation_evaluation"]["rows"]
    }
    for a in payloads["validation"]["arms"]:
        group = "20260922_08" if a["group"].startswith("2026-09-22") else "20260921_08"
        evaluated = validation_eval[
            (a["group"], a["model"], a["scale_s"], a["view_scan_count"], a["prior"])
        ]
        rows.append(
            attach_evaluation(
                row(
                    a,
                    "validation",
                    group,
                    "frozen_validation",
                    "fixed_identity_shared_global_tau"
                    if a["model"] == "global"
                    else "regularized_global_plus_scan_epoch",
                ),
                evaluated,
            )
        )
    test_eval = {
        (x["model"], x["scale_s"], x["view_scan_count"], x["prior"]): x
        for x in payloads["test_evaluation"]["rows"]
    }
    for a in payloads["test"]["arms"]:
        item = row(a, "test", "20260922_00", "final_test", "fixed_identity_shared_global_tau")
        evaluated = test_eval.get((a["model"], a["scale_s"], a["view_scan_count"], a["prior"]))
        rows.append(attach_evaluation(item, evaluated) if evaluated else item)
    for item in rows:
        case = case_index.get((item["partition"], item["group_id"], item["scan_count"]))
        if case is None:
            raise ValueError(
                f"not a DS1 case: {item['partition']} {item['group_id']} {item['scan_count']}"
            )
        item["case_id"] = case["case_id"]
        item["view"] = case["view"]
    # Freeze a scale solely from complete outer TRAIN blocks.  The metric is the
    # published TRAIN capped RMS; held rows and reference coordinates are not read.
    candidates = []
    for scale in (0.2, 1.0, 5.0):
        selected = [
            r
            for r in rows
            if r["partition"] == "train"
            and r["model"] == "regularized_global_plus_scan_epoch"
            and r["scan_count"] in (72, 79)
            and r["scale_s"] == scale
        ]
        if len(selected) != 4:
            raise ValueError(f"TRAIN full-block coverage missing at scale {scale}: {len(selected)}")
        candidates.append(
            {
                "scale_s": scale,
                "mean_training_capped_rms_hz": sum(r["training_capped_rms_hz"] for r in selected)
                / len(selected),
            }
        )
    selected_scale = min(candidates, key=lambda x: (x["mean_training_capped_rms_hz"], x["scale_s"]))
    output = {
        "schema": "ds1-timing-ablations/v2",
        "rows": rows,
        "train_only_scale_selection": {
            "selected": selected_scale,
            "candidates": candidates,
            "frozen_before_new_fractional_diagnostic": True,
        },
        "coverage": {
            "rows": len(rows),
            "full_train_blocks": [72, 79],
            "validation_views": [1, 6, 16, 44, 80],
            "test_views": [1, 6, 16],
            "full_TEST64": "explicit input failure retained",
            "fractional": "separate newly computed diagnostic",
        },
        "bindings": {
            **{name: digest(path) for name, path in sources.items()},
            "ds1_dataset": digest(ROOT / "reports/2026_09_24_ds1/dataset.json"),
        },
        "held_used_for_fit": False,
        "truth_used_for_fit": False,
    }
    (HERE / "timing_rows.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    (HERE / "timing_rows.sha256").write_text(
        hashlib.sha256((HERE / "timing_rows.json").read_bytes()).hexdigest() + "\n"
    )
    print(json.dumps({"rows": len(rows), "selected_scale": selected_scale}, indent=2))


if __name__ == "__main__":
    main()
