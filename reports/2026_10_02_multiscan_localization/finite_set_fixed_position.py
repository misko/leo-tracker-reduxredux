"""Oracle-only fixed-position diagnostic for paired finite-set pilot arms."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from finite_set_fit import GroupMedianGeometryData, build_likelihood_arms
from finite_set_likelihood import circular_residual
from gauss_newton import refine_gauss_newton
from prediction_plan import SharedPredictionPlan
from rough_smoke import load_module, serializable
from selection import ROOT


ARMS = ("finite_set", "categorical_control")
DEFAULT_MULTIPLICITY_DIAGNOSTIC = ROOT / "finite-set-multiplicity-diagnostic.json"
NUMERICAL_DEPENDENCIES = (
    "finite_set_fixed_position.py",
    "finite_set_fit.py",
    "finite_set_likelihood.py",
    "gauss_newton.py",
    "prediction_plan.py",
    "prediction_jacobian.py",
    "joint_inputs.py",
    "grouped_likelihood.py",
    "track_likelihood.py",
    "staged_fit.py",
)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _array_digest(values):
    values = np.ascontiguousarray(values)
    payload = values.dtype.str.encode() + np.asarray(values.shape, dtype="<i8").tobytes()
    return hashlib.sha256(payload + values.tobytes()).hexdigest()


def _validate_configuration(source):
    expected = {
        "sigma_hz": 200.0,
        "tau_sigma_s": 1.0,
        "tau_bound_s": 3.0,
        "slope_bound_hz_s": 50.0,
    }
    configuration = source.get("configuration", {})
    for key, value in expected.items():
        if not np.isclose(configuration.get(key, np.nan), value, rtol=0, atol=1e-12):
            raise ValueError(f"source configuration changed {key}")
    if source.get("stage") == "finite_set_raw_control":
        for key, value in (
            ("finite_set_clutter_rate", 2.0),
            ("full_bank_signal_or_detection_mass", 0.8),
        ):
            if not np.isclose(configuration.get(key, np.nan), value, rtol=0, atol=1e-12):
                raise ValueError(f"source configuration changed {key}")
        if configuration.get("finite_set_implementation") != "batched":
            raise ValueError("source finite-set implementation must be batched")
    elif not np.isclose(
        source.get("fit", {}).get("finite_set_clutter_rate", np.nan),
        2.0,
        rtol=0,
        atol=1e-12,
    ):
        raise ValueError("continuation source changed finite_set_clutter_rate")
    return expected


def freeze_selected_arms(source, candidate_count):
    """Freeze each arm's final score leader without reading reference coordinates."""

    if not isinstance(source, dict):
        raise TypeError("source must be a decoded fit receipt")
    if source.get("stage") not in {
        "finite_set_raw_control",
        "finite_set_raw_control_continuation",
    }:
        raise ValueError("source must be a finite-set raw-control fit")
    if source.get("reference_read_before_seal") is not False or not source.get("sealed_utc"):
        raise ValueError("source must be sealed before reference evaluation")
    _validate_configuration(source)
    fit = source["fit"]
    full_bank = np.asarray(fit["full_bank"], dtype=int)
    if (
        full_bank.ndim != 1
        or len(full_bank) == 0
        or len(np.unique(full_bank)) != len(full_bank)
        or np.any(full_bank < 0)
        or np.any(full_bank >= candidate_count)
    ):
        raise ValueError("source full bank is invalid")
    frozen = {}
    for arm in ARMS:
        selection = fit[f"{arm}_selection"]
        leader = selection["score_leader"]
        satellites = np.asarray(leader["satellite_indices"], dtype=int)
        parameters = np.asarray(leader["parameters"], dtype=float)
        if (
            satellites.ndim != 1
            or len(satellites) == 0
            or len(np.unique(satellites)) != len(satellites)
            or np.any(satellites < 0)
            or np.any(satellites >= candidate_count)
        ):
            raise ValueError(f"{arm} selected bank is invalid")
        if parameters.shape != (6 + candidate_count,) or np.any(~np.isfinite(parameters)):
            raise ValueError(f"{arm} selected parameters do not match the candidate pool")
        trials = fit[f"{arm}_trials"]
        matches = [
            trial
            for trial in trials
            if np.array_equal(np.asarray(trial["satellite_indices"], dtype=int), satellites)
            and np.array_equal(np.asarray(trial["parameters"], dtype=float), parameters)
        ]
        if len(matches) != 1:
            raise ValueError(f"{arm} score leader is not uniquely bound to its final trial")
        expected_per_satellite = 0.8 / len(full_bank)
        if not np.isclose(
            leader.get("per_satellite_probability", np.nan),
            expected_per_satellite,
            rtol=0,
            atol=1e-12,
        ):
            raise ValueError(f"{arm} selected trial changed the frozen full-bank signal scale")
        raw_masses = leader.get("raw_masses", {})
        if not np.allclose(
            raw_masses.get("raw_satellite_mass", np.nan),
            np.full(len(satellites), expected_per_satellite),
            rtol=0,
            atol=1e-12,
        ) or not np.isclose(
            raw_masses.get("raw_background_mass", np.nan),
            1.0 - len(satellites) * expected_per_satellite,
            rtol=0,
            atol=1e-12,
        ):
            raise ValueError(f"{arm} selected trial changed the frozen categorical masses")
        frozen[arm] = {
            "satellites": satellites.copy(),
            "parameters": parameters.copy(),
            "satellites_sha256": _array_digest(satellites),
            "parameters_sha256": _array_digest(parameters),
            "objective": float(leader["objective"]),
            "selection_score": float(leader["selection_score"]),
            "success": bool(leader["success"]),
            "status": str(leader["status"]),
            "convergence_reason": str(leader.get("convergence_reason", leader.get("message", ""))),
            "selection_resolved": bool(selection["selection_resolved"]),
        }
    return full_bank.copy(), frozen


def _weighted_quantile(values, weights, probability):
    selected = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not np.any(selected):
        return None
    values = np.asarray(values[selected], dtype=float)
    weights = np.asarray(weights[selected], dtype=float)
    order = np.argsort(values, kind="stable")
    values = values[order]
    weights = weights[order]
    cumulative = np.cumsum(weights)
    threshold = float(probability) * cumulative[-1]
    return float(values[min(np.searchsorted(cumulative, threshold, side="left"), len(values) - 1)])


def _residual_summary(residual, weights):
    selected = np.isfinite(residual) & np.isfinite(weights) & (weights > 0)
    if not np.any(selected):
        return {
            "posterior_mass": 0.0,
            "mean_hz": None,
            "rms_hz": None,
            "mean_absolute_hz": None,
            "absolute_p95_hz": None,
        }
    residual = np.asarray(residual[selected], dtype=float)
    weights = np.asarray(weights[selected], dtype=float)
    total = float(np.sum(weights))
    return {
        "posterior_mass": total,
        "mean_hz": float(np.sum(weights * residual) / total),
        "rms_hz": float(np.sqrt(np.sum(weights * residual**2) / total)),
        "mean_absolute_hz": float(np.sum(weights * np.abs(residual)) / total),
        "absolute_p95_hz": _weighted_quantile(np.abs(residual), weights, 0.95),
    }


def _arm_group_arrays(arm, result):
    group_values = np.asarray(result["group_values"])
    if arm == "finite_set":
        return {
            "group_values": group_values,
            "log_likelihood": np.asarray(result["log_likelihood"], dtype=float),
            "satellite_support": np.asarray(
                result["satellite_detection_probability"], dtype=float
            ),
            "null": np.asarray(result["expected_clutter_count"], dtype=float),
            "null_semantics": "posterior expected clutter peak count",
            "raw_peak_count": np.asarray(result["raw_peak_count"], dtype=int),
            "unique_peak_count": np.asarray(result["unique_peak_count"], dtype=int),
        }
    if int(result.get("anchor_count", -1)) != 0:
        raise ValueError("categorical control diagnostic must remain raw-only")
    raw_groups = np.asarray(result["raw_group_values"])
    if not np.array_equal(raw_groups, group_values):
        raise ValueError("categorical control did not retain all groups as raw groups")
    return {
        "group_values": group_values,
        "log_likelihood": np.asarray(result["raw_group_log_likelihood"], dtype=float),
        "satellite_support": np.asarray(result["group_satellite_responsibility"], dtype=float),
        "null": np.asarray(result["group_null_responsibility"], dtype=float),
        "null_semantics": "posterior categorical null probability",
        "raw_peak_count": np.asarray(result["alternative_count"], dtype=int),
        "unique_peak_count": None,
    }


def _evaluate_state(
    data,
    parameters,
    satellites,
    likelihood,
    *,
    sigma_hz,
    tau_sigma_s,
    plan_factory=SharedPredictionPlan,
):
    plan = plan_factory(data, satellites)
    predicted, visible, jacobian = plan.predict(parameters)
    predicted = np.asarray(predicted, dtype=float).reshape(len(data.times), len(satellites))
    visible = np.asarray(visible, dtype=bool).reshape(predicted.shape)
    weights = np.full(len(satellites), 1.0 / len(satellites))
    result = likelihood.evaluate(
        predicted,
        visible,
        sigma_hz=sigma_hz,
        satellite_weights=weights,
        background_mass=0.2,
        return_gradient=True,
        return_precision=True,
    )
    prediction_gradient = np.asarray(result["prediction_gradient"], dtype=float)
    prediction_precision = np.asarray(result["prediction_precision"], dtype=float)
    if prediction_gradient.shape != predicted.shape or prediction_precision.shape != predicted.shape:
        raise ValueError("likelihood derivatives do not match prediction geometry")
    tau = np.asarray(parameters, dtype=float)[6 + satellites]
    tau_prior_by_satellite = 0.5 * (tau / tau_sigma_s) ** 2
    full_gradient = -np.asarray(
        jacobian.transpose_multiply(prediction_gradient.ravel()), dtype=float
    )
    full_gradient[6 + satellites] += tau / tau_sigma_s**2
    total_log_likelihood = float(result["total_log_likelihood"])
    objective = -total_log_likelihood + float(np.sum(tau_prior_by_satellite))
    return {
        "parameters": np.asarray(parameters, dtype=float).copy(),
        "predicted": predicted,
        "visible": visible,
        "result": result,
        "row_assignment_mass": prediction_precision * sigma_hz**2,
        "tau_prior_by_satellite": tau_prior_by_satellite,
        "tau_prior": float(np.sum(tau_prior_by_satellite)),
        "total_log_likelihood": total_log_likelihood,
        "objective": objective,
        "full_gradient": full_gradient,
    }


def _largest_group_rows(group_values, delta, free_support, fixed_support, free_null, fixed_null):
    order = np.argsort(-np.abs(delta), kind="stable")[: min(25, len(delta))]
    return [
        {
            "group": group_values[index],
            "fixed_minus_free_nll": float(delta[index]),
            "free_expected_signal_count": float(np.sum(free_support[index])),
            "fixed_expected_signal_count": float(np.sum(fixed_support[index])),
            "free_null": float(free_null[index]),
            "fixed_null": float(fixed_null[index]),
        }
        for index in order
    ]


def _decompose_arm(data, arm, satellites, free, fixed):
    free_groups = _arm_group_arrays(arm, free["result"])
    fixed_groups = _arm_group_arrays(arm, fixed["result"])
    if not np.array_equal(free_groups["group_values"], fixed_groups["group_values"]):
        raise ValueError("free and fixed group order changed")
    group_values = free_groups["group_values"]
    nll_delta = free_groups["log_likelihood"] - fixed_groups["log_likelihood"]
    likelihood_delta = float(np.sum(nll_delta))
    prior_delta_by_satellite = (
        fixed["tau_prior_by_satellite"] - free["tau_prior_by_satellite"]
    )
    objective_delta = fixed["objective"] - free["objective"]
    reconstructed = likelihood_delta + float(np.sum(prior_delta_by_satellite))
    if not np.isclose(objective_delta, reconstructed, rtol=1e-10, atol=1e-7):
        raise AssertionError("group and prior decomposition does not reconstruct objective delta")

    measured = np.asarray(data.measured, dtype=float)[:, None]
    free_residual = circular_residual(measured, free["predicted"])
    fixed_residual = circular_residual(measured, fixed["predicted"])
    satellite_rows = []
    for column, satellite in enumerate(satellites):
        free_visibility = free["visible"][:, column]
        fixed_visibility = fixed["visible"][:, column]
        satellite_rows.append(
            {
                "satellite_index": int(satellite),
                "catalog_number": int(np.asarray(data.numbers)[satellite]),
                "free_tau_s": float(free["parameters"][6 + satellite]),
                "fixed_tau_s": float(fixed["parameters"][6 + satellite]),
                "fixed_minus_free_tau_prior": float(prior_delta_by_satellite[column]),
                "free_support": float(np.sum(free_groups["satellite_support"][:, column])),
                "fixed_support": float(np.sum(fixed_groups["satellite_support"][:, column])),
                "free_visible_row_count": int(np.sum(free_visibility)),
                "fixed_visible_row_count": int(np.sum(fixed_visibility)),
                "visibility_gain_row_count": int(np.sum(~free_visibility & fixed_visibility)),
                "visibility_loss_row_count": int(np.sum(free_visibility & ~fixed_visibility)),
                "free_residual": _residual_summary(
                    free_residual[:, column], free["row_assignment_mass"][:, column]
                ),
                "fixed_residual": _residual_summary(
                    fixed_residual[:, column], fixed["row_assignment_mass"][:, column]
                ),
            }
        )

    receiver_rows = []
    receivers = np.asarray(data.receiver)
    for receiver in np.unique(receivers):
        rows = receivers == receiver
        receiver_rows.append(
            {
                "receiver": int(receiver),
                "free_residual": _residual_summary(
                    free_residual[rows].ravel(), free["row_assignment_mass"][rows].ravel()
                ),
                "fixed_residual": _residual_summary(
                    fixed_residual[rows].ravel(), fixed["row_assignment_mass"][rows].ravel()
                ),
            }
        )

    return {
        "fixed_minus_free_objective": objective_delta,
        "fixed_minus_free_negative_log_likelihood": likelihood_delta,
        "fixed_minus_free_tau_prior": float(np.sum(prior_delta_by_satellite)),
        "decomposition_reconstruction_error": float(objective_delta - reconstructed),
        "group": {
            "group_values": group_values,
            "free_log_likelihood": free_groups["log_likelihood"],
            "fixed_log_likelihood": fixed_groups["log_likelihood"],
            "fixed_minus_free_nll": nll_delta,
            "free_satellite_support": free_groups["satellite_support"],
            "fixed_satellite_support": fixed_groups["satellite_support"],
            "free_null": free_groups["null"],
            "fixed_null": fixed_groups["null"],
            "null_semantics": free_groups["null_semantics"],
            "raw_peak_count": free_groups["raw_peak_count"],
            "unique_peak_count": free_groups["unique_peak_count"],
        },
        "largest_absolute_group_contributors": _largest_group_rows(
            group_values,
            nll_delta,
            free_groups["satellite_support"],
            fixed_groups["satellite_support"],
            free_groups["null"],
            fixed_groups["null"],
        ),
        "satellites": satellite_rows,
        "receivers": receiver_rows,
        "satellite_log_likelihood_additivity": False,
        "satellite_diagnostics_role": (
            "Posterior support, visibility, timing prior and assignment-weighted residual evidence; "
            "the mixture likelihood has no additive per-satellite NLL decomposition."
        ),
    }


def fit_fixed_position_pairs(
    data,
    source,
    position_km,
    *,
    budget_s_per_arm=20.0,
    refiner=refine_gauss_newton,
    arm_builder=build_likelihood_arms,
    plan_factory=SharedPredictionPlan,
):
    """Refit nuisance parameters at one supplied position for both frozen arms."""

    if not np.isfinite(budget_s_per_arm) or not 0 < budget_s_per_arm <= 20:
        raise ValueError("budget_s_per_arm must lie in (0, 20]")
    position_km = np.asarray(position_km, dtype=float)
    if position_km.shape != (2,) or np.any(~np.isfinite(position_km)):
        raise ValueError("position_km must contain one finite east/north pair")
    geometry = data if isinstance(data, GroupMedianGeometryData) else GroupMedianGeometryData(data)
    full_bank, frozen = freeze_selected_arms(source, len(geometry.numbers))
    results = {}
    for arm in ARMS:
        selected = frozen[arm]
        satellites = selected["satellites"]
        likelihood = arm_builder(geometry, len(satellites), len(full_bank))[arm]
        free = _evaluate_state(
            geometry,
            selected["parameters"],
            satellites,
            likelihood,
            sigma_hz=200.0,
            tau_sigma_s=1.0,
            plan_factory=plan_factory,
        )
        if not np.isclose(free["objective"], selected["objective"], rtol=1e-9, atol=1e-6):
            raise ValueError(f"{arm} sealed free objective does not reproduce")
        fixed_fit = refiner(
            geometry,
            selected["parameters"].copy(),
            satellites,
            np.ones(len(satellites)),
            likelihood,
            sigma_hz=200.0,
            tau_sigma_s=1.0,
            tau_bound_s=3.0,
            slope_bound=50.0,
            budget_s=float(budget_s_per_arm),
            fixed_position_km=position_km.copy(),
        )
        fixed_parameters = np.asarray(fixed_fit["parameters"], dtype=float)
        if not np.array_equal(fixed_parameters[:2], position_km):
            raise AssertionError(f"{arm} fixed-position refiner moved the position")
        if not np.array_equal(np.asarray(fixed_fit["satellite_indices"], dtype=int), satellites):
            raise AssertionError(f"{arm} fixed-position refiner changed the selected bank")
        fixed = _evaluate_state(
            geometry,
            fixed_parameters,
            satellites,
            likelihood,
            sigma_hz=200.0,
            tau_sigma_s=1.0,
            plan_factory=plan_factory,
        )
        if not np.isclose(fixed["objective"], fixed_fit["objective"], rtol=1e-9, atol=1e-6):
            raise ValueError(f"{arm} fixed objective does not reproduce")
        results[arm] = {
            "selected_bank": satellites,
            "selected_catalog_numbers": np.asarray(geometry.numbers)[satellites],
            "same_bank_free_and_fixed": True,
            "source_free": {
                "parameters": selected["parameters"],
                "parameters_sha256": selected["parameters_sha256"],
                "objective": free["objective"],
                "total_log_likelihood": free["total_log_likelihood"],
                "tau_prior": free["tau_prior"],
                "success": selected["success"],
                "status": selected["status"],
                "convergence_reason": selected["convergence_reason"],
                "selection_resolved": selected["selection_resolved"],
                "position_gradient": free["full_gradient"][:2],
            },
            "fixed_reference": {
                **fixed_fit,
                "objective": fixed["objective"],
                "total_log_likelihood": fixed["total_log_likelihood"],
                "tau_prior": fixed["tau_prior"],
                "position_gradient": fixed["full_gradient"][:2],
            },
            "decomposition": _decompose_arm(geometry, arm, satellites, free, fixed),
        }
    return {
        "position_km": position_km.copy(),
        "full_bank": full_bank,
        "arms": results,
        "fit_calls": 2,
        "free_fit_calls": 0,
        "fixed_fit_calls": 2,
        "budget_s_per_arm": float(budget_s_per_arm),
        "maximum_case_fit_budget_s": float(2 * budget_s_per_arm),
        "cross_arm_absolute_nll_comparisons": False,
        "same_bank_pairing_within_each_arm": True,
        "geometry": geometry.geometry_receipt,
    }


def _inverse_reference_position(common, reference, initial):
    from scipy.optimize import least_squares

    cosine = np.cos(np.deg2rad(reference["latitude_deg"]))

    def residual(point):
        latitude, longitude = common.coordinates(point)
        longitude_error = (longitude - reference["longitude_deg"] + 180.0) % 360.0 - 180.0
        return np.asarray(
            [latitude - reference["latitude_deg"], cosine * longitude_error], dtype=float
        )

    fitted = least_squares(
        residual,
        np.asarray(initial, dtype=float),
        bounds=([-200.0, -200.0], [200.0, 200.0]),
        xtol=1e-13,
        ftol=1e-13,
        gtol=1e-13,
        max_nfev=100,
    )
    if not fitted.success or np.linalg.norm(fitted.fun, ord=np.inf) > 1e-9:
        raise RuntimeError(f"reference-coordinate inversion failed: {fitted.message}")
    return fitted.x


def _multiplicity_context(unit_id):
    receipt = json.loads(DEFAULT_MULTIPLICITY_DIAGNOSTIC.read_text())
    if (
        receipt.get("schema") != "finite-set-multiplicity-diagnostic/v1"
        or receipt.get("reference_coordinates_read") is not False
        or receipt.get("fits_run") is not False
    ):
        raise ValueError("multiplicity context must be the truth-free, fit-free v1 diagnostic")
    matches = [row for row in receipt["units"] if row["unit_id"] == unit_id]
    if len(matches) != 1:
        raise ValueError("multiplicity context does not contain the diagnostic unit")
    return {
        "path": str(DEFAULT_MULTIPLICITY_DIAGNOSTIC),
        "sha256": _digest(DEFAULT_MULTIPLICITY_DIAGNOSTIC),
        "row": matches[0],
        "role": (
            "Truth-free v1 context showing material posterior multi-emitter assignments; not a "
            "physical-independence confirmation and not used in this fit or selection."
        ),
    }


def run_oracle(source_fit_path, output_path, *, budget_s_per_arm=20.0):
    """Run two fixed-only truth-conditioned fits after a final source is sealed."""

    source_fit_path = Path(source_fit_path)
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(output_path)
    source_sha256 = _digest(source_fit_path)
    source = json.loads(source_fit_path.read_text())
    unit = source["unit"]
    unit_id = unit["unit_id"]
    if unit_id not in {"DS10-S01", "DS11-S02"} or unit.get("size") != 1:
        raise ValueError("oracle diagnostic is restricted to the two finite-set single pilots")

    candidate_count = 64
    full_bank, frozen = freeze_selected_arms(source, candidate_count)
    frozen_before_reference = {
        arm: {
            "satellites_sha256": frozen[arm]["satellites_sha256"],
            "parameters_sha256": frozen[arm]["parameters_sha256"],
        }
        for arm in ARMS
    }
    source_evaluation_path = source_fit_path.with_name("evaluation.json")
    source_evaluation = json.loads(source_evaluation_path.read_text())
    if source_evaluation.get("fit_sha256") != source_sha256:
        raise ValueError("source evaluation does not bind the sealed final fit")
    reference = source_evaluation["reference_site"]

    bundle_path = ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py"
    bundle = load_module(f"finite_set_fixed_position_bundle_{unit_id}", bundle_path)
    session_id = unit["session_ids"][0]
    data = bundle.Data(ROOT / "scans" / session_id)
    initial_position = np.mean(
        np.vstack([frozen[arm]["parameters"][:2] for arm in ARMS]), axis=0
    )
    oracle_position = _inverse_reference_position(bundle._COMMON, reference, initial_position)
    if not np.array_equal(full_bank, np.asarray(source["fit"]["full_bank"], dtype=int)):
        raise AssertionError("source full bank changed after reference read")
    for arm in ARMS:
        current = freeze_selected_arms(source, candidate_count)[1][arm]
        if (
            current["satellites_sha256"] != frozen_before_reference[arm]["satellites_sha256"]
            or current["parameters_sha256"] != frozen_before_reference[arm]["parameters_sha256"]
        ):
            raise AssertionError("source arm selection changed after reference read")

    source_paths = [ROOT / name for name in NUMERICAL_DEPENDENCIES] + [bundle_path]
    source_hashes = {str(path): _digest(path) for path in source_paths}
    artifact_hashes = {
        str(source_fit_path): source_sha256,
        str(source_evaluation_path): _digest(source_evaluation_path),
        str(DEFAULT_MULTIPLICITY_DIAGNOSTIC): _digest(DEFAULT_MULTIPLICITY_DIAGNOSTIC),
    }
    started = time.monotonic()
    fitted = fit_fixed_position_pairs(
        data,
        source,
        oracle_position,
        budget_s_per_arm=budget_s_per_arm,
    )
    changed_sources = [path for path, value in source_hashes.items() if _digest(path) != value]
    changed_artifacts = [path for path, value in artifact_hashes.items() if _digest(path) != value]
    if changed_sources or changed_artifacts:
        raise RuntimeError("diagnostic provenance changed before writing the oracle receipt")

    payload = {
        "schema": "finite-set-fixed-position-oracle-diagnostic/v1",
        "generated_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "oracle": True,
        "eligible_for_cohort": False,
        "unit_id": unit_id,
        "source_run_id": source["run_id"],
        "source_fit": str(source_fit_path),
        "source_fit_sha256": source_sha256,
        "source_evaluation": str(source_evaluation_path),
        "source_evaluation_sha256": artifact_hashes[str(source_evaluation_path)],
        "source_hashes": source_hashes,
        "bound_artifact_hashes": artifact_hashes,
        "source_selections_frozen_before_reference_read": frozen_before_reference,
        "reference_site": reference,
        "oracle_position_km": oracle_position,
        "multiplicity_context": _multiplicity_context(unit_id),
        "fit": fitted,
        "elapsed_s": time.monotonic() - started,
        "cross_arm_absolute_nll_comparisons": False,
        "free_fits_run": False,
        "scope": (
            "Explicitly truth-conditioned diagnostic run only after a sealed final finite-set fit. "
            "Each arm keeps its own final score-leader bank and nuisance initialization; only RX "
            "lines and selected timing offsets are refit at the known fixed position. No free fit is "
            "run, no arm is selected using reference error, and absolute NLL is never compared "
            "between arms. Group NLL deltas are additive only within an arm. Satellite diagnostics "
            "are posterior support and residual evidence, not additive NLL or physical-emitter proof."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(serializable(payload), indent=2) + "\n")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", action="store_true")
    parser.add_argument("--source-fit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--budget-s-per-arm", type=float, default=20.0)
    args = parser.parse_args()
    if not args.oracle:
        parser.error("--oracle is required because this command reads reference coordinates")
    if not 0 < args.budget_s_per_arm <= 20:
        parser.error("budget-s-per-arm must lie in (0, 20]")
    result = run_oracle(
        args.source_fit,
        args.output,
        budget_s_per_arm=args.budget_s_per_arm,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "source_fit_sha256": result["source_fit_sha256"],
                "unit_id": result["unit_id"],
                "finite_set_fixed_minus_free_objective": result["fit"]["arms"]["finite_set"][
                    "decomposition"
                ]["fixed_minus_free_objective"],
                "categorical_control_fixed_minus_free_objective": result["fit"]["arms"][
                    "categorical_control"
                ]["decomposition"]["fixed_minus_free_objective"],
                "cross_arm_absolute_nll_comparisons": False,
                "eligible_for_cohort": False,
            }
        )
    )


if __name__ == "__main__":
    main()


__all__ = ["fit_fixed_position_pairs", "freeze_selected_arms", "run_oracle"]
