#!/usr/bin/env python3
"""Fit one donor age-scale arm and evaluate frozen held transfer."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.optimize import minimize_scalar

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DONOR = ROOT / "reports/2026_09_29_donor_residual_transfer"
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as fast  # noqa: E402
from age_scale import ProfiledCases, log_density, scale_from_age  # noqa: E402


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_preflight_sources(bindings):
    checked = 0
    for section in ("source_sha256", "runtime_sha256"):
        for name, expected in bindings[section].items():
            path = Path(name)
            if not path.is_absolute():
                path = ROOT / path
            if digest(path) != expected.removeprefix("sha256:"):
                raise ValueError(f"bound preflight source changed: {path}")
            checked += 1
    return checked


def load_rows(plan, bindings):
    bound = {
        (row["unit_id"], row["session_id"], row["track_id"], int(row["number"])): row
        for row in bindings["rows"]
    }
    if len(bound) != len(bindings["rows"]):
        raise ValueError("duplicate exact age binding")
    rows, paths = [], []
    for unit in plan["units"]:
        path = DONOR / "runs" / unit["unit_id"] / "result.json"
        document = json.loads(path.read_text())
        paths.append(path)
        for case in document["cases"]:
            key = (unit["unit_id"], case["session_id"], case["track_id"], int(case["number"]))
            binding = bound.pop(key)
            if binding["role"] != unit["role"] or binding["dataset"] != unit["unit_id"][:3]:
                raise ValueError("age binding role or dataset mismatch")
            row = dict(case)
            row.update(dataset=binding["dataset"], age_days=binding["age_days"],
                       element_sha256=binding["element_sha256"])
            rows.append(row)
    if bound or len(rows) != 13951:
        raise ValueError("age binding and residual coverage differ")
    return rows, paths


def baseline_parity(rows, cases):
    ours = cases.profile(np.full(len(rows), 100.0))
    offset_difference = score_difference = 0.0
    groups = defaultdict(list)
    for index, mask in enumerate(cases.masks):
        groups[int(mask.sum())].append(index)
    for indices in groups.values():
        values = np.stack([cases.residuals[i][cases.masks[i]] for i in indices])
        mask = np.ones(values.shape[1], dtype=bool)
        scores, _, audits, offsets = fast.profile(values, mask)
        if not all(audit["converged"] for audit in audits):
            raise RuntimeError("baseline fixed100 offset failed stationarity")
        local_ours = ours[indices]
        local_scores = np.asarray([
            float(log_density(values[j:j+1], np.asarray([local_ours[j]]), np.asarray([100.0])).sum())
            - 0.5 * local_ours[j] ** 2 / 1e12
            for j in range(len(indices))
        ])
        offset_difference = max(offset_difference, float(np.max(abs(offsets - local_ours))))
        score_difference = max(score_difference, float(np.max(abs(scores - local_scores))))
    if offset_difference > 1e-9 or score_difference > 1e-9:
        raise ValueError(f"fixed100 profile parity failed: {offset_difference} {score_difference}")
    return dict(maximum_offset_difference_hz=offset_difference,
                maximum_training_score_difference=score_difference)


def fit_parameter(name, objective, bounds):
    result = minimize_scalar(lambda value: -objective(value), method="bounded", bounds=bounds,
                             options=dict(xatol=1e-6, maxiter=60))
    value = float(result.x)
    width = bounds[1] - bounds[0]
    step1 = max(width * 1e-6, 1e-4)
    step2 = step1 * 0.5
    derivative1 = (objective(value + step1) - objective(value - step1)) / (2 * step1)
    derivative2 = (objective(value + step2) - objective(value - step2)) / (2 * step2)
    margin = min(value - bounds[0], bounds[1] - value)
    qualified = bool(
        result.success and np.isfinite([value, result.fun, derivative1, derivative2]).all()
        and margin >= width * 1e-4 and abs(derivative1) <= 1e-6
        and abs(derivative1 - derivative2) <= 1e-5
    )
    return dict(name=name, value=value, objective=float(-result.fun), success=bool(result.success),
                message=str(result.message), nfev=int(result.nfev), bounds=list(bounds),
                boundary_margin=margin, derivative=float(derivative1),
                derivative_audit_difference=float(abs(derivative1 - derivative2)),
                qualified=qualified)


def source_scores(rows, values):
    grouped = defaultdict(list)
    for row, value in zip(rows, values, strict=True):
        key = (row["dataset"], row["session_id"], int(row["number"]), float(row["rf_hz"]))
        grouped[key].append(float(value))
    return {key: float(np.mean(group)) for key, group in grouped.items()}


def comparison(rows, weights, age_score, other_score):
    delta = np.asarray(age_score) - np.asarray(other_score)
    result = {}
    for dataset in ("DS7", "DS8", "DS9"):
        indices = [i for i, row in enumerate(rows) if row["dataset"] == dataset]
        subset = [rows[i] for i in indices]
        local_weights = weights[indices]
        local_weights = local_weights / local_weights.sum()
        result[dataset] = dict(cases=len(indices), scans=len({row["session_id"] for row in subset}),
                               held_gain=float(local_weights @ delta[indices]))
    age_sources = source_scores(rows, age_score)
    other_sources = source_scores(rows, other_score)
    if age_sources.keys() != other_sources.keys():
        raise ValueError("paired source coverage differs")
    wins = sum(age_sources[key] > other_sources[key] for key in age_sources)
    return dict(datasets=result, source_occasions=len(age_sources), source_wins=wins,
                source_losses=sum(age_sources[key] < other_sources[key] for key in age_sources),
                source_ties=sum(age_sources[key] == other_sources[key] for key in age_sources),
                all_datasets_positive=all(row["held_gain"] > 0 for row in result.values()),
                majority_source_wins=wins > len(age_sources) / 2)


def main():
    started = time.monotonic()
    plan_path = DONOR / "plan.json"
    binding_path = HERE / "age-bindings.json"
    plan = json.loads(plan_path.read_text())
    bindings = json.loads(binding_path.read_text())
    if bindings["schema"] != "ds11-age-scale-exact-bindings/v1" or bindings["status"] != "preflight_passed":
        raise ValueError("exact age preflight is absent or failed")
    verified_preflight_sources = verify_preflight_sources(bindings)
    rows, case_paths = load_rows(plan, bindings)
    donor_rows = [row for row in rows if row["role"] == "donor"]
    target_rows = [row for row in rows if row["role"] == "target"]
    if len(donor_rows) != 9968 or len(target_rows) != 3983:
        raise ValueError("unexpected calibration or transfer coverage")
    donors = ProfiledCases.from_rows(donor_rows)
    targets = ProfiledCases.from_rows(target_rows)
    parity = dict(donor=baseline_parity(donor_rows, donors), target=baseline_parity(target_rows, targets))

    age_cache, constant_cache = {}, {}
    def age_objective(k):
        key = float(k)
        if key not in age_cache:
            age_cache[key] = donors.training_objective(scale_from_age(donors.ages, key))[0]
        return age_cache[key]
    def constant_objective(sigma):
        key = float(sigma)
        if key not in constant_cache:
            constant_cache[key] = donors.training_objective(np.full(len(donor_rows), key))[0]
        return constant_cache[key]

    age_fit = fit_parameter("k_hz_per_day", age_objective, (0.0, 2000.0))
    constant_fit = fit_parameter("constant_sigma_hz", constant_objective, (10.0, 5000.0))
    age_scales = scale_from_age(targets.ages, age_fit["value"])
    fixed_scales = np.full(len(target_rows), 100.0)
    constant_scales = np.full(len(target_rows), constant_fit["value"])
    age_held, _ = targets.held_scores(age_scales)
    fixed_held, _ = targets.held_scores(fixed_scales)
    constant_held, _ = targets.held_scores(constant_scales)
    versus_fixed = comparison(target_rows, targets.weights, age_held, fixed_held)
    versus_constant = comparison(target_rows, targets.weights, age_held, constant_held)
    gate = bool(age_fit["qualified"] and constant_fit["qualified"]
                and versus_fixed["all_datasets_positive"] and versus_fixed["majority_source_wins"]
                and versus_constant["all_datasets_positive"] and versus_constant["majority_source_wins"])
    source_paths = [Path(__file__), HERE / "age_scale.py", HERE / "AGE_SCALE_PROTOCOL.md",
                    HERE / "test_age_scale.py", plan_path, binding_path, *case_paths,
                    ROOT / "tools/ds7_fast_baseline_adapter.py", ROOT / "tools/ds7_baseline_adapter.py"]
    result = dict(
        schema="ds11-donor-age-scale-calibration/v1",
        status="passed" if gate else "failed",
        geographic_fits_run=0,
        ds11_residuals_read=False,
        populations=dict(donor_cases=len(donor_rows), target_cases=len(target_rows),
                         target_scans=len({r["session_id"] for r in target_rows}),
                         target_source_occasions=len(source_scores(target_rows, age_held)),
                         verified_preflight_sources=verified_preflight_sources),
        fixed100_profile_parity=parity,
        fits=dict(age=age_fit, constant=constant_fit,
                  fixed100_donor_objective=age_objective(0.0)),
        target_scale_ranges_hz=dict(age=[float(age_scales.min()), float(age_scales.max())],
                                    fixed100=[100.0, 100.0],
                                    constant=[constant_fit["value"], constant_fit["value"]]),
        held_transfer=dict(age_versus_fixed100=versus_fixed, age_versus_constant=versus_constant),
        advance_gate=gate,
        limitation="Conditional training-MAP identities and exposed fixed target endpoints; finite stationary-root enumeration is not a global-minimum certificate for arbitrary residuals.",
        elapsed_seconds=time.monotonic() - started,
        source_sha256={str(path.relative_to(ROOT)): digest(path) for path in dict.fromkeys(source_paths)},
    )
    output = HERE / "age-calibration.json"
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({key: value for key, value in result.items() if key != "source_sha256"}, indent=2))


if __name__ == "__main__":
    main()
