#!/usr/bin/env python3
"""Strict scientific and component-cost assessment of an ARM probe receipt."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

METHODS = ("packed_builtin_fp64", "packed_fftw_fp64", "aligned_v5_fftw_fp32")
BASELINES = ("packed_builtin_fp64", "packed_fftw_fp64")
TIMING_LIMIT_US = 2.0
CFO_LIMIT_HZ = 8000.0
STAGES = (
    "total_cpu_ms",
    "total_wall_ms",
    "boundary_cpu_ms",
    "boundary_wall_ms",
    "detector_outer_cpu_ms",
    "detector_outer_wall_ms",
    "native_cpu_ms",
    "native_wall_ms",
    "rank_cpu_ms",
    "conversion_cpu_ms",
    "coarse_cpu_ms",
    "fine_cpu_ms",
    "fractional_cpu_ms",
    "nuisance_cpu_ms",
    "io_cpu_ms",
    "io_wall_ms",
    "initialization_cpu_ms",
    "initialization_wall_ms",
)


def finite(
    value, *, positive: bool = False, nonnegative: bool = True, name: str = "value"
) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"nonfinite or nonnumeric {name}")
    result = float(value)
    if (positive and result <= 0) or (nonnegative and not positive and result < 0):
        raise ValueError(f"invalid negative/zero {name}")
    return result


def validate_plan(plan: dict) -> dict[str, dict]:
    if (
        plan.get("schema") != "org.leo.research.arm-stateless-probe-plan/v1"
        or plan.get("holdout_excluded") is not True
        or tuple(plan.get("methods", ())) != METHODS
        or plan.get("warmups") != 1
        or plan.get("repetitions") != 3
        or plan.get("max_confirmations") != 1
        or plan.get("seeded") is not False
    ):
        raise ValueError("probe plan contract differs")
    cases = plan.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("empty probe plan")
    by_id = {}
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in by_id:
            raise ValueError("invalid or duplicate planned case")
        if case.get("rate_hz") not in (2_500_000, 5_000_000):
            raise ValueError("unsupported planned rate")
        if case.get("edge") not in ("lower", "upper"):
            raise ValueError("invalid planned edge")
        if case.get("origin") == "real_ds5":
            if case.get("split") != "dev":
                raise ValueError("real ARM probe case is not development")
        elif case.get("origin") == "synthetic_control":
            if case.get("split") != "control" or control_kind(case_id) is None:
                raise ValueError("invalid synthetic control plan case")
        else:
            raise ValueError("unsupported planned case origin")
        by_id[case_id] = case
    return by_id


def control_kind(case_id: str) -> str | None:
    for kind in ("pilot", "noise", "tone"):
        if case_id.startswith(f"control-{kind}-"):
            return kind
    return None


def validate_candidate(candidate: dict) -> None:
    finite(candidate.get("epoch"), name="candidate epoch")
    for name in (
        "fractional_offset_samples",
        "acquired_cfo_hz",
        "tracking_cfo_hz",
        "margin",
    ):
        finite(candidate.get(name), nonnegative=False, name=f"candidate {name}")
    for name in (
        "exact_score",
        "control_score",
        "acquire_score",
        "verify_score",
        "verify_control_score",
        "conditioned_score",
        "coarse_score",
    ):
        finite(candidate.get(name), name=f"candidate {name}")
    for name in ("exact_grid", "control_grid"):
        grid = candidate.get(name)
        if not isinstance(grid, list) or len(grid) != 5:
            raise ValueError(f"invalid candidate {name}")
        for value in grid:
            finite(value, name=f"candidate {name}")
    if candidate.get("fractional_complete") not in (0, 1, False, True):
        raise ValueError("invalid fractional_complete")
    expected_margin = candidate["exact_score"] - candidate["control_score"]
    if not math.isclose(candidate["margin"], expected_margin, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("candidate margin is inconsistent")


def science(receiver: dict) -> dict:
    result = receiver.get("result")
    if not isinstance(result, dict) or result.get("confirmation_count") != 1:
        raise ValueError("incomplete one-confirmation result")
    rank = result.get("rank", {})
    order = rank.get("order")
    epochs = rank.get("projected_epoch_samples")
    scores = rank.get("scores")
    if (
        not isinstance(order, list)
        or sorted(order) != list(range(6))
        or not isinstance(epochs, list)
        or len(epochs) != 6
        or not isinstance(scores, list)
        or len(scores) != 6
    ):
        raise ValueError("invalid six-window rank result")
    for value in scores:
        finite(value, name="rank score")
    for value in epochs:
        finite(value, name="projected epoch")
    confirmations = result.get("confirmations")
    if not isinstance(confirmations, list) or len(confirmations) != 1:
        raise ValueError("invalid confirmation array")
    confirmation = confirmations[0]
    candidate_count = confirmation.get("candidate_count")
    candidates = confirmation.get("candidates")
    if candidate_count not in (0, 1) or not isinstance(candidates, list):
        raise ValueError("invalid candidate accounting")
    if len(candidates) != candidate_count:
        raise ValueError("candidate array length differs")
    candidate = candidates[0] if candidate_count else None
    if candidate is not None:
        validate_candidate(candidate)
    window_mask = result.get("confirmation_window_mask")
    if window_mask != 1 << order[0]:
        raise ValueError("confirmation mask differs from selected rank window")
    screens = receiver.get("screens")
    if not isinstance(screens, dict) or screens.get("selected") not in (0, 1):
        raise ValueError("missing or invalid rank screens")
    for name in ("scores", "order", "epochs"):
        values = screens.get(name)
        if (
            not isinstance(values, list)
            or len(values) != 2
            or any(not isinstance(row, list) or len(row) != 6 for row in values)
        ):
            raise ValueError(f"invalid screen {name}")
    if any(sorted(row) != list(range(6)) for row in screens["order"]):
        raise ValueError("invalid screen order")
    for row in screens["scores"]:
        for value in row:
            finite(value, name="screen score")
    for row in screens["epochs"]:
        for value in row:
            finite(value, name="screen epoch")
    contrasts = screens.get("contrast")
    if not isinstance(contrasts, list) or len(contrasts) != 2:
        raise ValueError("invalid screen contrast")
    for value in contrasts:
        finite(value, nonnegative=False, name="screen contrast")
    return {
        "rank_order": tuple(order),
        "screen_selected": screens["selected"],
        "screen_orders": tuple(tuple(row) for row in screens["order"]),
        "selected_window": order[0],
        "confirmation_window_mask": window_mask,
        "candidate_count": candidate_count,
        "fractional_complete": (
            bool(candidate["fractional_complete"]) if candidate is not None else None
        ),
        "epoch_samples": (
            candidate["epoch"] + candidate["fractional_offset_samples"]
            if candidate is not None
            else None
        ),
        "tracking_cfo_hz": (candidate["tracking_cfo_hz"] if candidate is not None else None),
        "exact": candidate["exact_score"] if candidate is not None else None,
        "control": candidate["control_score"] if candidate is not None else None,
        "margin": candidate["margin"] if candidate is not None else None,
        "positive": bool(
            candidate is not None
            and candidate["fractional_complete"]
            and candidate["margin"] > 0.025
        ),
    }


def repetition_cost(repetition: dict) -> dict:
    visit_cpu = finite(repetition.get("visit_cpu_ms"), positive=True, name="visit CPU")
    visit_wall = finite(repetition.get("visit_wall_ms"), positive=True, name="visit wall")
    receivers = repetition.get("receivers")
    if not isinstance(receivers, list) or [row.get("receiver") for row in receivers] != [0, 1]:
        raise ValueError("incomplete or unordered receiver schedule")
    cost = {name: 0.0 for name in STAGES}
    cost["total_cpu_ms"] = visit_cpu
    cost["total_wall_ms"] = visit_wall
    for receiver in receivers:
        packing_cpu = finite(receiver.get("packing_cpu_ms"), name="packing CPU")
        packing_wall = finite(receiver.get("packing_wall_ms"), name="packing wall")
        detector_cpu = finite(receiver.get("detector_cpu_ms"), positive=True, name="detector CPU")
        detector_wall = finite(
            receiver.get("detector_wall_ms"), positive=True, name="detector wall"
        )
        result = receiver["result"]
        native_cpu = finite(result.get("total_cpu_ms"), positive=True, name="native CPU")
        native_wall = finite(result.get("total_wall_ms"), positive=True, name="native wall")
        rank_cpu = finite(result["rank"].get("total_cpu_ms"), positive=True, name="rank CPU")
        rank_wall = finite(result["rank"].get("total_wall_ms"), positive=True, name="rank wall")
        rank_parts = sum(
            finite(result["rank"].get(name), name=f"rank {name}")
            for name in ("fold_cpu_ms", "correlation_cpu_ms")
        )
        confirmation = result["confirmations"][0]
        confirmation_cpu = finite(
            confirmation.get("total_cpu_ms"), positive=True, name="confirmation CPU"
        )
        confirmation_wall = finite(
            confirmation.get("total_wall_ms"), positive=True, name="confirmation wall"
        )
        component_sum = 0.0
        for key in ("conversion", "coarse", "fine", "fractional"):
            value = finite(confirmation.get(f"{key}_cpu_ms"), name=f"{key} CPU")
            cost[f"{key}_cpu_ms"] += value
            component_sum += value
        nuisances = result.get("nuisances")
        if not isinstance(nuisances, list) or len(nuisances) != 1:
            raise ValueError("invalid nuisance accounting")
        nuisance = nuisances[0]
        nuisance_cpu = finite(nuisance.get("cpu_ms"), name="nuisance CPU")
        finite(nuisance.get("frequency_hz"), nonnegative=False, name="nuisance frequency")
        for name in ("spectral_fraction", "fitted_power_fraction"):
            finite(nuisance.get(name), name=f"nuisance {name}")
        cost["nuisance_cpu_ms"] += nuisance_cpu
        tolerance = max(0.05, native_cpu * 0.05)
        if rank_parts > rank_cpu + tolerance:
            raise ValueError("rank stages exceed rank total")
        if rank_cpu + confirmation_cpu > native_cpu + tolerance:
            raise ValueError("native stages exceed native total")
        if component_sum + nuisance_cpu > confirmation_cpu + tolerance:
            raise ValueError("confirmation stages exceed confirmation total")
        if native_cpu > detector_cpu + max(0.05, detector_cpu * 0.05):
            raise ValueError("native CPU exceeds detector boundary")
        if native_wall > detector_wall + max(0.05, detector_wall * 0.05):
            raise ValueError("native wall exceeds detector boundary")
        if rank_wall > native_wall + tolerance or confirmation_wall > native_wall + tolerance:
            raise ValueError("native child wall timing exceeds native total")
        prefixes_cpu = result.get("prefix_cpu_ms")
        prefixes_wall = result.get("prefix_wall_ms")
        proposals = result.get("timing_proposals")
        if not all(
            isinstance(value, list) and len(value) == 1
            for value in (
                prefixes_cpu,
                prefixes_wall,
                proposals,
            )
        ):
            raise ValueError("invalid prefix or timing proposal accounting")
        finite(prefixes_cpu[0], name="prefix CPU")
        finite(prefixes_wall[0], name="prefix wall")
        proposal = proposals[0]
        finite(proposal.get("epoch"), name="timing proposal epoch")
        finite(proposal.get("score"), name="timing proposal score")
        for name in ("fold_cpu_ms", "correlation_cpu_ms", "total_cpu_ms", "total_wall_ms"):
            finite(proposal.get(name), name=f"timing proposal {name}")
        cost["boundary_cpu_ms"] += packing_cpu
        cost["boundary_wall_ms"] += packing_wall
        cost["detector_outer_cpu_ms"] += detector_cpu
        cost["detector_outer_wall_ms"] += detector_wall
        cost["native_cpu_ms"] += native_cpu
        cost["native_wall_ms"] += native_wall
        cost["rank_cpu_ms"] += rank_cpu
    if cost["boundary_cpu_ms"] + cost["detector_outer_cpu_ms"] > visit_cpu + max(
        0.05, visit_cpu * 0.05
    ):
        raise ValueError("receiver CPU stages exceed visit total")
    if cost["boundary_wall_ms"] + cost["detector_outer_wall_ms"] > visit_wall + max(
        0.05, visit_wall * 0.05
    ):
        raise ValueError("receiver wall stages exceed visit total")
    return cost


def validate_probe_result(result: dict, case: dict, method: str) -> dict:
    if (
        result.get("schema") != "org.leo.research.arm-stateless-probe-result/v1"
        or result.get("method") != method
        or result.get("case_id") != case["case_id"]
        or result.get("rate_hz") != case["rate_hz"]
        or result.get("edge") != case["edge"]
        or result.get("warmups") != 1
    ):
        raise ValueError("probe result identity differs from schedule")
    repetitions = result.get("repetitions")
    if not isinstance(repetitions, list) or len(repetitions) != 3:
        raise ValueError("probe lacks exactly three repetitions")
    setup = {
        "io_cpu_ms": finite(result.get("io_cpu_ms"), name="I/O CPU"),
        "io_wall_ms": finite(result.get("io_wall_ms"), name="I/O wall"),
        "initialization_cpu_ms": finite(
            result.get("initialization_cpu_ms"), name="initialization CPU"
        ),
        "initialization_wall_ms": finite(
            result.get("initialization_wall_ms"), name="initialization wall"
        ),
    }
    costs = []
    signatures = []
    for index, repetition in enumerate(repetitions):
        if repetition.get("index") != index:
            raise ValueError("repetition indices differ")
        receivers = repetition.get("receivers", [])
        signatures.append(tuple(science(receiver) for receiver in receivers))
        costs.append(repetition_cost(repetition))
    if any(signature != signatures[0] for signature in signatures[1:]):
        raise ValueError("scientific output changes across repetitions")
    medians = {
        name: (setup[name] if name in setup else statistics.median(cost[name] for cost in costs))
        for name in STAGES
    }
    return {"science": signatures[0], "cost": medians}


def groups(cases: dict[str, dict]) -> dict[str, set[str]]:
    return {
        "all": set(cases),
        "real_dev": {case_id for case_id, case in cases.items() if case["origin"] == "real_ds5"},
        "controls": {
            case_id for case_id, case in cases.items() if case["origin"] == "synthetic_control"
        },
        "rate_2500000": {
            case_id for case_id, case in cases.items() if case["rate_hz"] == 2_500_000
        },
        "rate_5000000": {
            case_id for case_id, case in cases.items() if case["rate_hz"] == 5_000_000
        },
    }


def sum_costs(rows: dict[tuple[str, str], dict], case_ids: set[str]) -> dict:
    return {
        method: {
            stage: sum(rows[case_id, method]["cost"][stage] for case_id in case_ids)
            for stage in STAGES
        }
        for method in METHODS
    }


def circular_samples(value: float, rate: int) -> float:
    period = rate / 750.0
    return (value + period / 2) % period - period / 2


def identity(
    rows: dict[tuple[str, str], dict],
    cases: dict[str, dict],
    case_ids: set[str],
    baseline: str,
    method: str,
) -> dict:
    comparisons = []
    for case_id in sorted(case_ids):
        rate = cases[case_id]["rate_hz"]
        for receiver, (reference, candidate) in enumerate(
            zip(
                rows[case_id, baseline]["science"],
                rows[case_id, method]["science"],
                strict=True,
            )
        ):
            same_count = reference["candidate_count"] == candidate["candidate_count"]
            same_fractional = reference["fractional_complete"] == candidate["fractional_complete"]
            timing_us = None
            cfo_hz = None
            score_delta = None
            if reference["candidate_count"] and candidate["candidate_count"]:
                timing_us = (
                    abs(
                        circular_samples(
                            candidate["epoch_samples"] - reference["epoch_samples"], rate
                        )
                    )
                    / rate
                    * 1e6
                )
                cfo_hz = abs(candidate["tracking_cfo_hz"] - reference["tracking_cfo_hz"])
                score_delta = {
                    "exact": candidate["exact"] - reference["exact"],
                    "control": candidate["control"] - reference["control"],
                    "margin": candidate["margin"] - reference["margin"],
                }
            passed = (
                reference["rank_order"] == candidate["rank_order"]
                and reference["screen_selected"] == candidate["screen_selected"]
                and reference["screen_orders"] == candidate["screen_orders"]
                and reference["confirmation_window_mask"] == candidate["confirmation_window_mask"]
                and same_count
                and same_fractional
                and (timing_us is None or timing_us <= TIMING_LIMIT_US)
                and (cfo_hz is None or cfo_hz <= CFO_LIMIT_HZ)
            )
            comparisons.append(
                {
                    "case_id": case_id,
                    "receiver": receiver,
                    "passed": passed,
                    "same_rank_order": reference["rank_order"] == candidate["rank_order"],
                    "same_screen_projection": reference["screen_selected"]
                    == candidate["screen_selected"],
                    "same_screen_orders": reference["screen_orders"] == candidate["screen_orders"],
                    "same_confirmation_window": reference["confirmation_window_mask"]
                    == candidate["confirmation_window_mask"],
                    "same_candidate_count": same_count,
                    "same_fractional_complete": same_fractional,
                    "timing_error_us": timing_us,
                    "cfo_error_hz": cfo_hz,
                    "score_delta": score_delta,
                    "reference_positive": reference["positive"],
                    "candidate_positive": candidate["positive"],
                }
            )
    reference_positive = [row for row in comparisons if row["reference_positive"]]
    candidate_positive = [row for row in comparisons if row["candidate_positive"]]
    retained = [
        row
        for row in comparisons
        if row["reference_positive"] and row["candidate_positive"] and row["passed"]
    ]
    score_rows = [row["score_delta"] for row in comparisons if row["score_delta"]]
    return {
        "receiver_cases": len(comparisons),
        "all_identity_gates_pass": all(row["passed"] for row in comparisons),
        "identity_failures": sum(not row["passed"] for row in comparisons),
        "reference_positives": len(reference_positive),
        "candidate_positives": len(candidate_positive),
        "retained_reference_positives": len(retained),
        "lost_reference_positives": len(reference_positive) - len(retained),
        "additional_candidate_positives": sum(
            row["candidate_positive"] and not row["reference_positive"] for row in comparisons
        ),
        "max_timing_error_us": max(
            (row["timing_error_us"] or 0.0 for row in comparisons), default=0.0
        ),
        "max_cfo_error_hz": max((row["cfo_error_hz"] or 0.0 for row in comparisons), default=0.0),
        "max_abs_score_delta": {
            name: max((abs(row[name]) for row in score_rows), default=0.0)
            for name in ("exact", "control", "margin")
        },
        "rows": comparisons,
    }


def control_labels(
    rows: dict[tuple[str, str], dict], cases: dict[str, dict], case_ids: set[str]
) -> dict:
    result = {}
    for method in METHODS:
        kinds = {}
        for kind in ("pilot", "noise", "tone"):
            selected = [case_id for case_id in case_ids if control_kind(case_id) == kind]
            receiver_values = [
                receiver["positive"]
                for case_id in selected
                for receiver in rows[case_id, method]["science"]
            ]
            expected = kind == "pilot"
            kinds[kind] = {
                "receiver_cases": len(receiver_values),
                "expected_positive": expected,
                "observed_positive": sum(receiver_values),
                "exact_label_matches": sum(value is expected for value in receiver_values),
                "all_exact_labels_match": all(value is expected for value in receiver_values),
            }
        result[method] = kinds
    return result


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 0 else None


def cost_comparison(baseline: dict, candidate: dict) -> dict:
    cpu_base = baseline["total_cpu_ms"]
    result = {
        "total_cpu_speedup": safe_ratio(cpu_base, candidate["total_cpu_ms"]),
        "total_wall_speedup": safe_ratio(baseline["total_wall_ms"], candidate["total_wall_ms"]),
        "native_cpu_speedup": safe_ratio(baseline["native_cpu_ms"], candidate["native_cpu_ms"]),
        "stage_delta_cpu_ms": {
            stage: candidate[stage] - baseline[stage]
            for stage in STAGES
            if stage.endswith("cpu_ms")
        },
        "baseline_perfect_stage_removal_ceiling": {},
        "candidate_next_stage_zero_speedup_from_baseline": {},
    }
    for stage in (
        "boundary_cpu_ms",
        "native_cpu_ms",
        "rank_cpu_ms",
        "conversion_cpu_ms",
        "coarse_cpu_ms",
        "fine_cpu_ms",
        "fractional_cpu_ms",
        "nuisance_cpu_ms",
    ):
        result["baseline_perfect_stage_removal_ceiling"][stage] = safe_ratio(
            cpu_base, cpu_base - baseline[stage]
        )
        result["candidate_next_stage_zero_speedup_from_baseline"][stage] = safe_ratio(
            cpu_base, candidate["total_cpu_ms"] - candidate[stage]
        )
    return result


def assess_remote(receipt: dict, plan: dict) -> dict:
    cases = validate_plan(plan)
    if (
        receipt.get("schema") != "org.leo.research.arm-stateless-remote-result/v1"
        or receipt.get("status") != "complete"
        or receipt.get("execution_environment") != "physical_arm_saved_iq"
        or receipt.get("qemu") is not False
        or receipt.get("plan_complete") is not True
        or receipt.get("case_limit") != len(cases)
        or receipt.get("rf_collection") is not False
        or receipt.get("firmware_written") is not False
        or receipt.get("temporary_files_removed") is not True
    ):
        raise ValueError("remote receipt is incomplete or unsafe for assessment")
    if (
        not isinstance(receipt.get("host"), str)
        or not isinstance(receipt.get("serial"), str)
        or not isinstance(receipt.get("firmware"), str)
        or receipt.get("before") != receipt.get("after")
        or receipt.get("remote_hashes_before") != receipt.get("remote_hashes_after")
    ):
        raise ValueError("remote identity, attestation, or staged hashes differ")
    raw_rows = receipt.get("rows")
    if not isinstance(raw_rows, list) or len(raw_rows) != len(cases) * len(METHODS):
        raise ValueError("incomplete case/method schedule")
    rows = {}
    case_order = {case_id: index for index, case_id in enumerate(cases)}
    for item in raw_rows:
        result = item.get("result") if isinstance(item, dict) else None
        if not isinstance(result, dict):
            raise ValueError("malformed scheduled result")
        key = (result.get("case_id"), result.get("method"))
        if key in rows or key[0] not in cases or key[1] not in METHODS:
            raise ValueError("duplicate or unexpected scheduled result")
        expected_case = cases[key[0]]
        expected_identity = {
            name: expected_case[name] for name in ("case_id", "origin", "split", "rate_hz", "edge")
        }
        expected_order = METHODS[case_order[key[0]] % 3 :] + METHODS[: case_order[key[0]] % 3]
        if item.get("case") != expected_identity or item.get(
            "schedule_position"
        ) != expected_order.index(key[1]):
            raise ValueError("case identity or rotated schedule position differs")
        rows[key] = validate_probe_result(result, cases[key[0]], key[1])
    expected = {(case_id, method) for case_id in cases for method in METHODS}
    if set(rows) != expected:
        raise ValueError("remote receipt omits a case/method pair")

    grouped = groups(cases)
    costs = {name: sum_costs(rows, case_ids) for name, case_ids in grouped.items()}
    identities = {}
    comparisons = {}
    for group, case_ids in grouped.items():
        identities[group] = {
            baseline: {
                method: identity(rows, cases, case_ids, baseline, method) for method in METHODS
            }
            for baseline in BASELINES
        }
        comparisons[group] = {
            baseline: {
                method: cost_comparison(costs[group][baseline], costs[group][method])
                for method in METHODS
            }
            for baseline in BASELINES
        }
    labels = control_labels(rows, cases, grouped["controls"])
    return {
        "schema": "org.leo.research.arm-stateless-assessment/v1",
        "input_kind": "physical_arm_remote_receipt",
        "timing_valid": True,
        "component_scope": "stateless saved-IQ detector only",
        "cost_scope": (
            "total/boundary/native costs are sums of per-case three-repetition medians; "
            "I/O and initialization are separately summed one-time process measurements"
        ),
        "cases": len(cases),
        "receiver_cases": len(cases) * 2,
        "costs": costs,
        "cost_comparisons": comparisons,
        "scientific_identity": identities,
        "control_labels": labels,
        "scientific_pass": all(
            identities["all"][baseline][method]["all_identity_gates_pass"]
            for baseline in BASELINES
            for method in METHODS
        )
        and all(
            kind["all_exact_labels_match"] for method in labels.values() for kind in method.values()
        ),
        "limitations": [
            "component timing excludes capture, scheduling, queueing, causal state, and fallback",
            "stateless component speedup cannot establish a 10x pipeline result",
            (
                "physical ARM component timing does not by itself establish real-time "
                "pipeline capacity"
            ),
        ],
    }


def assess_qemu(receipt: dict) -> dict:
    if (
        receipt.get("schema") != "org.leo.research.arm-stateless-qemu-functional/v1"
        or receipt.get("timing_valid") is not False
        or "qemu" not in str(receipt.get("environment", "")).lower()
    ):
        raise ValueError("not a frozen QEMU functional receipt")
    comparisons = []
    for case in receipt.get("cases", []):
        for name in ("fp64_fftw_vs_builtin", "aligned_fp32_vs_builtin"):
            values = case.get(name)
            if not isinstance(values, list) or len(values) != 6:
                raise ValueError("incomplete QEMU functional schedule")
            comparisons.extend(values)
    if not comparisons or not all(row.get("passed") is True for row in comparisons):
        raise ValueError("QEMU functional identity failed")
    return {
        "schema": "org.leo.research.arm-stateless-assessment/v1",
        "input_kind": "qemu_functional_fixture",
        "timing_valid": False,
        "functional_comparisons": len(comparisons),
        "functional_identity_pass": True,
        "costs": None,
        "cost_comparisons": None,
        "limitations": [
            "QEMU establishes bounded functional execution only",
            "QEMU timing is invalid and is never included in performance results",
            "no pipeline or real-time claim can be made from this fixture",
        ],
    }


def assess(receipt: dict, plan: dict | None = None) -> dict:
    if receipt.get("schema") == "org.leo.research.arm-stateless-qemu-functional/v1":
        return assess_qemu(receipt)
    if plan is None:
        raise ValueError("physical ARM assessment requires the frozen plan")
    return assess_remote(receipt, plan)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--plan", type=Path, default=Path(__file__).with_name("plan.json"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    receipt = json.loads(args.receipt.read_text())
    plan = None if "qemu" in receipt.get("schema", "") else json.loads(args.plan.read_text())
    result = assess(receipt, plan)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
