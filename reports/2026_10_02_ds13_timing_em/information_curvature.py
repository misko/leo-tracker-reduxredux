"""Local information diagnostic at sealed common-RF DS13 optima."""

from __future__ import annotations

import json
import os
import time

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from prepare_scans import ROOT, load_scan
from rf_calibration_diagnostic import CalibrationObjective
from rough_smoke import serializable

SIGMA_HZ = 200.0
BUDGET_S = 40.0
RELATIVE_STEPS = (1.0e-5, 3.0e-6)
EIGENVALUE_RCOND = 1.0e-10
RANK_SENSITIVITY_RCONDS = (1.0e-6, 1.0e-8, 1.0e-10, 1.0e-12)
CHI_SQUARE_2D_95 = 5.991464547107979


def central_gradient_hessian(evaluate, vector, scales, relative_step, validator=None):
    vector = np.asarray(vector, dtype=float)
    scales = np.asarray(scales, dtype=float)
    if (
        vector.ndim != 1
        or scales.shape != vector.shape
        or np.any(~np.isfinite(vector))
        or np.any(~np.isfinite(scales))
        or np.any(scales <= 0.0)
        or not np.isfinite(relative_step)
        or relative_step <= 0.0
    ):
        raise ValueError("invalid central-difference inputs")
    hessian = np.empty((len(vector), len(vector)), dtype=float)
    steps = scales * float(relative_step)
    for column, step in enumerate(steps):
        upper = vector.copy()
        lower = vector.copy()
        upper[column] += step
        lower[column] -= step
        if validator is not None and not (validator(upper) and validator(lower)):
            raise ValueError("central-difference point leaves the feasible domain")
        _upper_value, upper_gradient = evaluate(upper)
        _lower_value, lower_gradient = evaluate(lower)
        upper_gradient = np.asarray(upper_gradient, dtype=float)
        lower_gradient = np.asarray(lower_gradient, dtype=float)
        if (
            upper_gradient.shape != vector.shape
            or lower_gradient.shape != vector.shape
            or np.any(~np.isfinite(upper_gradient))
            or np.any(~np.isfinite(lower_gradient))
        ):
            raise ValueError("central-difference gradient is invalid")
        hessian[:, column] = (upper_gradient - lower_gradient) / (2.0 * step)
    symmetric = 0.5 * (hessian + hessian.T)
    asymmetry = float(
        np.linalg.norm(hessian - hessian.T)
        / max(1.0, np.linalg.norm(symmetric))
    )
    return {
        "relative_step": float(relative_step),
        "physical_steps": steps,
        "raw_hessian": hessian,
        "hessian": symmetric,
        "relative_asymmetry": asymmetry,
    }


def matrix_spectrum(matrix, *, rcond=EIGENVALUE_RCOND):
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("information matrix must be square")
    if np.any(~np.isfinite(matrix)):
        raise ValueError("information matrix must be finite")
    eigenvalues = np.linalg.eigvalsh(0.5 * (matrix + matrix.T))
    spectral_scale = max(1.0, float(np.max(np.abs(eigenvalues), initial=0.0)))
    cutoff = float(rcond * spectral_scale)
    positive = eigenvalues > cutoff
    negative = eigenvalues < -cutoff
    condition = None
    if np.any(positive):
        condition = float(np.max(eigenvalues[positive]) / np.min(eigenvalues[positive]))
    return {
        "eigenvalues": eigenvalues,
        "eigenvalue_cutoff": cutoff,
        "positive_rank": int(np.count_nonzero(positive)),
        "near_zero_count": int(np.count_nonzero(~positive & ~negative)),
        "negative_count": int(np.count_nonzero(negative)),
        "minimum_eigenvalue": float(eigenvalues[0]),
        "maximum_eigenvalue": float(eigenvalues[-1]),
        "positive_condition_number": condition,
        "finite_psd_with_tolerance": bool(not np.any(negative)),
    }


def _positive_pseudoinverse(matrix, spectrum):
    eigenvalues, eigenvectors = np.linalg.eigh(0.5 * (matrix + matrix.T))
    retained = eigenvalues > spectrum["eigenvalue_cutoff"]
    if not np.any(retained):
        return np.zeros_like(matrix)
    basis = eigenvectors[:, retained]
    return (basis / eigenvalues[retained]) @ basis.T


def _position_uncertainty(profile_information, spectrum, nuisance_profile_valid):
    if (
        not nuisance_profile_valid
        or not spectrum["finite_psd_with_tolerance"]
        or spectrum["positive_rank"] != 2
    ):
        return {
            "covariance_km2": None,
            "marginal_standard_errors_km": None,
            "principal_standard_errors_km": None,
            "major_axis_95_km": None,
            "sub_km_marginal_standard_errors": False,
            "sub_km_major_axis_95": False,
        }
    covariance = np.linalg.inv(profile_information)
    covariance = 0.5 * (covariance + covariance.T)
    covariance_eigenvalues = np.linalg.eigvalsh(covariance)
    marginal = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    principal = np.sqrt(np.maximum(covariance_eigenvalues, 0.0))
    major_95 = float(np.sqrt(CHI_SQUARE_2D_95) * np.max(principal))
    return {
        "covariance_km2": covariance,
        "marginal_standard_errors_km": marginal,
        "principal_standard_errors_km": principal,
        "major_axis_95_km": major_95,
        "sub_km_marginal_standard_errors": bool(np.all(marginal < 1.0)),
        "sub_km_major_axis_95": bool(major_95 < 1.0),
    }


def profile_position_information(hessian, scales=None, *, rcond=EIGENVALUE_RCOND):
    hessian = np.asarray(hessian, dtype=float)
    if hessian.ndim != 2 or hessian.shape[0] != hessian.shape[1] or len(hessian) < 3:
        raise ValueError("Hessian must include two position and nuisance parameters")
    symmetric = 0.5 * (hessian + hessian.T)
    if scales is None:
        scales = np.ones(len(hessian))
    scales = np.asarray(scales, dtype=float)
    if (
        scales.shape != (len(hessian),)
        or np.any(~np.isfinite(scales))
        or np.any(scales <= 0)
    ):
        raise ValueError("information scales must be positive and match the Hessian")
    position = symmetric[:2, :2]
    cross = symmetric[:2, 2:]
    nuisance = symmetric[2:, 2:]
    nuisance_scales = scales[2:]
    scaled_nuisance = nuisance_scales[:, None] * nuisance * nuisance_scales[None, :]
    scaled_cross = cross * nuisance_scales[None, :]
    nuisance_spectrum = matrix_spectrum(scaled_nuisance, rcond=rcond)
    nuisance_inverse = _positive_pseudoinverse(scaled_nuisance, nuisance_spectrum)
    coupling_loss = scaled_cross @ nuisance_inverse @ scaled_cross.T
    nuisance_eigenvalues, nuisance_eigenvectors = np.linalg.eigh(scaled_nuisance)
    discarded = nuisance_eigenvalues <= nuisance_spectrum["eigenvalue_cutoff"]
    discarded_coupling = scaled_cross @ nuisance_eigenvectors[:, discarded]
    discarded_coupling_norm = float(np.linalg.norm(discarded_coupling))
    coupling_reference = max(1.0, float(np.linalg.norm(scaled_cross)))
    discarded_coupling_tolerance = float(np.sqrt(rcond) * coupling_reference)
    discarded_modes_couple_to_position = bool(
        discarded_coupling_norm > discarded_coupling_tolerance
    )
    nuisance_profile_valid = bool(
        nuisance_spectrum["negative_count"] == 0
        and not discarded_modes_couple_to_position
    )
    profiled = 0.5 * (
        position - coupling_loss + (position - coupling_loss).T
    )
    full_scales = np.r_[np.ones(2), nuisance_scales]
    scaled_full = full_scales[:, None] * symmetric * full_scales[None, :]
    fixed_spectrum = matrix_spectrum(position, rcond=rcond)
    profile_spectrum = matrix_spectrum(profiled, rcond=rcond)
    fixed_trace = float(np.trace(position))
    profile_trace = float(np.trace(profiled))
    retained_trace_fraction = None
    if fixed_trace > 0.0:
        retained_trace_fraction = profile_trace / fixed_trace
    return {
        "fixed_nuisance_position_information": position,
        "profiled_position_information": profiled,
        "nuisance_coupling_information_loss": coupling_loss,
        "full_spectrum": matrix_spectrum(scaled_full, rcond=rcond),
        "nuisance_spectrum": nuisance_spectrum,
        "nuisance_optimizer_scales": nuisance_scales,
        "nuisance_rank_sensitivity": [
            {
                "rcond": candidate_rcond,
                **{
                    key: value
                    for key, value in matrix_spectrum(
                        scaled_nuisance,
                        rcond=candidate_rcond,
                    ).items()
                    if key in {
                        "positive_rank",
                        "near_zero_count",
                        "negative_count",
                        "eigenvalue_cutoff",
                    }
                },
            }
            for candidate_rcond in RANK_SENSITIVITY_RCONDS
        ],
        "discarded_nuisance_coupling_norm": discarded_coupling_norm,
        "discarded_nuisance_coupling_tolerance": discarded_coupling_tolerance,
        "discarded_modes_couple_to_position": discarded_modes_couple_to_position,
        "nuisance_profile_valid": nuisance_profile_valid,
        "fixed_position_spectrum": fixed_spectrum,
        "profiled_position_spectrum": profile_spectrum,
        "profiled_to_fixed_trace_fraction": retained_trace_fraction,
        "information_degeneracy": bool(
            nuisance_spectrum["positive_rank"] < nuisance.shape[0]
            or nuisance_spectrum["negative_count"] > 0
            or profile_spectrum["positive_rank"] < 2
            or profile_spectrum["negative_count"] > 0
        ),
        "local_uncertainty": _position_uncertainty(
            profiled,
            profile_spectrum,
            nuisance_profile_valid,
        ),
    }


def compare_hessians(left, right, scales=None):
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    difference = left - right
    denominator = max(1.0, float(np.linalg.norm(left)), float(np.linalg.norm(right)))
    left_profile = profile_position_information(
        left,
        scales,
    )["profiled_position_information"]
    right_profile = profile_position_information(
        right,
        scales,
    )["profiled_position_information"]
    profile_denominator = max(
        1.0,
        float(np.linalg.norm(left_profile)),
        float(np.linalg.norm(right_profile)),
    )
    return {
        "relative_frobenius_difference": float(np.linalg.norm(difference) / denominator),
        "maximum_absolute_difference": float(np.max(np.abs(difference), initial=0.0)),
        "profiled_position_relative_difference": float(
            np.linalg.norm(left_profile - right_profile) / profile_denominator
        ),
    }


def timing_knot_diagnostic(objective, vector, relative_steps=RELATIVE_STEPS):
    state = objective.base.state(np.asarray(vector, dtype=float)[: objective.size])
    shifted = (
        np.asarray(objective.base.data.times, dtype=float)[:, None]
        + state["total_shifts_s"][None, :]
    ).ravel()
    nodes = np.asarray(objective.base.data.nodes, dtype=float)
    insertion = np.searchsorted(nodes, shifted)
    lower = nodes[np.maximum(insertion - 1, 0)]
    upper = nodes[np.minimum(insertion, len(nodes) - 1)]
    distances = np.minimum(np.abs(shifted - lower), np.abs(upper - shifted))
    timing_scales = np.asarray(objective.scale[6 : objective.size], dtype=float)
    maximum_step = float(max(relative_steps) * np.max(timing_scales, initial=0.0))
    spacing = np.diff(nodes)
    return {
        "minimum_distance_to_ephemeris_knot_s": float(np.min(distances)),
        "maximum_timing_coordinate_step_s": maximum_step,
        "shifted_row_satellite_times": int(len(shifted)),
        "times_within_maximum_step_of_knot": int(np.count_nonzero(distances <= maximum_step)),
        "timing_knot_crossing_possible": bool(np.any(distances <= maximum_step)),
        "minimum_node_spacing_s": float(np.min(spacing)),
        "maximum_node_spacing_s": float(np.max(spacing)),
    }


def calibrated_current_vector(objective, fitted):
    base_vector = np.asarray(fitted["vector"], dtype=float)
    coefficients = np.asarray(fitted["rf_coefficient_hz_per_ghz"], dtype=float)
    vector = np.r_[base_vector, coefficients]
    if vector.shape != objective.initial.shape or np.any(~np.isfinite(vector)):
        raise ValueError("sealed calibration state has the wrong shape")
    state = objective.base.state(base_vector)
    if not np.allclose(
        state["parameters"],
        np.asarray(fitted["parameters"], dtype=float),
        rtol=0.0,
        atol=1.0e-12,
    ):
        raise ValueError("sealed calibration vector does not reproduce its parameters")
    return vector


def _feasible(objective, vector):
    for value, (lower, upper) in zip(vector, objective.bounds, strict=True):
        if (lower is not None and value < lower) or (upper is not None and value > upper):
            return False
    return bool(objective.base.state(vector[: objective.size])["ephemeris_valid"])


def curvature_diagnostic(objective, current):
    center_value, center_gradient = objective.evaluate(current)
    center_calls = objective.base.calls
    finite_differences = []
    for relative_step in RELATIVE_STEPS:
        finite_differences.append(
            central_gradient_hessian(
                objective.evaluate,
                current,
                objective.scale,
                relative_step,
                validator=lambda vector: _feasible(objective, vector),
            )
        )
    objective.evaluate(current)
    complete_hessian = objective.curvature(current)
    observed = finite_differences[-1]["hessian"]
    observed_analysis = profile_position_information(observed, objective.scale)
    complete_analysis = profile_position_information(complete_hessian, objective.scale)
    return {
        "objective": float(center_value),
        "analytic_gradient": np.asarray(center_gradient, dtype=float),
        "center_evaluations_before_differences": center_calls,
        "finite_difference_evaluations": 2 * len(current) * len(RELATIVE_STEPS),
        "finite_difference_steps": [
            {
                "relative_step": item["relative_step"],
                "physical_steps": item["physical_steps"],
                "relative_asymmetry": item["relative_asymmetry"],
                "observed_analysis": profile_position_information(
                    item["hessian"],
                    objective.scale,
                ),
            }
            for item in finite_differences
        ],
        "step_stability": compare_hessians(
            finite_differences[0]["hessian"],
            finite_differences[1]["hessian"],
            objective.scale,
        ),
        "observed_hessian": observed,
        "observed_information": observed_analysis,
        "complete_data_fisher_hessian": complete_hessian,
        "complete_data_fisher_information": complete_analysis,
        "observed_vs_complete_data": compare_hessians(
            observed,
            complete_hessian,
            objective.scale,
        ),
        "timing_knots": timing_knot_diagnostic(objective, current),
    }


def run_case(session):
    destination = ROOT / "information-curvature-v2" / f"{session}.json"
    if destination.exists():
        raise FileExistsError(destination)
    protocol_path = ROOT / "protocol-soft.json"
    protocol = json.loads(protocol_path.read_text())
    if session not in protocol["sessions"]:
        raise ValueError("session is outside the frozen soft protocol")
    calibration_path = ROOT / "rf-calibration-diagnostic" / f"{session}-common.json"
    parent_path = ROOT / "runs-continuation" / session / "medium" / "fit.json"
    calibration = json.loads(calibration_path.read_text())
    parent = json.loads(parent_path.read_text())
    fitted = calibration.get("fit", {})
    if (
        calibration.get("schema") != "ds13-rf-calibration-diagnostic/v1"
        or calibration.get("session") != session
        or calibration.get("variant") != "common"
        or calibration.get("reference_read_in_fitter") is not False
        or fitted.get("success") is not True
        or fitted.get("parameters_added") != 1
        or fitted.get("sigma_hz") != SIGMA_HZ
        or parent.get("schema") != "ds13-soft-continuation-fit/v1"
        or parent.get("session") != session
        or parent.get("tolerance") != "medium"
    ):
        raise ValueError("invalid sealed common-RF optimum")
    source_hashes = {
        **calibration["source_hashes"],
        **snapshot_files(
            [
                __file__,
                protocol_path,
                calibration_path,
                parent_path,
                ROOT / "rf_calibration_diagnostic.py",
            ]
        ),
    }
    assert_snapshot_unchanged(source_hashes)
    started = time.monotonic()
    _source, data = load_scan(session)
    satellites = np.asarray(parent["fit"]["satellite_indices"], dtype=int)
    objective = CalibrationObjective(
        data,
        fitted["parameters"],
        satellites,
        False,
        BUDGET_S,
    )
    current = calibrated_current_vector(objective, fitted)
    diagnostic = curvature_diagnostic(objective, current)
    if not np.isclose(diagnostic["objective"], fitted["objective"], rtol=0.0, atol=1.0e-6):
        raise ValueError("common-RF optimum objective does not reproduce")
    elapsed = time.monotonic() - started
    if elapsed > BUDGET_S:
        raise RuntimeError("information diagnostic exceeded its per-scan budget")
    assert_snapshot_unchanged(source_hashes)
    result = {
        "schema": "ds13-local-information-curvature/v2",
        "session": session,
        "sigma_hz": SIGMA_HZ,
        "current_vector": current,
        "rf_coefficient_hz_per_ghz": current[objective.size :],
        "optimizer_scale": objective.scale,
        "budget_s": BUDGET_S,
        "elapsed_s": elapsed,
        **diagnostic,
        "source_hashes": source_hashes,
        "calibration_sha256": digest(calibration_path),
        "scope": (
            "Local curvature diagnostic at the sealed common-RF optimum using all "
            "grouped GLRT observations. Reported standard errors are conditional, "
            "penalized-model Gaussian approximations, not localization accuracy or a "
            "global precision guarantee. Observed-Hessian indefiniteness, nuisance "
            "rank loss, timing-knot sensitivity, and finite-difference instability "
            "invalidate sub-kilometer interpretation when present. Nuisance Schur "
            "profiling is performed after optimizer scaling while retaining position "
            "coordinates in kilometers; uncertainty is suppressed if discarded or "
            "negative nuisance modes couple materially to position."
        ),
    }
    destination.parent.mkdir(exist_ok=True)
    with destination.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {
        "session": session,
        "objective": diagnostic["objective"],
        "elapsed_s": elapsed,
        "observed_information_degeneracy": diagnostic["observed_information"][
            "information_degeneracy"
        ],
        "observed_model_standard_errors_km": diagnostic["observed_information"][
            "local_uncertainty"
        ]["marginal_standard_errors_km"],
    }


def main():
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    sessions = json.loads((ROOT / "protocol-soft.json").read_text())["sessions"]
    for session in sessions:
        print(json.dumps(serializable(run_case(session))), flush=True)


if __name__ == "__main__":
    main()


__all__ = [
    "calibrated_current_vector",
    "central_gradient_hessian",
    "compare_hessians",
    "curvature_diagnostic",
    "matrix_spectrum",
    "profile_position_information",
    "timing_knot_diagnostic",
]
