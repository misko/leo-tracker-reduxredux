"""Sparse-assisted continuation of every sealed reset-cohort branch."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE_RUN = "finite-set-reset-cohort-v1"
SOURCE_SCHEMA = "finite-set-reset-cohort/v1"
RUN_ID = "finite-set-reset-sparse-continue-v1"
SCHEMA = "finite-set-reset-sparse-continue/v1"
SUPPORTED_UNITS = ("DS10-D02", "DS11-D02", "DS10-Q02", "DS11-Q02")
BRANCH_NAMES = ("baseline_refinement", "fresh_child_refinement")
SPARSE_BUDGET_S = 30.0
DENSE_POLISH_BUDGET_S = 5.0
OBJECTIVE_TOLERANCE = 1e-6
INCUMBENT_TIE_TOLERANCE = 1e-7
PARITY_TOLERANCES = {
    "objective": 1e-6,
    "group_log_likelihood": 1e-6,
    "prediction_gradient": 1e-9,
    "prediction_precision": 1e-10,
    "theoretical_omission_bound": 1e-6,
}
SPARSE_ADAPTER_SHA256 = "27ce9964ce6db071faac1f412a435411ce8a2ce0e5a3edfa078edc22640a32ff"
SPARSE_BENCHMARK_SHA256 = "087e8c0a44a394de27360aa9d8201433dd40216327847f63690ecffd81609625"
SPARSE_BENCHMARK = ROOT / "finite-set-sparse-benchmark-v1.json"
DIRECT_DEPENDENCIES = (
    "alias_family_joint.py",
    "capture_reset_fit.py",
    "capture_reset_gn.py",
    "finite_set_capture_reset.py",
    "finite_set_fit.py",
    "finite_set_grouped_cohort.py",
    "finite_set_likelihood.py",
    "finite_set_reset_cohort.py",
    "finite_set_reset_multistart.py",
    "finite_set_sparse.py",
    "finite_set_sparse_benchmark.py",
    "finite_set_tau_continue.py",
    "gauss_newton.py",
    "joint_inputs.py",
    "prediction_jacobian.py",
    "prediction_plan.py",
    "rough_smoke.py",
    "selection.py",
    "staged_fit.py",
)


def _digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _snapshot_files(paths):
    snapshot = {}
    for path in paths:
        key = str(Path(path).resolve())
        if key not in snapshot:
            snapshot[key] = _digest(key)
    return snapshot


def _assert_snapshot_unchanged(snapshot):
    changed = [path for path, expected in snapshot.items() if _digest(path) != expected]
    if changed:
        raise RuntimeError(f"continuation provenance changed before seal: {', '.join(changed)}")


def source_dependency_paths(source, source_path, *, root=ROOT):
    """Return source, inputs, geometry authorities, validators, and numerical closure."""

    inherited = source.get("source_hashes")
    bound = source.get("bound_input_hashes")
    if not isinstance(inherited, dict) or not isinstance(bound, dict):
        raise ValueError("source lacks inherited or bound input hashes")
    paths = [source_path, upstream_source_path(source, root=root), Path(__file__), SPARSE_BENCHMARK]
    paths.extend(Path(path) for path in inherited)
    paths.extend(Path(path) for path in bound)
    paths.extend(Path(root) / name for name in DIRECT_DEPENDENCIES)
    paths.append(Path(root).parent / "2026_10_02_localization_benchmark" / "bundle.py")
    return tuple(dict.fromkeys(Path(path).resolve() for path in paths))


def upstream_source_path(source, *, root=ROOT):
    run_id = source.get("source_run_id")
    unit_id = source.get("unit", {}).get("unit_id")
    if not isinstance(run_id, str) or not run_id or not isinstance(unit_id, str) or not unit_id:
        raise ValueError("source lacks its upstream run or unit identity")
    return Path(root) / "runs" / run_id / unit_id / "fit.json"


def snapshot_before_validation(source, source_path, *, snapshotter=_snapshot_files):
    return snapshotter(source_dependency_paths(source, source_path))


def _valid_hashes(values):
    return isinstance(values, dict) and bool(values) and all(
        isinstance(path, str)
        and isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
        for path, value in values.items()
    )


def _validate_state(state, bank, capture_count, candidate_count=None):
    parameters = np.asarray(state.get("parameters"), dtype=float)
    jumps = np.asarray(state.get("capture_jumps_hz"), dtype=float)
    satellites = np.asarray(state.get("satellite_indices"), dtype=int)
    weights = np.asarray(state.get("satellite_weights", np.ones(len(bank))), dtype=float)
    if (
        parameters.ndim != 1
        or not len(parameters)
        or np.any(~np.isfinite(parameters))
        or jumps.shape != (capture_count, 2)
        or np.any(~np.isfinite(jumps))
        or not np.array_equal(satellites, bank)
        or weights.shape != bank.shape
        or np.any(~np.isfinite(weights))
        or np.any(weights <= 0)
        or not np.isfinite(state.get("objective", np.nan))
        or not isinstance(state.get("success"), bool)
        or state.get("status") not in {"converged", "nonconverged"}
    ):
        raise ValueError("source reset branch state is malformed")
    if candidate_count is not None and parameters.shape != (6 + candidate_count,):
        raise ValueError("source reset parameters differ from reconstructed candidate count")
    if candidate_count is not None and (np.any(bank < 0) or np.any(bank >= candidate_count)):
        raise ValueError("source reset bank differs from reconstructed candidate indices")
    return parameters, jumps, weights


def validate_source_record(source, unit_id, *, root=ROOT):
    """Require one of the four sealed reset-cohort pilot receipts with both branches."""

    if unit_id not in SUPPORTED_UNITS:
        raise ValueError("unit must be one of the four frozen D02/Q02 pilots")
    unit = source.get("unit")
    expected_size = 2 if "-D" in unit_id else 4
    if (
        source.get("schema") != SOURCE_SCHEMA
        or source.get("run_id") != SOURCE_RUN
        or not isinstance(unit, dict)
        or unit.get("unit_id") != unit_id
        or unit.get("size") != expected_size
        or source.get("dataset") != unit_id[:4]
        or source.get("reference_read_before_seal") is not False
        or source.get("evaluation_written") is not False
        or source.get("sealed") is not True
        or not source.get("sealed_utc")
    ):
        raise ValueError("source must be a sealed truth-free reset-cohort D02/Q02 fit")
    if not _valid_hashes(source.get("source_hashes")) or not _valid_hashes(
        source.get("bound_input_hashes")
    ):
        raise ValueError("source hashes are malformed")
    upstream_key = str(upstream_source_path(source, root=root).resolve())
    upstream_digest = source.get("source_fit_sha256")
    if (
        source.get("source_run_id") != "finite-set-grouped-cohort-v1"
        or not isinstance(upstream_digest, str)
        or len(upstream_digest) != 64
        or source["source_hashes"].get(upstream_key) != upstream_digest
    ):
        raise ValueError("source does not bind its upstream continuous fit exactly")
    fit = source.get("fit")
    if not isinstance(fit, dict):
        raise ValueError("source lacks reset fit")
    expected_model = {
        "optimizer": "complete-data-fisher-capture-reset-gn/v1",
        "refinements_per_bank": 2,
        "budget_s_per_refinement": 15.0,
        "sigma_hz": 200.0,
        "tau_sigma_s": 1.0,
        "tau_bound_s": 3.0,
        "slope_bound_hz_s": 50.0,
    }
    for name, expected in expected_model.items():
        observed = fit.get(name)
        if isinstance(expected, float):
            matches = np.isclose(observed, expected, rtol=0, atol=0)
        else:
            matches = observed == expected
        if not matches:
            raise ValueError(f"source reset model changed {name}")
    full_bank = np.asarray(fit.get("full_bank"), dtype=int)
    attempts = fit.get("attempts")
    trials = fit.get("trials")
    if (
        full_bank.ndim != 1
        or not len(full_bank)
        or len(np.unique(full_bank)) != len(full_bank)
        or not isinstance(attempts, list)
        or not attempts
        or not isinstance(trials, list)
        or len(trials) != len(attempts)
    ):
        raise ValueError("source reset bank ladder is incomplete")
    banks = []
    source_complete = True
    for trial, attempt in zip(trials, attempts, strict=True):
        bank = np.asarray(attempt.get("satellite_indices"), dtype=int)
        if (
            bank.ndim != 1
            or not len(bank)
            or len(np.unique(bank)) != len(bank)
            or not np.array_equal(np.asarray(trial.get("satellite_indices"), dtype=int), bank)
            or attempt.get("satellite_count") != len(bank)
            or attempt.get("selected_multistart_branch")
            not in {"nested_parent", *BRANCH_NAMES}
        ):
            raise ValueError("source reset attempt bank is malformed")
        _validate_state(trial, bank, expected_size)
        nested = attempt.get("nested_parent")
        if (
            not isinstance(nested, dict)
            or set(nested) != {"capture_jumps_hz", "group_count", "objective"}
            or np.asarray(nested.get("capture_jumps_hz"), dtype=float).shape
            != (expected_size, 2)
            or np.any(np.asarray(nested["capture_jumps_hz"], dtype=float) != 0)
            or not isinstance(nested.get("group_count"), int)
            or nested["group_count"] <= 0
            or not np.isfinite(nested.get("objective", np.nan))
        ):
            raise ValueError("source nested parent must use the persisted minimal schema")
        for branch_name in BRANCH_NAMES:
            branch = attempt.get(branch_name)
            _validate_state(branch or {}, bank, expected_size)
            source_complete &= bool(branch["success"])
        if attempt.get("baseline_branch_complete") is not bool(
            attempt["baseline_refinement"]["success"]
        ) or attempt.get("fresh_branch_complete") is not bool(
            attempt["fresh_child_refinement"]["success"]
        ):
            raise ValueError("source branch completion flags differ from branch states")
        banks.append(tuple(int(value) for value in bank))
    if len(set(banks)) != len(banks) or tuple(int(value) for value in full_bank) not in banks:
        raise ValueError("source reset banks are duplicated or omit the full bank")
    if fit.get("all_refinement_branches_complete") is not source_complete:
        raise ValueError("source all-branch completion flag is inconsistent")
    return source


def reconstruct_nested_incumbents(source, upstream, *, retainer=None):
    """Rebuild full reset-model nested incumbents from the bound continuous parent."""

    if retainer is None:
        from finite_set_capture_reset import retained_continuous_incumbent

        retainer = retained_continuous_incumbent
    if (
        upstream.get("schema") != "finite-set-grouped-cohort/v1"
        or upstream.get("run_id") != source["source_run_id"]
        or upstream.get("unit") != source["unit"]
        or upstream.get("dataset") != source["dataset"]
        or not upstream.get("sealed_utc")
        or upstream.get("reference_read_before_seal") is not False
        or upstream.get("evaluation_written") is not False
    ):
        raise ValueError("upstream continuous receipt identity differs from reset source")
    upstream_trials = upstream.get("fit", {}).get("trials")
    if not isinstance(upstream_trials, list) or not upstream_trials:
        raise ValueError("upstream continuous receipt lacks its bank ladder")
    by_bank = {}
    for trial in upstream_trials:
        bank = tuple(trial.get("satellite_indices", ()))
        if not bank or bank in by_bank:
            raise ValueError("upstream continuous banks are empty or duplicated")
        by_bank[bank] = trial
    reconstructed = copy.deepcopy(source["fit"])
    capture_count = source["unit"]["size"]
    for attempt in reconstructed["attempts"]:
        bank = tuple(attempt["satellite_indices"])
        if bank not in by_bank:
            raise ValueError("reset nested bank is absent from upstream continuous fit")
        parent = by_bank[bank]
        nested = attempt["nested_parent"]
        if not np.isclose(parent.get("objective", np.nan), nested["objective"], rtol=0, atol=1e-6):
            raise ValueError("minimal nested objective differs from upstream continuous parent")
        full = retainer(
            parent,
            nested,
            capture_count,
            "nested_continuous_incumbent_reconstructed_from_bound_source",
        )
        if not np.array_equal(np.asarray(full["satellite_indices"], dtype=int), np.asarray(bank)):
            raise ValueError("reconstructed nested incumbent changed its bank")
        attempt["nested_parent"] = full
    reconstructed["nested_incumbents_reconstructed_from_bound_upstream"] = True
    return reconstructed


def validate_sparse_benchmark(receipt, snapshot):
    """Bind the frozen sparse adapter to its sealed no-fit parity benchmark."""

    benchmark_key = str(SPARSE_BENCHMARK.resolve())
    adapter_key = str((ROOT / "finite_set_sparse.py").resolve())
    if (
        receipt.get("schema") != "finite-set-sparse-benchmark/v1"
        or receipt.get("fit_performed") is not False
        or receipt.get("reference_accessed") is not False
        or snapshot.get(benchmark_key) != SPARSE_BENCHMARK_SHA256
        or snapshot.get(adapter_key) != SPARSE_ADAPTER_SHA256
    ):
        raise ValueError("frozen sparse benchmark or adapter digest differs")
    rows = receipt.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("sparse benchmark lacks cases")
    for row in rows:
        if row.get("source_hashes", {}).get(adapter_key) != SPARSE_ADAPTER_SHA256:
            raise ValueError("sparse benchmark case does not bind the frozen adapter")
    return {
        "path": benchmark_key,
        "sha256": SPARSE_BENCHMARK_SHA256,
        "adapter_sha256": SPARSE_ADAPTER_SHA256,
        "case_count": len(rows),
        "fit_performed": False,
        "reference_accessed": False,
    }


def validate_loaded_source(source, unit, dataset, data, input_paths, snapshot, *, serializer):
    """Match the snapshotted selection, exact inputs, geometry, and capture lineage."""

    if unit != source["unit"] or dataset != source["dataset"]:
        raise ValueError("reconstructed selection differs from sealed source")
    expected_inputs = source["bound_input_hashes"]
    actual_paths = {str(Path(path).resolve()) for path in input_paths}
    if actual_paths != set(expected_inputs):
        raise ValueError("loader paths differ from sealed bound inputs")
    if any(snapshot.get(path) != digest for path, digest in expected_inputs.items()):
        raise ValueError("snapshotted loader inputs differ from sealed hashes")
    if serializer(data.geometry_receipt) != source.get("geometry_receipt"):
        raise ValueError("reconstructed geometry differs from sealed source")
    sessions = tuple(source["unit"].get("session_ids", ()))
    if tuple(data.child_sessions) != sessions:
        raise ValueError("reconstructed capture lineage differs from sealed source")
    for trial, attempt in zip(source["fit"]["trials"], source["fit"]["attempts"], strict=True):
        bank = np.asarray(attempt["satellite_indices"], dtype=int)
        _validate_state(trial, bank, len(sessions), len(data.numbers))
        for branch_name in BRANCH_NAMES:
            _validate_state(attempt[branch_name], bank, len(sessions), len(data.numbers))
    return {
        "bound_input_hashes": dict(expected_inputs),
        "geometry_receipt": serializer(data.geometry_receipt),
        "capture_count": len(sessions),
    }


def evaluate_likelihood_pair(data, state, satellites, dense, sparse=None, *, plan=None):
    """Evaluate one reset state densely and optionally with the packed approximation."""

    from capture_reset_gn import apply_capture_offsets
    from prediction_plan import SharedPredictionPlan

    satellites = np.asarray(satellites, dtype=int)
    parameters = np.asarray(state["parameters"], dtype=float)
    jumps = np.asarray(state["capture_jumps_hz"], dtype=float)
    plan = SharedPredictionPlan(data, satellites) if plan is None else plan
    predicted, visible, _ = plan.predict(parameters)
    shape = (len(data.times), len(satellites))
    predicted = apply_capture_offsets(
        data,
        np.asarray(predicted).reshape(shape),
        jumps,
        len(satellites),
    )
    visible = np.asarray(visible).reshape(shape)
    weights = np.asarray(state.get("satellite_weights", np.ones(len(satellites))), dtype=float)
    options = {
        "sigma_hz": 200.0,
        "satellite_weights": weights,
        "background_mass": 0.2,
        "return_gradient": True,
        "return_precision": True,
    }
    dense_result = dense.evaluate(predicted, visible, **options)
    prior = 0.5 * float(np.sum(parameters[6 + satellites] ** 2))
    receipt = {
        "dense_objective": float(-dense_result["total_log_likelihood"] + prior),
        "dense_total_log_likelihood": float(dense_result["total_log_likelihood"]),
        "tau_prior_objective": prior,
    }
    if sparse is None:
        return receipt
    sparse_result = sparse.evaluate(predicted, visible, **options)
    receipt.update(
        sparse_objective=float(-sparse_result["total_log_likelihood"] + prior),
        sparse_total_log_likelihood=float(sparse_result["total_log_likelihood"]),
        observed_total_log_likelihood_roundoff_difference=float(
            dense_result["total_log_likelihood"] - sparse_result["total_log_likelihood"]
        ),
        observed_objective_roundoff_difference=float(
            -dense_result["total_log_likelihood"] + sparse_result["total_log_likelihood"]
        ),
        maximum_absolute_group_log_likelihood_difference=float(
            np.max(np.abs(dense_result["log_likelihood"] - sparse_result["log_likelihood"]))
        ),
        maximum_absolute_prediction_gradient_difference=float(
            np.max(
                np.abs(
                    dense_result["prediction_gradient"]
                    - sparse_result["prediction_gradient"]
                )
            )
        ),
        maximum_absolute_prediction_precision_difference=float(
            np.max(
                np.abs(
                    dense_result["prediction_precision"]
                    - sparse_result["prediction_precision"]
                )
            )
        ),
        theoretical_omission_log_likelihood_upper_bound=float(
            sparse_result["total_omitted_log_likelihood_upper_bound"]
        ),
        packed_satellite_count=int(sparse_result["packed_satellite_count"]),
        retained_satellite_count_min=int(
            np.min(sparse_result["retained_satellite_count_per_group"])
        ),
        retained_satellite_count_max=int(
            np.max(sparse_result["retained_satellite_count_per_group"])
        ),
        parity_scope=(
            "The omission bound is an exact-arithmetic model bound; observed dense/sparse "
            "differences also contain floating evaluation-order roundoff."
        ),
    )
    receipt.update(assess_sparse_parity(receipt))
    return receipt


def assess_sparse_parity(receipt):
    """Apply fixed numerical tolerances without conflating roundoff and omission bounds."""

    checks = {
        "objective": abs(receipt["observed_objective_roundoff_difference"]),
        "group_log_likelihood": receipt[
            "maximum_absolute_group_log_likelihood_difference"
        ],
        "prediction_gradient": receipt[
            "maximum_absolute_prediction_gradient_difference"
        ],
        "prediction_precision": receipt[
            "maximum_absolute_prediction_precision_difference"
        ],
        "theoretical_omission_bound": receipt[
            "theoretical_omission_log_likelihood_upper_bound"
        ],
    }
    failures = [
        name
        for name, value in checks.items()
        if not np.isfinite(value) or value > PARITY_TOLERANCES[name]
    ]
    return {
        "parity_tolerances": dict(PARITY_TOLERANCES),
        "parity_observed_absolute": {name: float(value) for name, value in checks.items()},
        "parity_failures": failures,
        "parity_within_tolerance": not failures,
    }


def _same_state(left, right):
    return np.array_equal(left["parameters"], right["parameters"]) and np.array_equal(
        left["capture_jumps_hz"], right["capture_jumps_hz"]
    )


def choose_incumbent(candidates, *, score_field="objective", tolerance=INCUMBENT_TIE_TOLERANCE):
    """Choose lower score, preferring convergence only inside the declared tie tolerance."""

    if not candidates:
        raise ValueError("at least one incumbent candidate is required")
    best_name, best = candidates[0]
    if not np.isfinite(best.get(score_field, np.nan)):
        raise ValueError("incumbent score must be finite")
    for name, candidate in candidates[1:]:
        score = candidate.get(score_field, np.nan)
        if not np.isfinite(score):
            raise ValueError("incumbent score must be finite")
        difference = float(score - best[score_field])
        if difference < -tolerance or (
            abs(difference) <= tolerance
            and candidate.get("success") is True
            and best.get("success") is not True
        ):
            best_name, best = name, candidate
    return best_name, copy.deepcopy(best)


def _validate_penalty(candidate, source):
    observed = candidate.get("model_penalty", {}).get("total_penalty")
    expected = source.get("model_penalty", {}).get("total_penalty")
    if not np.isclose(observed, expected, rtol=0, atol=1e-9):
        raise ValueError("continuation changed the reset-model penalty")


def _continue_branch(
    data,
    source,
    satellites,
    support,
    dense,
    sparse,
    plan,
    *,
    refiner,
    evaluator,
):
    source_parity = evaluator(
        data, source, satellites, dense, sparse, plan=plan
    )
    if not np.isclose(
        source_parity["dense_objective"], source["objective"], rtol=0, atol=OBJECTIVE_TOLERANCE
    ):
        raise ValueError("dense preflight does not reproduce sealed branch objective")
    sparse_attempt = refiner(
        data,
        np.asarray(source["parameters"], dtype=float).copy(),
        np.asarray(source["capture_jumps_hz"], dtype=float).copy(),
        satellites,
        support.copy(),
        sparse,
        sigma_hz=200.0,
        tau_sigma_s=1.0,
        tau_bound_s=3.0,
        slope_bound_hz_s=50.0,
        budget_s=SPARSE_BUDGET_S,
    )
    if not np.isclose(
        sparse_attempt["initial_objective"],
        source_parity["sparse_objective"],
        rtol=0,
        atol=OBJECTIVE_TOLERANCE,
    ):
        raise ValueError("sparse continuation does not reproduce its sealed initializer")
    if sparse_attempt["objective"] > sparse_attempt["initial_objective"] + OBJECTIVE_TOLERANCE:
        raise ValueError("sparse continuation lost its own initializer")
    _validate_penalty(sparse_attempt, source)
    final_parity = evaluator(
        data, sparse_attempt, satellites, dense, sparse, plan=plan
    )
    if not np.isclose(
        final_parity["sparse_objective"],
        sparse_attempt["objective"],
        rtol=0,
        atol=OBJECTIVE_TOLERANCE,
    ):
        raise ValueError("sparse terminal state does not reproduce its sparse objective")
    dense_polish = refiner(
        data,
        np.asarray(sparse_attempt["parameters"], dtype=float).copy(),
        np.asarray(sparse_attempt["capture_jumps_hz"], dtype=float).copy(),
        satellites,
        support.copy(),
        dense,
        sigma_hz=200.0,
        tau_sigma_s=1.0,
        tau_bound_s=3.0,
        slope_bound_hz_s=50.0,
        budget_s=DENSE_POLISH_BUDGET_S,
    )
    if not np.isclose(
        dense_polish["initial_objective"],
        final_parity["dense_objective"],
        rtol=0,
        atol=OBJECTIVE_TOLERANCE,
    ):
        raise ValueError("dense polish does not reproduce the sparse terminal state densely")
    if dense_polish["objective"] > dense_polish["initial_objective"] + OBJECTIVE_TOLERANCE:
        raise ValueError("dense polish lost its dense initializer")
    _validate_penalty(dense_polish, source)
    selected_name, selected = choose_incumbent(
        (("sealed_source_branch", source), ("dense_polish", dense_polish))
    )
    parity_resolved = bool(
        source_parity.get("parity_within_tolerance")
        and final_parity.get("parity_within_tolerance")
    )
    dense_success_before_parity_gate = bool(selected["success"])
    if not parity_resolved:
        selected.update(
            success=False,
            status="nonconverged",
            message="dense_sparse_parity_tolerance_exceeded",
            convergence_reason="dense_sparse_parity_tolerance_exceeded",
        )
    selected.update(
        source_branch_objective=float(source["objective"]),
        source_branch_success=bool(source["success"]),
        selected_branch_incumbent=selected_name,
        selected_state_changed_from_source=not _same_state(selected, source),
        dense_stationarity_checked=True,
        convergence_provenance=(
            "sealed_dense_source_status"
            if selected_name == "sealed_source_branch"
            else "dense_polish_terminal_status"
        ),
        sparse_success_not_used_for_endstate=True,
        sparse_dense_parity_resolved=parity_resolved,
        dense_success_before_parity_gate=dense_success_before_parity_gate,
    )
    return selected, {
        "source_branch": copy.deepcopy(source),
        "dense_source_parity": source_parity,
        "sparse_gn": sparse_attempt,
        "dense_sparse_terminal_parity": final_parity,
        "dense_polish": dense_polish,
        "selected_branch_incumbent": selected_name,
        "selected_state_changed_from_source": not _same_state(selected, source),
        "endstate_success_dense_checked_only": bool(selected["success"]),
        "sparse_dense_parity_resolved": parity_resolved,
        "dense_success_before_parity_gate": dense_success_before_parity_gate,
        "sparse_budget_s": SPARSE_BUDGET_S,
        "dense_polish_budget_s": DENSE_POLISH_BUDGET_S,
    }


def _bank_selection(trials, all_branches_converged):
    winner_name, winner = choose_incumbent(
        [(str(index), trial) for index, trial in enumerate(trials)],
        score_field="selection_score",
    )
    successful = [(str(index), trial) for index, trial in enumerate(trials) if trial["success"]]
    converged = (
        choose_incumbent(successful, score_field="selection_score")[1]
        if successful
        else None
    )
    bank_endstates_converged = all(trial["success"] for trial in trials)
    resolved = bool(all_branches_converged and bank_endstates_converged)
    return {
        "winner": winner,
        "score_leader": winner,
        "score_leader_bank_index": int(winner_name),
        "converged_leader": converged,
        "selection_resolved": resolved,
        "success": resolved,
        "all_branch_endstates_converged": bool(all_branches_converged),
        "all_bank_endstates_converged": bool(bank_endstates_converged),
    }


def continue_reset_sparse_branches(
    data,
    source_fit,
    *,
    dense_factory=None,
    sparse_factory=None,
    refiner=None,
    evaluator=evaluate_likelihood_pair,
    plan_factory=None,
):
    """Continue both sealed multistart branches independently for every source bank."""

    if dense_factory is None:
        from finite_set_fit import build_likelihood_arms

        dense_factory = lambda selected, full: build_likelihood_arms(  # noqa: E731
            data, selected, full
        )["finite_set"]
    if sparse_factory is None:
        from finite_set_sparse import SparseFiniteSetLikelihoodAdapter

        sparse_factory = lambda dense: SparseFiniteSetLikelihoodAdapter(  # noqa: E731
            dense.prepared,
            dense.detection_probability,
            clutter_rate=dense.clutter_rate,
        )
    if refiner is None:
        from capture_reset_gn import refine_capture_reset_gauss_newton

        refiner = refine_capture_reset_gauss_newton
    if plan_factory is None:
        from prediction_plan import SharedPredictionPlan

        plan_factory = SharedPredictionPlan

    full_bank = np.asarray(source_fit["full_bank"], dtype=int)
    source_trials = source_fit["trials"]
    source_attempts = source_fit["attempts"]
    trials = []
    attempts = []
    all_branch_endstates = []
    for source_trial, source_attempt in zip(source_trials, source_attempts, strict=True):
        satellites = np.asarray(source_attempt["satellite_indices"], dtype=int)
        dense = dense_factory(len(satellites), len(full_bank))
        sparse = sparse_factory(dense)
        plan = plan_factory(data, satellites)
        branch_endstates = {}
        branch_attempts = {}
        for branch_name in BRANCH_NAMES:
            source_branch = source_attempt[branch_name]
            support = np.asarray(source_branch["satellite_weights"], dtype=float)
            branch_endstates[branch_name], branch_attempts[branch_name] = _continue_branch(
                data,
                source_branch,
                satellites,
                support,
                dense,
                sparse,
                plan,
                refiner=refiner,
                evaluator=evaluator,
            )
            all_branch_endstates.append(bool(branch_endstates[branch_name]["success"]))

        nested = copy.deepcopy(source_attempt["nested_parent"])
        nested_parity = evaluator(data, nested, satellites, dense, None, plan=plan)
        if not np.isclose(
            nested_parity["dense_objective"], nested["objective"], rtol=0, atol=OBJECTIVE_TOLERANCE
        ):
            raise ValueError("dense preflight does not reproduce nested source incumbent")
        selected_source = copy.deepcopy(source_trial)
        selected_parity = evaluator(data, selected_source, satellites, dense, None, plan=plan)
        if not np.isclose(
            selected_parity["dense_objective"],
            selected_source["objective"],
            rtol=0,
            atol=OBJECTIVE_TOLERANCE,
        ):
            raise ValueError("dense preflight does not reproduce selected source incumbent")
        selected_name, trial = choose_incumbent(
            (
                ("source_nested_parent", nested),
                ("source_selected_trial", selected_source),
                ("baseline_branch_endstate", branch_endstates["baseline_refinement"]),
                ("fresh_branch_endstate", branch_endstates["fresh_child_refinement"]),
            )
        )
        trial.update(
            selected_sparse_continuation_incumbent=selected_name,
            source_selected_multistart_branch=source_attempt["selected_multistart_branch"],
            source_selected_objective=float(source_trial["objective"]),
            global_incumbents_compared_by_dense_objective=True,
            incumbent_tie_tolerance=INCUMBENT_TIE_TOLERANCE,
            sparse_success_never_inherited=True,
        )
        trials.append(trial)
        attempts.append(
            {
                "satellite_indices": satellites,
                "satellite_count": len(satellites),
                "source_nested_parent": nested,
                "source_nested_dense_parity": nested_parity,
                "source_selected_trial": selected_source,
                "source_selected_dense_parity": selected_parity,
                "baseline_refinement": branch_attempts["baseline_refinement"],
                "fresh_child_refinement": branch_attempts["fresh_child_refinement"],
                "selected_incumbent": selected_name,
                "selected_objective": float(trial["objective"]),
                "selected_success": bool(trial["success"]),
                "all_branch_attempts_recorded": True,
            }
        )
    all_branches_converged = all(all_branch_endstates)
    selection = _bank_selection(trials, all_branches_converged)
    return {
        "full_bank": full_bank,
        "trials": trials,
        "attempts": attempts,
        "selection": selection,
        "all_branch_endstates_converged": all_branches_converged,
        "source_bank_order_preserved": True,
        "source_trial_count": len(source_trials),
        "branches_per_bank": len(BRANCH_NAMES),
        "sparse_budget_s_per_branch": SPARSE_BUDGET_S,
        "dense_polish_budget_s_per_branch": DENSE_POLISH_BUDGET_S,
        "sigma_hz": 200.0,
        "tau_sigma_s": 1.0,
        "tau_bound_s": 3.0,
        "slope_bound_hz_s": 50.0,
        "scope": (
            "Every sealed baseline and fresh reset branch continues independently from its own "
            "last state with one sparse 30-second GN pass and one dense 5-second GN polish. "
            "Dense source reproduction and sparse-terminal objective/gradient/precision parity "
            "are recorded. Source, nested, selected, and continued incumbents are compared only "
            "by dense objective; convergence comes only from a sealed dense source status or the "
            "new dense polish. Selection remains unresolved unless every branch and selected bank "
            "endstate converges."
        ),
    }


def run_unit(unit_id):
    if unit_id not in SUPPORTED_UNITS:
        raise ValueError("unit must be one of the four frozen D02/Q02 pilots")
    output = ROOT / "runs" / RUN_ID / unit_id
    if output.exists():
        raise FileExistsError(output)
    source_path = ROOT / "runs" / SOURCE_RUN / unit_id / "fit.json"
    started = time.monotonic()
    snapshot = None
    try:
        source_bytes = source_path.read_bytes()
        source = json.loads(source_bytes)
        snapshot = snapshot_before_validation(source, source_path)
        if snapshot[str(source_path.resolve())] != hashlib.sha256(source_bytes).hexdigest():
            raise RuntimeError("source changed while assembling prevalidation closure")
        source = validate_source_record(source, unit_id)
        benchmark = validate_sparse_benchmark(
            json.loads(SPARSE_BENCHMARK.read_text()), snapshot
        )
        if any(snapshot.get(path) != digest for path, digest in source["source_hashes"].items()):
            raise ValueError("inherited source hashes differ before validation")

        from alias_family_joint import load_unit_with_family_exports
        from finite_set_capture_reset import _find_unit, validate_group_capture_rx
        from rough_smoke import serializable

        upstream_path = upstream_source_path(source)
        upstream = json.loads(upstream_path.read_text())
        if snapshot.get(str(upstream_path.resolve())) != source["source_fit_sha256"]:
            raise ValueError("snapshotted upstream fit differs from source binding")
        selection = json.loads((ROOT / "selection.json").read_text())
        dataset, unit = _find_unit(selection, unit_id)
        exports = ROOT / "runs" / "alias-family-cohort-v1"
        manifest_key = str((exports / "manifest.json").resolve())
        expected_manifest = source["bound_input_hashes"].get(manifest_key)
        if expected_manifest is None:
            raise ValueError("source does not bind alias-family manifest")
        _, data, input_paths = load_unit_with_family_exports(
            unit_id,
            exports,
            expected_manifest_sha256=expected_manifest,
        )
        binding = validate_loaded_source(
            source,
            unit,
            dataset,
            data,
            input_paths,
            snapshot,
            serializer=serializable,
        )
        group_validation = validate_group_capture_rx(data)
        if group_validation != source["fit"].get("group_capture_rx_validation"):
            raise ValueError("reconstructed capture/group validation differs from source")
        source_fit = reconstruct_nested_incumbents(source, upstream)
        for attempt in source_fit["attempts"]:
            bank = np.asarray(attempt["satellite_indices"], dtype=int)
            _validate_state(
                attempt["nested_parent"],
                bank,
                len(data.child_sessions),
                len(data.numbers),
            )
        fitted = continue_reset_sparse_branches(data, source_fit)
        _assert_snapshot_unchanged(snapshot)
    except Exception as error:
        output.mkdir(parents=True, exist_ok=False)
        failure = {
            "schema": SCHEMA,
            "run_id": RUN_ID,
            "unit_id": unit_id,
            "error_type": type(error).__name__,
            "error": str(error),
            "elapsed_s": time.monotonic() - started,
            "source_hashes": snapshot,
            "reference_read_before_seal": False,
            "evaluation_written": False,
            "sealed": True,
            "sealed_utc": datetime.now(UTC).isoformat(),
        }
        with (output / "failure.json").open("x") as stream:
            json.dump(failure, stream, indent=2, allow_nan=False)
        raise
    result = {
        "schema": SCHEMA,
        "run_id": RUN_ID,
        "unit": source["unit"],
        "dataset": source["dataset"],
        "source_run_id": SOURCE_RUN,
        "source_fit_sha256": _digest(source_path),
        "source_hashes": snapshot,
        "inherited_source_hashes": source["source_hashes"],
        "bound_input_hashes": binding["bound_input_hashes"],
        "geometry_receipt": binding["geometry_receipt"],
        "group_capture_rx_validation": group_validation,
        "sparse_benchmark": benchmark,
        "limits": {
            "sparse_budget_s_per_branch": SPARSE_BUDGET_S,
            "dense_polish_budget_s_per_branch": DENSE_POLISH_BUDGET_S,
            "branches_per_bank": len(BRANCH_NAMES),
            "numerical_threads": 1,
        },
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "eligible_for_cohort": False,
        "fit": fitted,
        "elapsed_s": time.monotonic() - started,
        "sealed": True,
        "sealed_utc": datetime.now(UTC).isoformat(),
    }
    output.mkdir(parents=True, exist_ok=False)
    fit_path = output / "fit.json"
    with fit_path.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"unit_id": unit_id, "output": str(fit_path), "sha256": _digest(fit_path)}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit", required=True, choices=SUPPORTED_UNITS)
    return parser.parse_args(argv)


if __name__ == "__main__":
    arguments = parse_args()
    print(json.dumps(run_unit(arguments.unit)))


__all__ = [
    "SUPPORTED_UNITS",
    "choose_incumbent",
    "continue_reset_sparse_branches",
    "evaluate_likelihood_pair",
    "parse_args",
    "run_unit",
    "snapshot_before_validation",
    "source_dependency_paths",
    "validate_loaded_source",
    "validate_source_record",
    "validate_sparse_benchmark",
]
