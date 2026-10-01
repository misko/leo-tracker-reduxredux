"""Truth-free phase and paired-runtime diagnostics for localization runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLANNED_UNITS = 64
ARMS = ("A1", "B1")


def _load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"JSON document is not an object: {path}")
    return value


def _receipt_path(row: dict, root: Path) -> Path | None:
    value = row.get("receipt_path")
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else root / path


def _rows(document: dict) -> dict[tuple[str, str], dict]:
    result = {}
    for row in document.get("rows", []):
        arm, unit = row.get("arm"), row.get("unit_id")
        if arm not in ARMS or not unit:
            continue
        key = arm, unit
        if key in result:
            raise ValueError(f"duplicate evaluator row: {key}")
        result[key] = row
    return result


def _number_summary(values: list[float]) -> dict:
    array = np.asarray(values, dtype=float)
    return {
        "count": int(array.size),
        "median_s": None if not array.size else float(np.median(array)),
        "p10_s": None if not array.size else float(np.percentile(array, 10)),
        "p90_s": None if not array.size else float(np.percentile(array, 90)),
        "sum_s": float(array.sum()),
    }


def _fit_seconds(receipt: dict) -> float:
    return sum(float(fit.get("fit_seconds", 0)) for fit in receipt.get("fits", []))


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _fit_key(fit: dict) -> tuple:
    if fit.get("seed_index") is not None:
        return "index", int(fit["seed_index"])
    seed = fit.get("seed") or fit.get("parent_seed")
    if isinstance(seed, dict):
        return "coordinates", float(seed["east_km"]), float(seed["north_km"])
    raise ValueError("fit lacks seed identity")


def _continuation_fit_seconds(receipt: dict, repository_root: Path) -> float:
    """Count only child fits changed by resumption, excluding copied parent fits."""
    binding = receipt.get("parent")
    if not isinstance(binding, dict) or not binding.get("path"):
        return _fit_seconds(receipt)
    parent_path = Path(binding["path"])
    parent_path = parent_path if parent_path.is_absolute() else repository_root / parent_path
    if not parent_path.is_file():
        raise ValueError(f"continuation parent receipt is missing: {parent_path}")
    expected_digest = binding.get("sha256")
    if expected_digest and _digest(parent_path) != expected_digest:
        raise ValueError(f"continuation parent digest mismatch: {parent_path}")
    parents = {_fit_key(fit): fit for fit in _load(parent_path).get("fits", [])}
    children = receipt.get("fits", [])
    if len({_fit_key(fit) for fit in children}) != len(children):
        raise ValueError("continuation contains duplicate seed identities")
    total = 0.0
    for fit in children:
        parent = parents.get(_fit_key(fit))
        if parent is None:
            raise ValueError("continuation fit has no parent seed")
        if fit != parent:
            # replay_approach records resumed fit_seconds as stage-only work.
            total += float(fit.get("fit_seconds", 0))
    return total


def _phase(row: dict, receipt: dict | None, launch: dict | None) -> str:
    if not row.get("attempted"):
        return "not_attempted"
    if launch and (
        launch.get("timed_out") is True
        or launch.get("status") == "timeout"
        or (launch.get("returncode") not in (None, 0))
    ):
        return "worker_timeout"
    if receipt is None:
        return "worker_timeout"
    exception = receipt.get("exception") or {}
    message = str(exception.get("message", "")).lower()
    if "acquisition" in message and "wall budget" in message:
        return "acquisition_timeout"
    if row.get("accepted"):
        return "accepted"
    if receipt.get("status") == "unresolved" or any(
        fit.get("reason") in {"wall_budget", "iteration_limit", "line_search_stalled"}
        for fit in receipt.get("fits", [])
    ):
        return "optimizer_unresolved"
    return "other_failure"


def _paired_runtime(rows: dict[tuple[str, str], dict], *, accepted_only: bool) -> dict:
    units = sorted({unit for arm, unit in rows if arm == "A1"})
    pairs = []
    for unit in units:
        left, right = rows.get(("A1", unit)), rows.get(("B1", unit))
        if left is None or right is None:
            continue
        if not left.get("attempted") or not right.get("attempted"):
            continue
        if accepted_only and not (left.get("accepted") and right.get("accepted")):
            continue
        a_time, b_time = left.get("runtime_s"), right.get("runtime_s")
        if a_time is None or b_time is None or a_time <= 0 or b_time <= 0:
            continue
        pairs.append((unit, float(a_time), float(b_time)))
    a_values = [pair[1] for pair in pairs]
    b_values = [pair[2] for pair in pairs]
    a_median = None if not a_values else float(np.median(a_values))
    b_median = None if not b_values else float(np.median(b_values))
    return {
        "planned_denominator": PLANNED_UNITS,
        "paired_count": len(pairs),
        "a1_median_s": a_median,
        "b1_median_s": b_median,
        "ratio_of_medians_b1_over_a1": (
            None if a_median is None or b_median is None else b_median / a_median
        ),
        "median_paired_ratio_b1_over_a1": (
            None if not pairs else float(np.median([b / a for _, a, b in pairs]))
        ),
        "unit_ids": [pair[0] for pair in pairs],
    }


def diagnose(
    primary_evaluator: Path,
    two_stage_evaluator: Path | None = None,
    *,
    repository_root: Path = ROOT,
) -> dict:
    """Summarize timing phases without loading truth fields from evaluator rows."""
    primary_rows = _rows(_load(primary_evaluator))
    final_rows = (
        primary_rows if two_stage_evaluator is None else _rows(_load(two_stage_evaluator))
    )
    phase_counts = {arm: Counter() for arm in ARMS}
    final_phase_counts = {arm: Counter() for arm in ARMS}
    acquisition = {arm: [] for arm in ARMS}
    optimizer = {arm: [] for arm in ARMS}
    cpu = {arm: [] for arm in ARMS}
    seen_receipts = set()
    for (arm, _unit), row in primary_rows.items():
        receipt_path = _receipt_path(row, repository_root)
        receipt = _load(receipt_path) if receipt_path and receipt_path.is_file() else None
        launch_path = row.get("launch_path")
        launch = None
        if launch_path:
            path = Path(launch_path)
            path = path if path.is_absolute() else repository_root / path
            launch = _load(path) if path.is_file() else None
        phase_counts[arm][_phase(row, receipt, launch)] += 1
        if receipt is not None and receipt.get("acquisition_seconds") is not None:
            acquisition[arm].append(float(receipt["acquisition_seconds"]))
        if receipt is not None:
            optimizer[arm].append(_fit_seconds(receipt))
            if receipt.get("cpu_seconds") is not None:
                cpu[arm].append(float(receipt["cpu_seconds"]))
            seen_receipts.add(receipt_path.resolve())
    # Add continuation-only optimizer and CPU work once; acquisition belongs to primary.
    for (arm, unit), row in final_rows.items():
        primary = primary_rows.get((arm, unit))
        if primary and row.get("receipt_path") == primary.get("receipt_path"):
            continue
        receipt_path = _receipt_path(row, repository_root)
        if (
            not receipt_path
            or not receipt_path.is_file()
            or receipt_path.resolve() in seen_receipts
        ):
            continue
        receipt = _load(receipt_path)
        optimizer[arm].append(_continuation_fit_seconds(receipt, repository_root))
        if receipt.get("cpu_seconds") is not None:
            cpu[arm].append(float(receipt["cpu_seconds"]))
        seen_receipts.add(receipt_path.resolve())

    for (arm, _unit), row in final_rows.items():
        receipt_path = _receipt_path(row, repository_root)
        receipt = _load(receipt_path) if receipt_path and receipt_path.is_file() else None
        launch = None
        if row.get("launch_path"):
            launch_path = Path(row["launch_path"])
            launch_path = (
                launch_path if launch_path.is_absolute() else repository_root / launch_path
            )
            launch = _load(launch_path) if launch_path.is_file() else None
        final_phase_counts[arm][_phase(row, receipt, launch)] += 1

    attempted = {
        arm: sum(bool(row.get("attempted")) for (row_arm, _), row in final_rows.items()
                 if row_arm == arm)
        for arm in ARMS
    }
    return {
        "schema": "localization-timing-diagnostics/v1",
        "qualification": (
            "truth-free timing diagnostic; all-attempt ratios are failure-confounded and "
            "must not be used to reward early timeout; accepted pairing requires both arms"
        ),
        "coverage": {
            "planned_units_per_arm": PLANNED_UNITS,
            "attempted_by_arm": attempted,
            "partial": any(attempted[arm] < PLANNED_UNITS for arm in ARMS),
        },
        "primary_phase_counts": {
            arm: {**dict(sorted(phase_counts[arm].items())),
                  "planned_denominator": PLANNED_UNITS}
            for arm in ARMS
        },
        "final_two_stage_phase_counts": {
            arm: {**dict(sorted(final_phase_counts[arm].items())),
                  "planned_denominator": PLANNED_UNITS}
            for arm in ARMS
        },
        "primary_completed_acquisition_seconds": {
            arm: _number_summary(acquisition[arm]) for arm in ARMS
        },
        "optimizer_fit_seconds_sum": {
            arm: float(sum(optimizer[arm])) for arm in ARMS
        },
        "native_cpu_seconds": {
            arm: _number_summary(cpu[arm]) for arm in ARMS
        },
        "all_attempt_paired_runtime": {
            **_paired_runtime(final_rows, accepted_only=False),
            "interpretation": "descriptive_only_failure_confounded",
        },
        "jointly_accepted_paired_runtime": {
            **_paired_runtime(final_rows, accepted_only=True),
            "interpretation": "primary_comparative_runtime_subset",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("primary_evaluator", type=Path)
    parser.add_argument("two_stage_evaluator", type=Path, nargs="?")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = diagnose(args.primary_evaluator, args.two_stage_evaluator)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.write_text(text)


if __name__ == "__main__":
    main()
