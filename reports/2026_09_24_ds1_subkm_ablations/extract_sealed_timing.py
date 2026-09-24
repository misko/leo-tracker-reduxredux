#!/usr/bin/env python3
# ruff: noqa: E501
"""Index exact, sealed historical timing arms against DS1 case identifiers.

These arms remain separate from the frozen-trace experiment: their identities
are fixed and their local optimizer is not the DS1 blind association search.
They are retained because they are the exact nonlinear 0.2/1/5 s timing
implementations, unlike the linearized diagnostic in ``run.py``.
"""

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def seal(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def add(rows, source, case, arm, model=None):
    rows.append(
        {
            "case_id": case,
            "source": str(source.relative_to(ROOT)),
            "comparison_scope": "sealed historical fixed-ID/local timing arm; not DS1 frozen-trace equivalent",
            "model": model or arm.get("model", "global"),
            "prior": arm["prior"],
            "scale_s": arm.get("scale_s"),
            "scan_count": arm.get("view_scan_count", arm.get("scan_count")),
            "reference_error_km": arm.get("reference_error_km"),
            "held_capped_rms_hz": arm.get(
                "held_capped_rms_hz", arm.get("reserved_capped800_rmse_hz")
            ),
            "held_uncapped_rms_hz": arm.get(
                "held_uncapped_rms_hz", arm.get("reserved_uncapped_rmse_hz")
            ),
            "tau_s": arm.get("global_tau_s"),
            "tau_boundary_count": arm.get("tau_boundary_count"),
            "stopping_rule_satisfied": arm.get("stopping_rule_satisfied"),
            "status": "input_failure" if arm.get("reference_error_km") is None else "completed",
        }
    )


def main():
    rows = []
    first = ROOT / "reports/2026_09_23_long_global_epoch_position/results/results.json"
    for arm in json.loads(first.read_text())["arms"]:
        view = "all" if arm["scan_count"] == 72 else str(arm["scan_count"])
        add(rows, first, "train_20260921_00_" + view, arm, "exact_global_epoch_fixed_id")
    full = ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/results/results.json"
    for arm in json.loads(full.read_text())["arms"]:
        add(rows, full, "train_20260921_00_all", arm, "exact_scan_epoch_fixed_id")
    second = ROOT / "reports/2026_09_23_second_train_epoch_replication/results/results.json"
    for arm in json.loads(second.read_text())["arms"]:
        add(
            rows,
            second,
            "train_20260921_16_"
            + ("all" if arm["view_scan_count"] == 79 else str(arm["view_scan_count"])),
            arm,
            "exact_" + arm["model"] + "_epoch_fixed_id",
        )
    validation = ROOT / "reports/2026_09_23_frozen_validation/results.json"
    for arm in json.loads(validation.read_text())["rows"]:
        group = (
            "validation_20260922_08"
            if "2026-09-22T08" in arm["group"]
            else "validation_20260921_08"
        )
        add(
            rows,
            validation,
            group
            + "_"
            + ("all" if arm["view_scan_count"] in (44, 80) else str(arm["view_scan_count"])),
            arm,
            "exact_" + arm["model"] + "_epoch_fixed_id",
        )
    test = ROOT / "reports/2026_09_23_final_test_global_epoch/results.json"
    for arm in json.loads(test.read_text())["rows"]:
        add(
            rows,
            test,
            "test_20260922_00_"
            + ("all" if arm["view_scan_count"] == 64 else str(arm["view_scan_count"])),
            arm,
            "exact_global_epoch_fixed_id",
        )
    output = HERE / "historical_exact_timing_rows.json"
    output.write_text(
        json.dumps(
            {
                "schema": "ds1-historical-exact-timing-index/v1",
                "rows": rows,
                "sources": {
                    str(p.relative_to(ROOT)): seal(p)
                    for p in (first, full, second, validation, test)
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    with (HERE / "historical_exact_timing_rows.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
