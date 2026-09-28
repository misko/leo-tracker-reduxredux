"""Evaluate a sealed DS7 progressive-search replay without selecting outcomes."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
FROZEN_BENCHMARK = HERE.parent / "2026_09_28_ds7_glrt_benchmark"
FROZEN_SCORER = FROZEN_BENCHMARK / "scoring.py"
FROZEN_SCORER_SHA256 = "30dd98adf6a15df0ab3a5f46f23c9ef08e16c33a5b0e4e327b1fa13fb7637aa0"
EXPECTED_REPETITIONS = 2


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_frozen_score():
    actual = _sha256(FROZEN_SCORER)
    if actual != FROZEN_SCORER_SHA256:
        raise RuntimeError(f"frozen scorer changed: {actual}")
    spec = importlib.util.spec_from_file_location("ds7_frozen_scoring", FROZEN_SCORER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import frozen DS7 scorer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.score


def _identity(context: Mapping[str, Any]) -> tuple[Any, ...]:
    """Immutable source identity, excluding extraction wall-clock metadata."""

    required = (
        "session_id", "visit_index", "manifest_sha256", "sample_start_counter",
        "sample_end_counter", "rate_hz", "target_index", "target",
        "actual_lo_frequency_hz", "actual_if_offset_hz", "shape", "dtype", "sha256",
    )
    missing = [name for name in required if name not in context]
    if missing:
        raise ValueError(f"context missing cohort identity fields: {', '.join(missing)}")
    target = context["target"]
    if not isinstance(target, Mapping):
        raise ValueError("context target must be a mapping")
    try:
        target_key = json.dumps(target, sort_keys=True, separators=(",", ":"), allow_nan=False)
        shape_key = tuple(context["shape"])
    except (TypeError, ValueError) as error:
        raise ValueError("context target or shape is not canonicalizable") from error
    return tuple(context[name] for name in required[:7]) + (
        target_key,
        context["actual_lo_frequency_hz"],
        context["actual_if_offset_hz"],
        shape_key,
        context["dtype"],
        context["sha256"],
    )


def _default_cohort() -> list[Mapping[str, Any]]:
    inputs = json.loads((FROZEN_BENCHMARK / "inputs.json").read_text())
    rows = inputs.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("frozen DS7 input cohort is unavailable")
    return rows


def _finite_timing(row: Mapping[str, Any]) -> None:
    timing = row.get("timing")
    if not isinstance(timing, Mapping):
        raise ValueError("row timing must be a mapping")
    for name in ("cpu_s", "wall_s"):
        value = timing.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"row timing {name} must be numeric")
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"row timing {name} must be finite and nonnegative")


def _validate_receipt(run: Mapping[str, Any]) -> None:
    if not run.get("complete") or not run.get("sources_unchanged"):
        raise ValueError("run receipt is incomplete or its source seal failed")
    if run.get("failed_calls") != 0:
        raise ValueError("run receipt records failed calls")
    if run.get("repetitions") != EXPECTED_REPETITIONS:
        raise ValueError("progressive evaluation requires exactly two repeats")
    if not isinstance(run.get("planned_calls"), int) or run["planned_calls"] <= 0:
        raise ValueError("run receipt planned_calls must be positive")
    source_hashes = run.get("source_hashes")
    if not isinstance(source_hashes, Mapping) or not source_hashes:
        raise ValueError("run receipt lacks source hashes")
    if any(not isinstance(value, str) or len(value) != 64 for value in source_hashes.values()):
        raise ValueError("run receipt contains an invalid source hash")


def _prior_original_parity(
    expected: set[tuple[Any, ...]],
    reference: Sequence[Mapping[str, Any]],
    prior_directory: Path | None,
) -> dict[str, Any]:
    """Compare the fresh baseline with the sealed prior baseline without using it as score input."""

    if prior_directory is None:
        return {"available": False, "reason": "prior comparison disabled by caller"}
    prior_receipt = json.loads((prior_directory / "run.json").read_text())
    _validate_receipt(prior_receipt)
    prior_rows = [json.loads(line) for line in (prior_directory / "rows.jsonl").read_text().splitlines()]
    prior = {
        _identity(row["context"]): row
        for row in prior_rows
        if row.get("method") == "original" and row.get("repeat") == 0 and row.get("status") == "ok"
    }
    if set(prior) != expected:
        raise ValueError("prior frozen original does not cover the progressive cohort")
    fresh = {_identity(row["context"]): row for row in reference}
    exact = sum(fresh[key]["result"] == prior[key]["result"] for key in expected)
    return {
        "prior_directory": str(prior_directory),
        "prior_rows_sha256": _sha256(prior_directory / "rows.jsonl"),
        "fresh_original_rows": len(fresh),
        "prior_original_rows": len(prior),
        "exact_full_output_equal": exact,
        "exact_full_output_fraction": exact / len(expected) if expected else None,
        "all_exact": exact == len(expected),
    }


def _cost(rows: Sequence[Mapping[str, Any]]) -> dict[str, float | int]:
    by_visit: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_visit[_identity(row["context"])].append(row)
    cpu_medians = [statistics.median(float(row["timing"]["cpu_s"]) for row in values)
                   for values in by_visit.values()]
    wall_medians = [statistics.median(float(row["timing"]["wall_s"]) for row in values)
                    for values in by_visit.values()]
    call_walls = sorted(float(row["timing"]["wall_s"]) for row in rows)
    index = math.ceil(0.95 * len(call_walls)) - 1
    return {
        "unique_visits": len(by_visit),
        "timed_calls": len(rows),
        "mean_visit_median_cpu_ms": 1_000 * statistics.fmean(cpu_medians),
        "mean_visit_median_wall_ms": 1_000 * statistics.fmean(wall_medians),
        "p95_call_wall_ms_nearest_rank": 1_000 * call_walls[index],
        "max_call_wall_ms": 1_000 * call_walls[-1],
        "total_cpu_s": sum(float(row["timing"]["cpu_s"]) for row in rows),
        "total_wall_s": sum(float(row["timing"]["wall_s"]) for row in rows),
    }


def _diagnostic_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    routes: Counter[str] = Counter()
    calls: Counter[str] = Counter()
    candidate_counts: list[int] = []
    for row in rows:
        diagnostics = row.get("diagnostics")
        if not isinstance(diagnostics, Mapping):
            raise ValueError("row diagnostics must be a mapping")
        route = diagnostics.get("route")
        routes[route if isinstance(route, str) else "<missing>"] += 1
        candidate_count = diagnostics.get("candidate_response_count")
        if isinstance(candidate_count, int) and not isinstance(candidate_count, bool):
            candidate_counts.append(candidate_count)
        for name, value in diagnostics.items():
            if (
                isinstance(name, str)
                and (name == "acquisition_calls" or name.endswith("_acquisition_calls")
                     or name == "detector_calls")
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
            ):
                calls[name] += value
    return {
        "route_counts_repeat0": dict(sorted(routes.items())),
        "acquisition_and_detector_calls_repeat0": dict(sorted(calls.items())),
        "actual_candidate_response_counts_repeat0": {
            "count": len(candidate_counts),
            "total": sum(candidate_counts),
            "minimum": min(candidate_counts) if candidate_counts else None,
            "maximum": max(candidate_counts) if candidate_counts else None,
            "mean": statistics.fmean(candidate_counts) if candidate_counts else None,
        },
    }


def _development_gates(science: Mapping[str, Any]) -> dict[str, Any]:
    recovery = science["recovery"]
    confirmation = recovery["confirmed_receiver_visit_matched_identity"]
    hypotheses = recovery["positive_candidate_identity"]
    confirmation_fraction = confirmation["fraction"]
    hypothesis_fraction = hypotheses["fraction"]
    return {
        "development_only_not_generalization": True,
        "confirmation_recovery_at_least_90_percent": (
            confirmation_fraction is not None and confirmation_fraction >= 0.90
        ),
        "confirmation_recovery_at_least_80_percent": (
            confirmation_fraction is not None and confirmation_fraction >= 0.80
        ),
        "positive_hypothesis_recovery_at_least_80_percent": (
            hypothesis_fraction is not None and hypothesis_fraction >= 0.80
        ),
    }


def _confirmed_receiver_visits(rows: Sequence[Mapping[str, Any]]) -> set[tuple[tuple[Any, ...], int]]:
    """Reconstruct standard positive-pair activity for added-reference reporting."""

    confirmed: set[tuple[tuple[Any, ...], int]] = set()
    for row in rows:
        by_receiver: dict[int, list[tuple[int, float]]] = defaultdict(list)
        for probe in row["result"]["probes"]:
            for candidate in probe["candidates"]:
                if candidate["passed_margin_gate"]:
                    by_receiver[probe["receiver_id"]].append(
                        (probe["probe_start_ms"], float(candidate["tracking_cfo_hz"]))
                    )
        for receiver_id, hits in by_receiver.items():
            if any(
                right_start - left_start >= 20 and abs(right_cfo - left_cfo) <= 8_000
                for left_start, left_cfo in hits
                for right_start, right_cfo in hits
            ):
                confirmed.add((_identity(row["context"]), receiver_id))
    return confirmed


def evaluate(
    run_directory: Path,
    *,
    expected_cohort: Sequence[Mapping[str, Any]] | None = None,
    prior_directory: Path | None = FROZEN_BENCHMARK / "run-01",
) -> dict[str, Any]:
    """Evaluate one sealed two-repeat progressive run against its fresh original."""

    run_directory = Path(run_directory)
    run = json.loads((run_directory / "run.json").read_text())
    _validate_receipt(run)
    rows = [json.loads(line) for line in (run_directory / "rows.jsonl").read_text().splitlines()]
    if len(rows) != run["planned_calls"]:
        raise ValueError("row count differs from planned_calls")
    cohort = list(_default_cohort() if expected_cohort is None else expected_cohort)
    expected = {_identity(context) for context in cohort}
    if len(expected) != len(cohort):
        raise ValueError("expected cohort has duplicate visit identities")
    expected_rates = Counter(identity[5] for identity in expected)
    grouped: dict[str, dict[int, dict[tuple[Any, ...], Mapping[str, Any]]]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or row.get("status") != "ok" or not isinstance(row.get("result"), Mapping):
            raise ValueError("every completed row must be an ok serialized analysis")
        method = row.get("method")
        repeat = row.get("repeat")
        context = row.get("context")
        if not isinstance(method, str) or not method:
            raise ValueError("row method must be nonempty")
        if isinstance(repeat, bool) or not isinstance(repeat, int) or repeat not in (0, 1):
            raise ValueError("row repeat must be zero or one")
        if not isinstance(context, Mapping):
            raise ValueError("row context must be a mapping")
        identity = _identity(context)
        if identity not in expected:
            raise ValueError("row is outside the frozen DS7 cohort")
        _finite_timing(row)
        by_repeat = grouped.setdefault(method, {}).setdefault(repeat, {})
        if identity in by_repeat:
            raise ValueError("duplicate method/repeat/visit row")
        by_repeat[identity] = row
    if not {"original", "optimized"} <= set(grouped):
        raise ValueError("fresh original and optimized methods are required")
    if len(grouped) < 3:
        raise ValueError("run must include at least one sparse or progressive method")
    declared_methods = run.get("methods")
    if (
        not isinstance(declared_methods, list)
        or any(not isinstance(name, str) or not name for name in declared_methods)
        or len(set(declared_methods)) != len(declared_methods)
        or set(declared_methods) != set(grouped)
    ):
        raise ValueError("receipt methods do not exactly match row methods")
    expected_calls = len(expected) * EXPECTED_REPETITIONS * len(grouped)
    if expected_calls != run["planned_calls"]:
        raise ValueError("planned_calls does not cover every method/repeat/visit")
    for method, repeats in grouped.items():
        if set(repeats) != {0, 1} or any(set(values) != expected for values in repeats.values()):
            raise ValueError(f"missing cohort rows for method {method}")
        rates = Counter(identity[5] for values in repeats.values() for identity in values)
        if rates != Counter({rate: count * EXPECTED_REPETITIONS for rate, count in expected_rates.items()}):
            raise ValueError(f"rate coverage mismatch for method {method}")

    score = _load_frozen_score()
    reference = list(grouped["original"][0].values())
    reference_confirmed = _confirmed_receiver_visits(reference)
    output: dict[str, Any] = {
        "schema": "leo.ds7.progressive-evaluation.v1",
        "scope": "development-only reference-relative replay; no oracle truth, false-alarm, or generalization claim",
        "run": {
            "directory": str(run_directory),
            "receipt": run,
            "rows_sha256": _sha256(run_directory / "rows.jsonl"),
            "frozen_scorer_sha256": FROZEN_SCORER_SHA256,
        },
        "cohort": {
            "unique_visits": len(expected),
            "rate_visits": {str(rate): expected_rates[rate] for rate in sorted(expected_rates)},
            "science_repeat": 0,
            "timing_repeats": [0, 1],
        },
        "fresh_original_vs_prior_frozen": _prior_original_parity(
            expected, reference, prior_directory
        ),
        "methods": {},
        "oracle_truth_claimed": False,
    }
    for method in sorted(grouped):
        repeat_zero = list(grouped[method][0].values())
        repeat_one = grouped[method][1]
        science = score(reference, repeat_zero)
        candidate_confirmed = _confirmed_receiver_visits(repeat_zero)
        repeat_exact = all(row["result"] == repeat_one[identity]["result"]
                           for identity, row in grouped[method][0].items())
        rate_entries: dict[str, Any] = {}
        for rate in sorted(expected_rates):
            reference_rate = [row for row in reference if row["context"]["rate_hz"] == rate]
            method_rate = [row for repeat in (0, 1) for row in grouped[method][repeat].values()
                           if row["context"]["rate_hz"] == rate]
            rate_science = score(reference_rate, [row for row in repeat_zero if row["context"]["rate_hz"] == rate])
            rate_entries[str(rate)] = {
                "cost": _cost(method_rate),
                "science": rate_science,
                "development_recovery_gates": _development_gates(rate_science),
            }
        output["methods"][method] = {
            "cost": _cost([row for repeat in (0, 1) for row in grouped[method][repeat].values()]),
            "science": science,
            "repeatability_exact_result": repeat_exact,
            "diagnostics": _diagnostic_summary(repeat_zero),
            "development_recovery_gates": _development_gates(science),
            "candidate_confirmed_relative_to_reference_unconfirmed_not_false_alarms": {
                "reference_confirmed_receiver_visit_pairs": len(reference_confirmed),
                "candidate_confirmed_receiver_visit_pairs": len(candidate_confirmed),
                "added_on_reference_unconfirmed_receiver_visit_pairs": len(
                    candidate_confirmed - reference_confirmed
                ),
            },
            "by_rate": rate_entries,
        }

    baseline = output["methods"]["original"]
    baseline_cost = baseline["cost"]
    for method, result in output["methods"].items():
        cost = result["cost"]
        result["cpu_speedup_vs_fresh_original"] = (
            baseline_cost["mean_visit_median_cpu_ms"] / cost["mean_visit_median_cpu_ms"]
        )
        result["wall_speedup_vs_fresh_original"] = (
            baseline_cost["mean_visit_median_wall_ms"] / cost["mean_visit_median_wall_ms"]
        )
        for rate, entry in result["by_rate"].items():
            baseline_rate = baseline["by_rate"][rate]["cost"]
            entry["cpu_speedup_vs_fresh_original"] = (
                baseline_rate["mean_visit_median_cpu_ms"] / entry["cost"]["mean_visit_median_cpu_ms"]
            )
            entry["wall_speedup_vs_fresh_original"] = (
                baseline_rate["mean_visit_median_wall_ms"] / entry["cost"]["mean_visit_median_wall_ms"]
            )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.run_directory)
    with args.output.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
