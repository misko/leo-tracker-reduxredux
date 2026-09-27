#!/usr/bin/env python3
"""Bounded controls and same-visit oracle benchmark for coefficient GLRT."""

from __future__ import annotations

import json
import statistics
import sys
from contextlib import ExitStack
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NATIVE_REPORT = ROOT / "reports/2026_09_27_ds5_cached_tracking/native"
DATASET = ROOT / "reports/2026_09_26_ds5_server_eval/dataset"
sys.path[:0] = [str(HERE), str(NATIVE_REPORT)]

from coeff_glrt import NativeCoeffGLRT, build_library  # noqa: E402
from known_state import sha256  # noqa: E402
from known_state_v2 import NativeKnownStateV2  # noqa: E402


def challenge_state(case, receiver):
    truth = case["truth"]
    spec = truth["receivers"][receiver]
    if truth["starlink_model_present"]:
        return spec["window"], spec["epoch_samples"] + spec["fractional_delay_samples"], spec["cfo_hz"]
    seed = spec["seed"]
    cfo = spec.get("carrier_hz")
    if cfo is None:
        cfo = (seed * 137) % 800_001 - 400_000
    return seed % 6, (seed * 0.731) % (case["rate_hz"] / 750.0), cfo


def load_case(case):
    path = (DATASET / case["raw_npy"]["path"]).resolve()
    if not path.is_relative_to(DATASET):
        raise ValueError("IQ outside dataset")
    if sha256(path) != case["raw_npy"]["sha256"].removeprefix("sha256:"):
        raise ValueError("IQ provenance mismatch")
    return np.load(path, allow_pickle=False)


def measure_pair(baseline, candidate, selected, epoch, cfo, design):
    repetitions = design["timing"]["repetitions"]
    warmups = design["timing"]["warmups"]
    for _ in range(warmups):
        baseline.measure(selected, epoch, cfo, frame_limit=16)
        candidate.measure(selected, epoch, cfo)
    baseline_rows = [
        baseline.measure(selected, epoch, cfo, frame_limit=16)
        for _ in range(repetitions)
    ]
    candidate_rows = [candidate.measure(selected, epoch, cfo) for _ in range(repetitions)]
    first = candidate_rows[0]
    if any(
        (row["exact_score"], row["control_score"], row["cfo_innovation_hz"],
         row["coefficient_tables_built"], row["coefficient_table_hits"])
        != (first["exact_score"], first["control_score"], first["cfo_innovation_hz"],
            first["coefficient_tables_built"], first["coefficient_table_hits"])
        for row in candidate_rows[1:]
    ):
        raise ValueError("coefficient result changed across identical calls")
    return {
        "baseline": baseline_rows[0],
        "candidate": first,
        "timing": {
            "baseline_median_cpu_ms": statistics.median(
                row["total_cpu_ms"] for row in baseline_rows
            ),
            "baseline_median_wall_ms": statistics.median(
                row["total_wall_ms"] for row in baseline_rows
            ),
            "candidate_median_cpu_ms": statistics.median(
                row["total_cpu_ms"] for row in candidate_rows
            ),
            "candidate_median_wall_ms": statistics.median(
                row["total_wall_ms"] for row in candidate_rows
            ),
            "coefficient_build_median_cpu_ms": statistics.median(
                row["coefficient_build_cpu_ms"] for row in candidate_rows
            ),
            "coefficient_dot_median_cpu_ms": statistics.median(
                row["coefficient_dot_cpu_ms"] for row in candidate_rows
            ),
        },
    }


def gate(result):
    return result["margin"] > 0.025 and abs(result["cfo_innovation_hz"]) <= 8_000


def run(output):
    if output.exists():
        raise FileExistsError(output)
    design_path = HERE / "design.json"
    design = json.loads(design_path.read_text())
    manifest_path = DATASET / "cases.json"
    manifest = json.loads(manifest_path.read_text())
    controls = [
        case for case in manifest["cases"]
        if case["split"] == "control" and case["rate_hz"] in (2_500_000, 5_000_000)
    ]
    oracle_path = NATIVE_REPORT / "real_oracle_microbenchmark.json"
    oracle = json.loads(oracle_path.read_text())
    cases = {case["case_id"]: case for case in manifest["cases"]}
    library = build_library()
    rows = []
    with ExitStack() as stack:
        workspaces = {}

        def workspace(rate, edge):
            key = rate, edge
            if key not in workspaces:
                workspaces[key] = (
                    stack.enter_context(NativeKnownStateV2(rate, edge, library)),
                    stack.enter_context(NativeCoeffGLRT(rate, edge, library)),
                )
            return workspaces[key]

        for case in controls:
            iq = load_case(case)
            rate = case["rate_hz"]
            count = rate // 50
            for receiver in range(2):
                window, epoch, cfo = challenge_state(case, receiver)
                selected = iq[window * count:(window + 1) * count, receiver, :]
                pair = measure_pair(*workspace(rate, case["edge"]), selected, epoch, cfo, design)
                rows.append({
                    "cohort": "constructed_control",
                    "case_id": case["case_id"],
                    "kind": case["truth"]["kind"],
                    "model_present": case["truth"]["starlink_model_present"],
                    "rate_hz": rate,
                    "edge": case["edge"],
                    "receiver": receiver,
                    "window": window,
                    "epoch_samples": epoch,
                    "scored_cfo_hz": cfo,
                    **pair,
                })
        arrays = {}
        for seed in oracle["rows"]:
            case = cases[seed["case_id"]]
            if case["split"] != "dev":
                raise ValueError("oracle row is not development data")
            if case["case_id"] not in arrays:
                arrays[case["case_id"]] = load_case(case)
            rate = case["rate_hz"]
            count = rate // 50
            begin = seed["window_index"] * count
            selected = arrays[case["case_id"]][begin:begin + count, seed["rx"], :]
            blind = seed["blind_candidate"]
            epoch = blind["epoch"] + blind["fractional_offset_samples"]
            cfo = blind["acquired_cfo_hz"]
            pair = measure_pair(*workspace(rate, case["edge"]), selected, epoch, cfo, design)
            rows.append({
                "cohort": "same_visit_oracle_noncausal",
                "case_id": case["case_id"],
                "kind": None,
                "model_present": None,
                "rate_hz": rate,
                "edge": case["edge"],
                "receiver": seed["rx"],
                "window": seed["window_index"],
                "epoch_samples": epoch,
                "scored_cfo_hz": cfo,
                **pair,
            })
    tolerance = design["tolerances"]
    for row in rows:
        baseline, candidate = row["baseline"], row["candidate"]
        row["comparison"] = {
            "exact_score_error": candidate["exact_score"] - baseline["exact_score"],
            "control_score_error": candidate["control_score"] - baseline["control_score"],
            "margin_gate_equal": (candidate["margin"] > 0.025) == (baseline["margin"] > 0.025),
            "trusted_gate_equal": gate(candidate) == gate(baseline),
            "peak_bin_equal": candidate["coefficient_peak_bin"] == candidate["baseline_peak_bin"],
            "residual_cfo_equal": candidate["cfo_innovation_hz"] == baseline["cfo_innovation_hz"],
        }
    summary = {
        "receiver_cases": len(rows),
        "constructed_controls": sum(row["cohort"] == "constructed_control" for row in rows),
        "same_visit_oracle_cases": sum(row["cohort"] == "same_visit_oracle_noncausal" for row in rows),
        "maximum_correlation_relative_error": max(
            row["candidate"]["correlation_max_relative_error"] for row in rows
        ),
        "maximum_ceiling_relative_error": max(
            row["candidate"]["ceiling_max_relative_error"] for row in rows
        ),
        "maximum_exact_score_absolute_error": max(
            abs(row["comparison"]["exact_score_error"]) for row in rows
        ),
        "maximum_control_score_absolute_error": max(
            abs(row["comparison"]["control_score_error"]) for row in rows
        ),
        "peak_bin_changes": sum(not row["comparison"]["peak_bin_equal"] for row in rows),
        "residual_cfo_changes": sum(not row["comparison"]["residual_cfo_equal"] for row in rows),
        "margin_gate_changes": sum(not row["comparison"]["margin_gate_equal"] for row in rows),
        "trusted_gate_changes": sum(not row["comparison"]["trusted_gate_equal"] for row in rows),
        "baseline_median_cpu_ms": statistics.median(
            row["timing"]["baseline_median_cpu_ms"] for row in rows
        ),
        "candidate_median_cpu_ms": statistics.median(
            row["timing"]["candidate_median_cpu_ms"] for row in rows
        ),
        "coefficient_build_median_cpu_ms": statistics.median(
            row["timing"]["coefficient_build_median_cpu_ms"] for row in rows
        ),
        "coefficient_dot_median_cpu_ms": statistics.median(
            row["timing"]["coefficient_dot_median_cpu_ms"] for row in rows
        ),
    }
    summary["candidate_over_baseline_cpu_ratio"] = (
        summary["candidate_median_cpu_ms"] / summary["baseline_median_cpu_ms"]
    )
    summary["within_frozen_numerical_bounds"] = (
        summary["maximum_correlation_relative_error"]
        <= tolerance["maximum_correlation_relative_error"]
        and summary["maximum_ceiling_relative_error"]
        <= tolerance["maximum_ceiling_relative_error"]
        and summary["maximum_exact_score_absolute_error"]
        <= tolerance["maximum_exact_score_absolute_error"]
        and summary["maximum_control_score_absolute_error"]
        <= tolerance["maximum_control_score_absolute_error"]
        and not summary["peak_bin_changes"] and not summary["residual_cfo_changes"]
        and not summary["margin_gate_changes"] and not summary["trusted_gate_changes"]
    )
    summary["performance_rule_passed"] = (
        summary["candidate_median_cpu_ms"] < summary["baseline_median_cpu_ms"]
    )
    receipt = {
        "schema": "org.leo.research.coefficient-glrt-experiment/v1",
        "scope": "constructed controls plus same-visit dev oracle; no holdout",
        "fresh_holdout_opened": False,
        "design_sha256": sha256(design_path),
        "dataset_cases_sha256": sha256(manifest_path),
        "oracle_receipt_sha256": sha256(oracle_path),
        "library_sha256": sha256(library),
        "library_build_receipt_sha256": sha256(library.with_name(library.name + ".build.json")),
        "source_sha256": sha256(Path(__file__)),
        "summary": summary,
        "rows": rows,
        "limitations": [
            "same-visit oracle coordinates are noncausal",
            "constructed controls do not calibrate classifier rates",
            "server timing is not ARM timing",
            "coefficient tables are rebuilt within every invocation",
        ],
    }
    with output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run(HERE / "results.json")
