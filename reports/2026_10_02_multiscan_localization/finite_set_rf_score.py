#!/usr/bin/env python3
"""Truth-free RF-coefficient score diagnostics at sealed finite-set fits."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, build_likelihood_arms
from finite_set_likelihood import circular_residual
from prediction_plan import SharedPredictionPlan

ROOT = Path(__file__).resolve().parent
DEFAULT_RUN_ROOT = ROOT / "runs" / "finite-set-tau-profile-v1"
DEFAULT_GROUPED_ROOT = ROOT / "runs" / "finite-set-grouped-cohort-v1"
DEFAULT_EXPORTS = ROOT / "runs" / "alias-family-cohort-v1"
DEFAULT_OUTPUT = ROOT / "finite-set-rf-score-v1.json"
EXPORT_SHA256 = "8752be16157de6c04e7242e6178d2e9e74725ec3c5eb279e9cbc3eefc43b34b1"
SIGMA_HZ = 200.0
TAU_SIGMA_S = 1.0
TAU_BOUND_S = 3.0
COEFFICIENT_PRIOR_SIGMA_HZ_GHZ = 250.0


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def snapshot(paths):
    return {str(Path(path).resolve()): digest(path) for path in paths}


def jsonable(value):
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def receiver_rf_design(data):
    """Return midpoint-centered Hz/GHz design and immutable center metadata."""

    receiver = np.asarray(data.receiver, dtype=int)
    rf = np.asarray(data.rf, dtype=float)
    if receiver.shape != rf.shape or receiver.ndim != 1 or np.any(~np.isfinite(rf)):
        raise ValueError("receiver and RF vectors must be aligned and finite")
    if np.any((receiver < 0) | (receiver > 1)):
        raise ValueError("receiver values must be zero or one")
    centers = np.empty(2)
    spans = []
    design = np.zeros((len(rf), 2))
    for rx in (0, 1):
        rows = receiver == rx
        if not np.any(rows):
            raise ValueError(f"RX{rx} has no RF observations")
        minimum = float(np.min(rf[rows]))
        maximum = float(np.max(rf[rows]))
        centers[rx] = 0.5 * (minimum + maximum)
        design[rows, rx] = (rf[rows] - centers[rx]) / 1e9
        spans.append(
            {
                "receiver": rx,
                "minimum_rf_hz": minimum,
                "maximum_rf_hz": maximum,
                "center_rf_hz": float(centers[rx]),
                "span_ghz": (maximum - minimum) / 1e9,
            }
        )
    return design, centers, spans


def _weighted_moments(x, y, weights):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if x.shape != y.shape or x.shape != weights.shape:
        raise ValueError("weighted moment inputs must align")
    total = float(np.sum(weights))
    if not np.isfinite(total) or total <= 0:
        return {
            "weight": total,
            "mean_x": None,
            "mean_y": None,
            "rms_y": None,
            "slope_y_per_x": None,
            "correlation": None,
        }
    mean_x = float(np.sum(weights * x) / total)
    mean_y = float(np.sum(weights * y) / total)
    centered_x = x - mean_x
    centered_y = y - mean_y
    xx = float(np.sum(weights * centered_x**2))
    yy = float(np.sum(weights * centered_y**2))
    xy = float(np.sum(weights * centered_x * centered_y))
    slope = None if xx <= 0 else xy / xx
    correlation = None if xx <= 0 or yy <= 0 else xy / math.sqrt(xx * yy)
    return {
        "weight": total,
        "mean_x": mean_x,
        "mean_y": mean_y,
        "rms_y": float(math.sqrt(np.sum(weights * y**2) / total)),
        "slope_y_per_x": slope,
        "correlation": correlation,
    }


def posterior_residual_summaries(data, predicted, result, rf_design):
    """Summarize posterior-associated residuals without assigning hard identities."""

    predicted = np.asarray(predicted, dtype=float)
    association = np.asarray(result["row_association_probability"], dtype=float)
    if predicted.shape != association.shape or predicted.shape[0] != len(data.times):
        raise ValueError("predictions and posterior row association must align")
    residual = circular_residual(
        np.asarray(data.measured, dtype=float)[:, None],
        predicted,
        float(result["alias_hz"]),
    )
    receiver = np.asarray(data.receiver, dtype=int)
    channel = np.asarray(data.channel, dtype=int)
    times = np.asarray(data.times, dtype=float)
    summaries = []
    for rx in (0, 1):
        rows = receiver == rx
        row_weights = np.sum(association[rows], axis=1)
        repeated_rf = np.repeat(rf_design[rows, rx], predicted.shape[1])
        repeated_time = np.repeat(times[rows], predicted.shape[1])
        weights = association[rows].ravel()
        values = residual[rows].ravel()
        rf_moments = _weighted_moments(repeated_rf, values, weights)
        time_moments = _weighted_moments(repeated_time, repeated_rf, weights)
        by_channel = []
        for value in np.unique(channel[rows]):
            channel_rows = rows & (channel == value)
            channel_weights = association[channel_rows].ravel()
            channel_residual = residual[channel_rows].ravel()
            channel_total = float(np.sum(channel_weights))
            by_channel.append(
                {
                    "channel": int(value),
                    "row_count": int(np.sum(channel_rows)),
                    "group_count": int(len(np.unique(np.asarray(data.group)[channel_rows]))),
                    "signal_weight": channel_total,
                    "weighted_residual_mean_hz": None
                    if channel_total <= 0
                    else float(np.sum(channel_weights * channel_residual) / channel_total),
                }
            )
        summaries.append(
            {
                "receiver": rx,
                "row_count": int(np.sum(rows)),
                "group_count": int(len(np.unique(np.asarray(data.group)[rows]))),
                "supported_row_count": int(np.sum(row_weights > 0)),
                "signal_weight": float(np.sum(row_weights)),
                "weighted_residual_mean_hz": rf_moments["mean_y"],
                "weighted_residual_rms_hz": rf_moments["rms_y"],
                "weighted_residual_rf_slope_hz_per_ghz": rf_moments[
                    "slope_y_per_x"
                ],
                "weighted_residual_rf_correlation": rf_moments["correlation"],
                "weighted_rf_time_correlation": time_moments["correlation"],
                "channels": by_channel,
            }
        )
    return summaries


def coefficient_score(evaluator, predicted, visible, rf_design, evaluate_kwargs):
    """Evaluate the exact log-likelihood score at zero RF correction."""

    predicted = np.asarray(predicted, dtype=float)
    visible = np.asarray(visible, dtype=bool)
    rf_design = np.asarray(rf_design, dtype=float)
    if predicted.ndim != 2 or visible.shape != predicted.shape:
        raise ValueError("predicted and visible arrays must be aligned matrices")
    if rf_design.shape != (predicted.shape[0], 2):
        raise ValueError("RF design must provide two receiver coefficient columns")
    result = evaluator.evaluate(
        predicted,
        visible,
        return_gradient=True,
        return_precision=True,
        **evaluate_kwargs,
    )
    prediction_gradient = np.asarray(result["prediction_gradient"], dtype=float)
    prediction_precision = np.asarray(result["prediction_precision"], dtype=float)
    if (
        prediction_gradient.shape != predicted.shape
        or prediction_precision.shape != predicted.shape
    ):
        raise ValueError("likelihood derivative arrays must match predictions")
    if np.any(~np.isfinite(prediction_gradient)) or np.any(~np.isfinite(prediction_precision)):
        raise FloatingPointError("likelihood derivatives must be finite")
    if np.any(prediction_precision < 0):
        raise ValueError("likelihood precision must be nonnegative")
    row_score = np.sum(prediction_gradient, axis=1)
    row_precision = np.sum(prediction_precision, axis=1)
    score = rf_design.T @ row_score
    return {
        "log_likelihood_score_at_zero": score,
        "negative_log_likelihood_gradient_at_zero": -score,
        "row_log_likelihood_score": row_score,
        "row_complete_data_precision": row_precision,
        "likelihood": result,
    }


def nuisance_design(data):
    receiver = np.asarray(data.receiver, dtype=int)
    times = np.asarray(data.times, dtype=float)
    reference = float(getattr(data, "reference_time_s", 150.0))
    result = np.zeros((len(times), 4))
    for rx in (0, 1):
        rows = receiver == rx
        result[rows, 2 * rx] = 1.0
        result[rows, 2 * rx + 1] = times[rows] - reference
    return result, reference


def project_complete_data_fisher(
    rf_design,
    nuisance,
    row_score,
    row_precision,
    *,
    prior_sigma=COEFFICIENT_PRIOR_SIGMA_HZ_GHZ,
):
    """Residualize RF score/information against RX intercept and time columns."""

    rf_design = np.asarray(rf_design, dtype=float)
    nuisance = np.asarray(nuisance, dtype=float)
    row_score = np.asarray(row_score, dtype=float)
    row_precision = np.asarray(row_precision, dtype=float)
    count = len(row_score)
    if (
        rf_design.shape != (count, 2)
        or nuisance.shape != (count, 4)
        or row_precision.shape != (count,)
        or np.any(~np.isfinite(rf_design))
        or np.any(~np.isfinite(nuisance))
        or np.any(~np.isfinite(row_score))
        or np.any(~np.isfinite(row_precision))
        or np.any(row_precision < 0)
    ):
        raise ValueError("Fisher projection inputs are invalid")
    if not np.isfinite(prior_sigma) or prior_sigma <= 0:
        raise ValueError("coefficient prior width must be positive and finite")
    weighted_norm = np.sqrt(np.sum(row_precision[:, None] * nuisance**2, axis=0))
    scales = np.where(weighted_norm > 0, weighted_norm, 1.0)
    scaled_nuisance = nuisance / scales
    nuisance_information = scaled_nuisance.T @ (
        row_precision[:, None] * scaled_nuisance
    )
    cross_information = scaled_nuisance.T @ (row_precision[:, None] * rf_design)
    coefficient_information = rf_design.T @ (row_precision[:, None] * rf_design)
    nuisance_score = scaled_nuisance.T @ row_score
    coefficient_score_value = rf_design.T @ row_score
    inverse = np.linalg.pinv(nuisance_information, rcond=1e-12, hermitian=True)
    projected_score = coefficient_score_value - cross_information.T @ inverse @ nuisance_score
    projected_information = (
        coefficient_information
        - cross_information.T @ inverse @ cross_information
    )
    projected_information = 0.5 * (projected_information + projected_information.T)
    eigenvalues = np.linalg.eigvalsh(projected_information)
    tolerance = max(1.0, float(np.max(np.abs(eigenvalues)))) * 1e-10
    projected_information[np.abs(projected_information) < tolerance] = 0.0
    prior_precision = 1.0 / prior_sigma**2
    information_with_prior = projected_information + prior_precision * np.eye(2)
    standardized = []
    for index in range(2):
        diagonal = information_with_prior[index, index]
        standardized.append(
            None if diagonal <= 0 else float(projected_score[index] / math.sqrt(diagonal))
        )
    positive = eigenvalues[eigenvalues > tolerance]
    condition = None if not len(positive) else float(np.max(positive) / np.min(positive))
    return {
        "exact_unprojected_log_likelihood_score": coefficient_score_value,
        "projected_log_likelihood_score": projected_score,
        "projected_complete_data_information": projected_information,
        "projected_information_plus_prior": information_with_prior,
        "prior_sigma_hz_per_ghz": float(prior_sigma),
        "prior_score_at_zero": [0.0, 0.0],
        "prior_information_per_coefficient": prior_precision,
        "score_over_sqrt_projected_information_plus_prior": standardized,
        "nuisance_rank": int(np.linalg.matrix_rank(nuisance_information, tol=1e-10)),
        "projected_information_eigenvalues": eigenvalues,
        "positive_projected_information_condition": condition,
        "interpretation": (
            "Complete-data/Fisher approximation after profiling only existing RX intercept/time "
            "columns. It omits missing-information, position and satellite-timing projection and "
            "is not a calibrated significance test."
        ),
    }


def _selected_trial(receipt):
    if (
        receipt.get("schema") != "finite-set-tau-profile/v1"
        or receipt.get("reference_read_before_seal") is not False
        or receipt.get("evaluation_written") is not False
        or not receipt.get("sealed_utc")
    ):
        raise ValueError("profile receipt is not sealed and truth-free")
    selection = receipt.get("fit", {}).get("selection", {})
    trial = selection.get("score_leader")
    if not isinstance(trial, dict):
        raise ValueError("profile receipt lacks a score-leading selected trial")
    return trial


def validate_authoritative_bindings(
    authoritative_snapshot,
    input_paths,
    actual_geometry,
    expected_geometry,
):
    """Bind loader inputs and complete geometry to the sealed profile snapshot."""

    if not isinstance(authoritative_snapshot, dict) or not authoritative_snapshot:
        raise ValueError("profile receipt lacks an authoritative source snapshot")
    if any(
        not isinstance(path, str) or not isinstance(value, str)
        for path, value in authoritative_snapshot.items()
    ):
        raise ValueError("profile authoritative source snapshot is malformed")
    assert_snapshot_unchanged(authoritative_snapshot)
    loader_digests = {}
    for path in input_paths:
        resolved = str(Path(path).resolve())
        expected = authoritative_snapshot.get(resolved)
        if expected is None:
            raise ValueError(f"loader input is absent from profile source snapshot: {resolved}")
        actual = digest(path)
        if actual != expected:
            raise RuntimeError(f"loader input differs from profile source snapshot: {resolved}")
        loader_digests[resolved] = actual
    if jsonable(actual_geometry) != expected_geometry:
        raise ValueError("complete loaded geometry differs from sealed grouped geometry")
    return loader_digests


def diagnose_unit(
    unit_id,
    *,
    profile_root=DEFAULT_RUN_ROOT,
    grouped_root=DEFAULT_GROUPED_ROOT,
    exports=DEFAULT_EXPORTS,
    expected_export_sha256=EXPORT_SHA256,
):
    """Evaluate one sealed selected fit and release its numerical arrays."""

    from alias_family_joint import load_unit_with_family_exports

    profile_path = Path(profile_root) / unit_id / "fit.json"
    grouped_path = Path(grouped_root) / unit_id / "fit.json"
    profile = json.loads(profile_path.read_text())
    grouped = json.loads(grouped_path.read_text())
    trial = _selected_trial(profile)
    authoritative_snapshot = profile.get("source_hashes")
    if (
        profile.get("unit", {}).get("unit_id") != unit_id
        or profile.get("source_fit_sha256") != digest(grouped_path)
        or grouped.get("schema") != "finite-set-grouped-cohort/v1"
        or grouped.get("unit", {}).get("unit_id") != unit_id
        or grouped.get("reference_read_before_seal") is not False
        or grouped.get("evaluation_written") is not False
        or not grouped.get("sealed_utc")
    ):
        raise ValueError("profile and grouped source receipts are not bound")
    if not isinstance(authoritative_snapshot, dict) or not authoritative_snapshot:
        raise ValueError("profile receipt lacks authoritative source hashes")
    assert_snapshot_unchanged(authoritative_snapshot)
    original_data, data, input_paths = load_unit_with_family_exports(
        unit_id,
        exports,
        expected_manifest_sha256=expected_export_sha256,
    )
    del original_data
    expected_geometry = grouped.get("fit", {}).get("grouped_geometry", {})
    loader_input_digests = validate_authoritative_bindings(
        authoritative_snapshot,
        input_paths,
        data.geometry_receipt,
        expected_geometry,
    )
    source_paths = [
        Path(__file__).resolve(),
        ROOT / "alias_family_joint.py",
        ROOT / "finite_set_fit.py",
        ROOT / "finite_set_likelihood.py",
        ROOT / "prediction_plan.py",
        ROOT / "prediction_jacobian.py",
        ROOT / "joint_inputs.py",
    ]
    fixed_paths = [*input_paths, profile_path, grouped_path]
    source_before = snapshot(source_paths)
    fixed_before = snapshot(fixed_paths)
    satellites = np.asarray(trial["satellite_indices"], dtype=int)
    parameters = np.asarray(trial["parameters"], dtype=float)
    full_bank = np.asarray(profile["fit"]["full_bank"], dtype=int)
    if (
        parameters.shape != (6 + len(data.numbers),)
        or satellites.ndim != 1
        or not len(satellites)
        or len(np.unique(satellites)) != len(satellites)
        or np.any(satellites < 0)
        or np.any(satellites >= len(data.numbers))
        or np.any(~np.isfinite(parameters))
        or not len(full_bank)
    ):
        raise ValueError("selected trial parameters or bank are invalid")
    arms = build_likelihood_arms(data, len(satellites), len(full_bank))
    evaluator = arms["finite_set"]
    plan = SharedPredictionPlan(data, satellites)
    predicted, visible, _ = plan.predict(parameters)
    predicted = np.asarray(predicted, dtype=float).reshape(len(data.times), len(satellites))
    visible = np.asarray(visible, dtype=bool).reshape(predicted.shape)
    rf_design, centers, spans = receiver_rf_design(data)
    evaluate_kwargs = {
        "sigma_hz": SIGMA_HZ,
        "satellite_weights": np.asarray(trial["satellite_weights"], dtype=float),
        "background_mass": 0.2,
    }
    score = coefficient_score(
        evaluator, predicted, visible, rf_design, evaluate_kwargs
    )
    likelihood = score["likelihood"]
    tau = parameters[6 + satellites]
    tau_prior = 0.5 * float(np.sum((tau / TAU_SIGMA_S) ** 2))
    reproduced_objective = -float(likelihood["total_log_likelihood"]) + tau_prior
    if not np.isclose(reproduced_objective, trial["objective"], rtol=0.0, atol=1e-6):
        raise ValueError("zero-correction evaluation does not reproduce sealed objective")
    nuisance, reference_time = nuisance_design(data)
    fisher = project_complete_data_fisher(
        rf_design,
        nuisance,
        score["row_log_likelihood_score"],
        score["row_complete_data_precision"],
    )
    residuals = posterior_residual_summaries(data, predicted, likelihood, rf_design)
    support = np.asarray(likelihood["satellite_support"], dtype=float)
    at_bound = np.isclose(np.abs(tau), TAU_BOUND_S, rtol=0.0, atol=1e-8)
    candidates = [
        {
            "satellite_index": int(satellite),
            "catalog_number": int(np.asarray(data.numbers)[satellite]),
            "tau_s": float(tau_value),
            "at_timing_bound": bool(bound),
            "posterior_support": float(weight),
        }
        for satellite, tau_value, bound, weight in zip(
            satellites, tau, at_bound, support, strict=True
        )
    ]
    source_after = snapshot(source_paths)
    fixed_after = snapshot(fixed_paths)
    if source_before != source_after or fixed_before != fixed_after:
        raise RuntimeError("RF score sources or sealed inputs changed during evaluation")
    assert_snapshot_unchanged(authoritative_snapshot)
    row_association = np.asarray(likelihood["row_association_probability"], dtype=float)
    result = {
        "unit_id": unit_id,
        "dataset": profile["dataset"],
        "profile_fit_sha256": digest(profile_path),
        "grouped_source_fit_sha256": digest(grouped_path),
        "profile_source_fit_sha256": profile["source_fit_sha256"],
        "sealed_profile_source_hashes": profile.get("source_hashes"),
        "loader_inputs_bound_to_profile_source_hashes": loader_input_digests,
        "source_sha256_pre": source_before,
        "source_sha256_post": source_after,
        "input_sha256_pre": fixed_before,
        "input_sha256_post": fixed_after,
        "inputs_unchanged": True,
        "geometry": {
            "fitted_array_sha256": data.geometry_receipt["fitted_array_sha256"],
            "representative_row_count": len(data.times),
            "group_count": len(np.unique(data.group)),
            "geometry_bound_to_grouped_source": True,
        },
        "selected_fit": {
            "satellite_count": len(satellites),
            "objective": float(trial["objective"]),
            "reproduced_objective": reproduced_objective,
            "selection_score": float(trial["selection_score"]),
            "success": bool(trial["success"]),
            "status": trial["status"],
            "tau_prior": tau_prior,
            "sigma_hz": SIGMA_HZ,
            "detection_probability_per_satellite": float(
                arms["detection_probability"]
            ),
            "clutter_rate": float(evaluator.clutter_rate),
        },
        "rf_design": {
            "formula": "c_rx * (rf_hz - midpoint_rx_hz) / 1e9",
            "centers_hz": centers,
            "spans": spans,
            "coefficient_units": "Hz/GHz",
            "zero_correction_evaluated": True,
        },
        "exact_score": {
            "log_likelihood_score_at_zero": score[
                "log_likelihood_score_at_zero"
            ],
            "negative_log_likelihood_gradient_at_zero": score[
                "negative_log_likelihood_gradient_at_zero"
            ],
            "prior_score_at_zero": [0.0, 0.0],
        },
        "complete_data_fisher_projection": {
            **fisher,
            "nuisance_columns": [
                "rx0_intercept",
                "rx0_time_slope",
                "rx1_intercept",
                "rx1_time_slope",
            ],
            "reference_time_s": reference_time,
        },
        "posterior_residuals": residuals,
        "support": {
            "raw_row_count": len(data.times),
            "group_count": len(likelihood["group_values"]),
            "raw_peak_count": int(np.sum(likelihood["raw_peak_count"])),
            "unique_peak_count": int(np.sum(likelihood["unique_peak_count"])),
            "total_signal_association_weight": float(np.sum(row_association)),
            "expected_clutter_count": float(np.sum(likelihood["expected_clutter_count"])),
            "timing_bound_candidate_count": int(np.sum(at_bound)),
            "timing_bound_candidate_support": float(np.sum(support[at_bound])),
            "timing_bound_support_fraction": None
            if np.sum(support) <= 0
            else float(np.sum(support[at_bound]) / np.sum(support)),
            "candidates": candidates,
        },
        "provenance": {
            "reference_accessed": False,
            "evaluation_artifact_accessed": False,
            "tle_queried": False,
            "iq_read": False,
            "fit_performed": False,
            "coefficient_optimized": False,
        },
        "status": "complete",
    }
    del data, arms, evaluator, plan, predicted, visible, likelihood, score
    return result


def _aggregate_score(units):
    raw_score = np.sum(
        [unit["exact_score"]["log_likelihood_score_at_zero"] for unit in units],
        axis=0,
    )
    projected_score = np.sum(
        [
            unit["complete_data_fisher_projection"]["projected_log_likelihood_score"]
            for unit in units
        ],
        axis=0,
    )
    projected_information = np.sum(
        [
            unit["complete_data_fisher_projection"][
                "projected_complete_data_information"
            ]
            for unit in units
        ],
        axis=0,
    )
    prior_precision = 1.0 / COEFFICIENT_PRIOR_SIGMA_HZ_GHZ**2
    information_with_prior = projected_information + prior_precision * np.eye(2)
    standardized = [
        None
        if information_with_prior[index, index] <= 0
        else float(projected_score[index] / math.sqrt(information_with_prior[index, index]))
        for index in range(2)
    ]
    return {
        "unit_count": len(units),
        "exact_unprojected_log_likelihood_score_sum": raw_score,
        "projected_log_likelihood_score_sum": projected_score,
        "projected_complete_data_information_sum": projected_information,
        "one_shared_prior_information_added_once": prior_precision,
        "score_sum_over_sqrt_information_plus_one_shared_prior": standardized,
        "interpretation": (
            "Conditional summary for one hypothetical shared receiver coefficient across these "
            "units. No coefficient is estimated and this is not calibrated significance."
        ),
    }


def existing_profile_units(profile_root):
    return sorted(
        path.parent.name
        for path in Path(profile_root).glob("DS??-S??/fit.json")
        if path.is_file()
    )


def run(
    unit_ids=None,
    *,
    profile_root=DEFAULT_RUN_ROOT,
    grouped_root=DEFAULT_GROUPED_ROOT,
    exports=DEFAULT_EXPORTS,
    expected_export_sha256=EXPORT_SHA256,
    budget_s=180.0,
    unit_diagnostic=diagnose_unit,
):
    if not np.isfinite(budget_s) or not 0 < budget_s <= 300:
        raise ValueError("diagnostic budget must lie in (0, 300] seconds")
    selected = existing_profile_units(profile_root) if unit_ids is None else sorted(set(unit_ids))
    if not selected:
        raise ValueError("no finalized profile units were selected")
    started = time.monotonic()
    deadline = started + float(budget_s)
    units = []
    failures = []
    for unit_id in selected:
        if time.monotonic() >= deadline:
            failures.append({"unit_id": unit_id, "status": "budget_exhausted"})
            continue
        try:
            units.append(
                unit_diagnostic(
                    unit_id,
                    profile_root=profile_root,
                    grouped_root=grouped_root,
                    exports=exports,
                    expected_export_sha256=expected_export_sha256,
                )
            )
        except Exception as error:
            failures.append(
                {
                    "unit_id": unit_id,
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
    return {
        "schema": "finite-set-rf-zero-score/v1",
        "scope": (
            "Truth-free diagnostic at sealed selected finite-set tau-profile fits. Two "
            "receiver RF coefficient scores are evaluated at zero correction; no coefficient, "
            "position, RX line or satellite timing parameter is fitted."
        ),
        "configuration": {
            "sigma_hz": SIGMA_HZ,
            "coefficient_prior_sigma_hz_per_ghz": COEFFICIENT_PRIOR_SIGMA_HZ_GHZ,
            "rf_center_policy": "midpoint of observed RF span independently per receiver/unit",
            "all_rows_and_alias_family_representatives_retained": True,
        },
        "requested_unit_count": len(selected),
        "complete_unit_count": len(units),
        "failed_unit_count": len(failures),
        "units": units,
        "failures": failures,
        "aggregate": None if not units else _aggregate_score(units),
        "elapsed_s": time.monotonic() - started,
        "budget_s": float(budget_s),
        "limitations": [
            (
                "Posterior-weighted residual summaries are selection-conditioned, not "
                "observations of truth."
            ),
            (
                "Complete-data/Fisher projection is not the observed Hessian and profiles only "
                "existing RX intercept/time columns."
            ),
            (
                "Position, satellite timing, identity uncertainty and common orbit error remain "
                "possible explanations for a nonzero RF score."
            ),
            "No p-values, coefficient estimates or hyperparameter selections are produced.",
        ],
        "provenance": {
            "reference_accessed": False,
            "evaluation_artifact_accessed": False,
            "fit_performed": False,
            "streamed_one_unit_at_a_time": True,
        },
        "sealed": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit", action="append", dest="units")
    parser.add_argument("--profile-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--grouped-root", type=Path, default=DEFAULT_GROUPED_ROOT)
    parser.add_argument("--exports", type=Path, default=DEFAULT_EXPORTS)
    parser.add_argument("--expected-export-sha256", default=EXPORT_SHA256)
    parser.add_argument("--budget-s", type=float, default=180.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    receipt = run(
        args.units,
        profile_root=args.profile_root,
        grouped_root=args.grouped_root,
        exports=args.exports,
        expected_export_sha256=args.expected_export_sha256,
        budget_s=args.budget_s,
    )
    args.output.write_text(
        json.dumps(jsonable(receipt), indent=2, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "requested": receipt["requested_unit_count"],
                "complete": receipt["complete_unit_count"],
                "failed": receipt["failed_unit_count"],
                "elapsed_s": receipt["elapsed_s"],
            }
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "coefficient_score",
    "diagnose_unit",
    "existing_profile_units",
    "nuisance_design",
    "posterior_residual_summaries",
    "project_complete_data_fisher",
    "receiver_rf_design",
    "run",
    "validate_authoritative_bindings",
]
