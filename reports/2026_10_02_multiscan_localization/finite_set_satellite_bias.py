"""Finite-set pilot with one shared constant-frequency bias per satellite."""

from __future__ import annotations

import argparse
import copy
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from finite_set_fit import (
    FiniteSetLikelihoodAdapter,
    GroupMedianGeometryData,
    array_digest,
    assert_snapshot_unchanged,
    digest,
    frozen_raw_masses,
    snapshot_files,
)
from finite_set_likelihood import prepare_finite_set_likelihood
from prediction_plan import SharedPredictionPlan
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN_ID = "finite-set-raw-control-v2"
DEFAULT_RUN_ID = "finite-set-satellite-bias-v1"
PILOT_UNIT = "DS11-S02"
OMEGA_SIGMA_HZ = 200.0
MEASUREMENT_SIGMA_HZ = 200.0
TAU_SIGMA_S = 1.0
TAU_BOUND_S = 3.0
RX_SLOPE_BOUND_HZ_S = 50.0
EXPECTED_BANK_COUNT = 5
NUMERICAL_DEPENDENCIES = (
    "finite_set_satellite_bias.py",
    "finite_set_fit.py",
    "finite_set_likelihood.py",
    "prediction_plan.py",
    "prediction_jacobian.py",
    "joint_inputs.py",
    "staged_fit.py",
)


@dataclass(frozen=True)
class BiasState:
    vector: np.ndarray
    parameters: np.ndarray
    omega_hz: np.ndarray
    objective: float
    gradient: np.ndarray
    likelihood: dict
    visible: np.ndarray
    tau_prior: float
    omega_prior: float


def _same_numeric(left, right):
    left = np.asarray(left)
    right = np.asarray(right)
    if left.size == 0 and right.size == 0:
        return True
    return left.shape == right.shape and np.allclose(left, right, rtol=0, atol=1e-12)


def _validate_source(source, unit_id):
    if source.get("schema") != "finite-set-raw-control-continuation/v1":
        raise ValueError("source must be a sealed finite-set v2 continuation")
    if source.get("stage") != "finite_set_raw_control_continuation":
        raise ValueError("source has the wrong finite-set stage")
    if source.get("reference_read_before_seal") is not False:
        raise ValueError("source was not sealed before reference access")
    if source.get("v1_evaluation_read") is not False:
        raise ValueError("source continuation read a prior evaluation")
    if source.get("evaluation_written") is not False:
        raise ValueError("source receipt unexpectedly contains an evaluation")
    if source.get("prefit_hashes_reverified_unchanged_before_seal") is not True:
        raise ValueError("source did not reverify its bound inputs")
    if source.get("unit", {}).get("unit_id") != unit_id:
        raise ValueError("source unit does not match the requested pilot")
    fit = source["fit"]
    trials = fit["finite_set_trials"]
    if not trials:
        raise ValueError("source contains no finite-set trials")
    banks = [tuple(np.asarray(trial["satellite_indices"], dtype=int)) for trial in trials]
    if len(set(banks)) != len(banks):
        raise ValueError("source contains duplicate finite-set banks")
    if any(trial.get("arm") != "finite_set" for trial in trials):
        raise ValueError("source finite-set ladder contains another arm")
    if fit.get("anchors_used_by_either_arm") != 0:
        raise ValueError("finite-set v2 source must be raw-only")
    return fit


def _trial_specification(data, source_parameters, satellites):
    candidate_count = len(data.numbers)
    source_parameters = np.asarray(source_parameters, dtype=float)
    satellites = np.asarray(satellites, dtype=int)
    if source_parameters.shape != (6 + candidate_count,) or np.any(~np.isfinite(source_parameters)):
        raise ValueError("sealed source parameters do not match the candidate pool")
    if satellites.ndim != 1 or len(satellites) == 0:
        raise ValueError("satellites must be a nonempty vector")
    if (
        len(np.unique(satellites)) != len(satellites)
        or np.any(satellites < 0)
        or np.any(satellites >= candidate_count)
    ):
        raise ValueError("satellites must be unique valid candidate indices")
    active = np.r_[np.arange(6), 6 + satellites]
    physical_scales = np.r_[
        20.0,
        20.0,
        1000.0,
        10.0,
        1000.0,
        10.0,
        np.ones(len(satellites)),
    ]
    scales = np.r_[physical_scales, np.full(len(satellites), OMEGA_SIGMA_HZ)]
    bounds = [
        (-10.0, 10.0),
        (-10.0, 10.0),
        (None, None),
        (-RX_SLOPE_BOUND_HZ_S / 10.0, RX_SLOPE_BOUND_HZ_S / 10.0),
        (None, None),
        (-RX_SLOPE_BOUND_HZ_S / 10.0, RX_SLOPE_BOUND_HZ_S / 10.0),
    ]
    bounds += [(-TAU_BOUND_S, TAU_BOUND_S)] * len(satellites)
    bounds += [(None, None)] * len(satellites)
    vector = np.r_[
        source_parameters[active] / physical_scales,
        np.zeros(len(satellites)),
    ]
    return {
        "initial_parameters": source_parameters.copy(),
        "active": active,
        "physical_scales": physical_scales,
        "scales": scales,
        "bounds": bounds,
        "vector": vector,
    }


def receiver_satellite_topology(data, satellites, visible, *, require_connected=True):
    satellites = np.asarray(satellites, dtype=int)
    receiver = np.asarray(data.receiver, dtype=int)
    channel = np.asarray(data.channel, dtype=int)
    visible = np.asarray(visible, dtype=bool).reshape(len(receiver), len(satellites))
    if set(np.unique(receiver)) != {0, 1}:
        raise ValueError("satellite-bias pilot requires both receivers")
    parent = np.arange(2 + len(satellites))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    rows = []
    for column, satellite in enumerate(satellites):
        receiver_counts = []
        channel_values = set()
        for receiver_id in (0, 1):
            mask = (receiver == receiver_id) & visible[:, column]
            count = int(np.sum(mask))
            receiver_counts.append(count)
            if count:
                union(receiver_id, 2 + column)
                channel_values.update(int(value) for value in np.unique(channel[mask]))
        if not any(receiver_counts):
            raise ValueError(f"satellite {int(satellite)} has no visible prediction support")
        rows.append(
            {
                "satellite_index": int(satellite),
                "visible_rows_by_receiver": receiver_counts,
                "visible_channels": sorted(channel_values),
            }
        )
    component_count = len({find(index) for index in range(len(parent))})
    if require_connected and component_count != 1:
        raise ValueError("receiver-satellite visibility topology is disconnected")
    return {
        "node_definition": "two RX intercept nodes plus one node per selected satellite",
        "edge_definition": "at least one geometrically visible row for RX and satellite",
        "component_count": component_count,
        "connected": component_count == 1,
        "likelihood_identifiable_omega_contrasts": max(len(satellites) - component_count, 0),
        "satellites_visible_on_both_receivers": int(
            sum(all(value > 0 for value in row["visible_rows_by_receiver"]) for row in rows)
        ),
        "satellites": rows,
        "limitation": (
            "Visibility connectivity is necessary but does not establish posterior assignment "
            "support; the K-1 score penalty is a conditional approximation."
        ),
    }


def _physical_parameters(vector, specification):
    vector = np.asarray(vector, dtype=float)
    physical_count = len(specification["active"])
    parameters = specification["initial_parameters"].copy()
    parameters[specification["active"]] = vector[:physical_count] * specification["physical_scales"]
    return parameters


def evaluate_bias_state(
    vector,
    *,
    data,
    specification,
    satellites,
    likelihood,
    plan,
):
    vector = np.asarray(vector, dtype=float)
    scales = specification["scales"]
    if vector.shape != scales.shape or np.any(~np.isfinite(vector)):
        raise ValueError("satellite-bias vector has the wrong shape or non-finite values")
    physical_count = len(specification["active"])
    parameters = _physical_parameters(vector, specification)
    omega_scaled = vector[physical_count:]
    omega_hz = omega_scaled * OMEGA_SIGMA_HZ
    predicted, visible, jacobian = plan.predict(parameters)
    predicted = np.asarray(predicted, dtype=float).reshape(len(data.times), len(satellites))
    visible = np.asarray(visible, dtype=bool).reshape(predicted.shape)
    predicted = predicted + omega_hz[None, :]
    result = likelihood.evaluate(
        predicted,
        visible,
        sigma_hz=MEASUREMENT_SIGMA_HZ,
        satellite_weights=likelihood.frozen_masses["raw_satellite_mass"],
        background_mass=likelihood.frozen_masses["raw_background_mass"],
        return_gradient=True,
    )
    prediction_gradient = np.asarray(result["prediction_gradient"], dtype=float)
    if prediction_gradient.shape != predicted.shape or np.any(~np.isfinite(prediction_gradient)):
        raise FloatingPointError("finite-set prediction gradient is invalid")
    physical_gradient = -jacobian.transpose_multiply(prediction_gradient.ravel())
    tau_indices = 6 + satellites
    tau = parameters[tau_indices]
    tau_prior = 0.5 * float(np.sum((tau / TAU_SIGMA_S) ** 2))
    physical_gradient[tau_indices] += tau / TAU_SIGMA_S**2
    omega_prior = 0.5 * float(np.sum(omega_scaled**2))
    omega_gradient = -OMEGA_SIGMA_HZ * np.sum(prediction_gradient, axis=0) + omega_scaled
    objective = float(-result["total_log_likelihood"] + tau_prior + omega_prior)
    gradient = np.r_[
        physical_gradient[specification["active"]] * specification["physical_scales"],
        omega_gradient,
    ]
    if not np.isfinite(objective) or np.any(~np.isfinite(gradient)):
        raise FloatingPointError("finite-set satellite-bias objective or gradient is non-finite")
    diagnostics = dict(result)
    diagnostics.pop("prediction_gradient", None)
    return BiasState(
        vector=vector.copy(),
        parameters=parameters,
        omega_hz=omega_hz,
        objective=objective,
        gradient=gradient,
        likelihood=diagnostics,
        visible=visible.copy(),
        tau_prior=tau_prior,
        omega_prior=omega_prior,
    )


def fit_satellite_bias_trial(
    data,
    source_trial,
    likelihood,
    *,
    budget_s=15.0,
    minimizer=None,
    plan_factory=SharedPredictionPlan,
):
    if not np.isfinite(budget_s) or not 0 < budget_s <= 15:
        raise ValueError("budget_s must lie in (0, 15]")
    satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
    specification = _trial_specification(
        data,
        source_trial["parameters"],
        satellites,
    )
    plan = plan_factory(data, satellites)
    _, initial_visible, _ = plan.predict(specification["initial_parameters"])
    initial_topology = receiver_satellite_topology(data, satellites, initial_visible)
    started = time.monotonic()
    deadline = started + float(budget_s)
    evaluations = 0
    best = None
    disconnected_topology_evaluations = 0

    def evaluate(candidate, *, check_time=True):
        nonlocal best, disconnected_topology_evaluations, evaluations
        if check_time and time.monotonic() > deadline:
            raise TimeoutError("finite-set satellite-bias fit budget exhausted")
        evaluations += 1
        state = evaluate_bias_state(
            candidate,
            data=data,
            specification=specification,
            satellites=satellites,
            likelihood=likelihood,
            plan=plan,
        )
        topology = receiver_satellite_topology(
            data,
            satellites,
            state.visible,
            require_connected=False,
        )
        if not topology["connected"]:
            disconnected_topology_evaluations += 1
        elif best is None or state.objective < best.objective:
            best = state
        return state.objective, state.gradient

    initial_objective, _ = evaluate(specification["vector"], check_time=False)
    optimizer = None
    timed_out = False
    try:
        if minimizer is None:
            from scipy.optimize import minimize

            optimizer = minimize(
                evaluate,
                specification["vector"],
                method="L-BFGS-B",
                jac=True,
                bounds=specification["bounds"],
                options={"maxiter": 500, "ftol": 1e-12, "gtol": 1e-7, "maxls": 50},
            )
        else:
            optimizer = minimizer(evaluate, specification["vector"], specification["bounds"])
    except TimeoutError:
        timed_out = True
    if best is None:
        raise RuntimeError("finite-set satellite-bias fit produced no finite state")
    final = evaluate_bias_state(
        best.vector,
        data=data,
        specification=specification,
        satellites=satellites,
        likelihood=likelihood,
        plan=plan,
    )
    _, retained_visible, _ = plan.predict(final.parameters)
    final_topology = receiver_satellite_topology(data, satellites, retained_visible)
    terminal_topology = None
    terminal_matches_retained = False
    if optimizer is not None and hasattr(optimizer, "x"):
        terminal_vector = np.asarray(optimizer.x, dtype=float)
        terminal_parameters = _physical_parameters(terminal_vector, specification)
        _, terminal_visible, _ = plan.predict(terminal_parameters)
        terminal_topology = receiver_satellite_topology(
            data,
            satellites,
            terminal_visible,
            require_connected=False,
        )
        terminal_matches_retained = bool(
            terminal_vector.shape == final.vector.shape
            and np.allclose(terminal_vector, final.vector, rtol=0, atol=1e-10)
        )
    terminal_connected = terminal_topology is None or terminal_topology["connected"]
    success = bool(
        optimizer is not None
        and optimizer.success
        and not timed_out
        and terminal_connected
        and terminal_matches_retained
    )
    groups = len(final.likelihood["group_values"])
    entry_penalty = 0.5 * len(satellites) * np.log(groups)
    omega_parameter_count = max(len(satellites) - final_topology["component_count"], 0)
    omega_penalty = 0.5 * omega_parameter_count * np.log(groups)
    return {
        "model": "finite_set_satellite_bias",
        "parameters": final.parameters,
        "omega_hz": final.omega_hz,
        "omega_sigma_hz": OMEGA_SIGMA_HZ,
        "omega_hard_bound_hz": None,
        "satellite_indices": satellites,
        "catalog_numbers": np.asarray(data.numbers)[satellites],
        "satellite_count": len(satellites),
        "objective": final.objective,
        "initial_objective": initial_objective,
        "selection_score": float(final.objective + entry_penalty + omega_penalty),
        "entry_penalty": float(entry_penalty),
        "omega_identifiable_parameter_count": omega_parameter_count,
        "omega_parameter_penalty": float(omega_penalty),
        "success": success,
        "status": "converged" if success else "nonconverged",
        "message": (
            "budget_exhausted"
            if timed_out
            else (
                "optimizer_terminal_topology_disconnected_retained_connected_incumbent"
                if not terminal_connected
                else (
                    "optimizer_terminal_differs_from_retained_connected_incumbent"
                    if not terminal_matches_retained
                    else str(
                        optimizer.message if optimizer is not None else "optimizer_not_started"
                    )
                )
            )
        ),
        "optimizer_status": (
            None if optimizer is None or not hasattr(optimizer, "status") else int(optimizer.status)
        ),
        "evaluations": evaluations,
        "iterations": (
            None if optimizer is None or not hasattr(optimizer, "nit") else int(optimizer.nit)
        ),
        "elapsed_s": time.monotonic() - started,
        "groups": groups,
        "sigma_hz": MEASUREMENT_SIGMA_HZ,
        "tau_sigma_s": TAU_SIGMA_S,
        "tau_bound_s": TAU_BOUND_S,
        "rx_slope_bound_hz_s": RX_SLOPE_BOUND_HZ_S,
        "tau_prior": final.tau_prior,
        "omega_prior": final.omega_prior,
        "gradient_inf_norm": float(np.max(np.abs(final.gradient))),
        "omega_mean_hz": float(np.mean(final.omega_hz)),
        "omega_shared_across_receivers_and_channels": True,
        "omega_gauge_resolution": (
            "The proper zero-mean Gaussian prior assigns the likelihood-invariant common omega "
            "mode to the two free RX intercepts; only connected omega contrasts are "
            "data-identified."
        ),
        "initial_topology": initial_topology,
        "final_topology": final_topology,
        "optimizer_terminal_topology": terminal_topology,
        "optimizer_terminal_matches_retained": terminal_matches_retained,
        "disconnected_topology_evaluation_count": disconnected_topology_evaluations,
        "best_finite_preserved": True,
        "best_connected_finite_preserved": True,
        "satellite_support": final.likelihood["satellite_support"],
        "null_support": final.likelihood["null_support"],
    }


def _compact_trial(trial, model):
    return {
        "model": model,
        "satellite_count": int(trial["satellite_count"]),
        "satellite_indices": copy.deepcopy(trial["satellite_indices"]),
        "objective": float(trial["objective"]),
        "selection_score": float(trial["selection_score"]),
        "success": bool(trial["success"]),
        "status": trial["status"],
    }


def _likelihood_diagnostics(adapter):
    result = adapter.last_result
    return {
        "conditioned_nonempty": bool(result["conditioned_nonempty"]),
        "density_convention": result["density_convention"],
        "group_count": int(len(result["group_values"])),
        "total_satellite_support": float(np.sum(result["satellite_support"])),
        "total_expected_clutter_count": float(np.sum(result["expected_clutter_count"])),
        "total_raw_peak_count": int(np.sum(result["raw_peak_count"])),
        "total_unique_peak_count": int(np.sum(result["unique_peak_count"])),
    }


def fit_satellite_bias_models(
    data,
    source,
    *,
    budget_s_per_bank=15.0,
    trial_fitter=fit_satellite_bias_trial,
    likelihood_preparer=prepare_finite_set_likelihood,
    expected_bank_count=EXPECTED_BANK_COUNT,
):
    if not np.isfinite(budget_s_per_bank) or not 0 < budget_s_per_bank <= 15:
        raise ValueError("budget_s_per_bank must lie in (0, 15]")
    unit_id = source["unit"]["unit_id"]
    source_fit = _validate_source(source, unit_id)
    source_trials = source_fit["finite_set_trials"]
    if len(source_trials) != expected_bank_count:
        raise ValueError("source does not contain the expected full bank ladder")
    geometry = data if isinstance(data, GroupMedianGeometryData) else GroupMedianGeometryData(data)
    if geometry.geometry_receipt != source_fit["geometry"]:
        raise ValueError("reconstructed group-median geometry differs from sealed finite-set v2")
    full_bank = np.asarray(source_fit["full_bank"], dtype=int)
    if len(full_bank) == 0 or len(np.unique(full_bank)) != len(full_bank):
        raise ValueError("source full bank must be nonempty and unique")
    prepared = likelihood_preparer(geometry.measured, geometry.group)
    bias_trials = []
    baseline_trials = []
    per_bank_incumbents = []
    for source_trial in source_trials:
        satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
        if source_trial["satellite_count"] != len(satellites):
            raise ValueError("source finite-set bank cardinality is inconsistent")
        expected_masses = frozen_raw_masses(len(satellites), len(full_bank))
        if set(source_trial["raw_masses"]) != set(expected_masses) or any(
            not _same_numeric(source_trial["raw_masses"][key], value)
            for key, value in expected_masses.items()
        ):
            raise ValueError("source finite-set masses differ from the frozen full-bank scale")
        expected_probability = 0.8 / len(full_bank)
        if not np.isclose(
            source_trial["per_satellite_probability"],
            expected_probability,
            rtol=0,
            atol=1e-12,
        ):
            raise ValueError("source detection probability differs from the frozen full-bank scale")
        expected_entry_penalty = 0.5 * len(satellites) * np.log(source_trial["groups"])
        if not np.isclose(source_trial["entry_penalty"], expected_entry_penalty, rtol=0, atol=1e-9):
            raise ValueError("source entry penalty differs from the frozen count convention")
        finite_set = FiniteSetLikelihoodAdapter(
            prepared,
            detection_probability=expected_probability,
            clutter_rate=float(source_fit["finite_set_clutter_rate"]),
        )
        finite_set.frozen_masses = copy.deepcopy(expected_masses)
        trial = trial_fitter(
            geometry,
            source_trial,
            finite_set,
            budget_s=float(budget_s_per_bank),
        )
        if not np.isclose(trial["initial_objective"], source_trial["objective"], rtol=0, atol=1e-5):
            raise ValueError("zero-omega state does not reproduce its finite-set v2 seed")
        trial["source_model"] = "finite_set_linear_v2"
        trial["source_objective"] = float(source_trial["objective"])
        trial["source_selection_score"] = float(source_trial["selection_score"])
        trial["source_success"] = bool(source_trial["success"])
        trial["source_status"] = source_trial["status"]
        trial["source_parameters_sha256"] = array_digest(source_trial["parameters"])
        trial["full_bank_count"] = len(full_bank)
        trial["per_satellite_probability"] = expected_probability
        trial["raw_masses"] = copy.deepcopy(expected_masses)
        trial["anchors_used"] = 0
        trial["likelihood_diagnostics"] = _likelihood_diagnostics(finite_set)
        bias_trials.append(trial)
        baseline = _compact_trial(source_trial, "finite_set_linear_v2")
        baseline_trials.append(baseline)
        per_bank_incumbents.append(
            min(
                (baseline, _compact_trial(trial, "finite_set_satellite_bias")),
                key=lambda candidate: candidate["selection_score"],
            )
        )
    bias_selection = select_trials(bias_trials)
    baseline_selection = select_trials(baseline_trials)
    combined_selection = select_trials(
        baseline_trials
        + [_compact_trial(trial, "finite_set_satellite_bias") for trial in bias_trials]
    )
    return {
        "full_bank": full_bank,
        "fitted_bank_sizes": [int(trial["satellite_count"]) for trial in bias_trials],
        "satellite_bias_trials": bias_trials,
        "satellite_bias_selection": bias_selection,
        "baseline_linear_trials": baseline_trials,
        "baseline_linear_selection": baseline_selection,
        "per_bank_penalized_incumbents": per_bank_incumbents,
        "combined_penalized_selection": combined_selection,
        "geometry": copy.deepcopy(geometry.geometry_receipt),
        "anchors_used": 0,
        "same_bank_finite_set_v2_seed_only": True,
        "zero_omega_initialization": True,
        "baseline_linear_v2_incumbent_retained": True,
        "all_source_ladder_banks_fitted": True,
        "omega_sigma_hz": OMEGA_SIGMA_HZ,
        "omega_sigma_semantics": "predeclared heuristic, not truth-calibrated",
        "omega_hard_bound_hz": None,
        "omega_score_penalty": "0.5 * (K - connected_components) * log(group_count)",
        "score_comparability": (
            "Conditional penalized-MAP approximation within this frozen finite-set family; "
            "not marginal evidence and not comparable across different sample spaces."
        ),
        "scope": (
            "Truth-free DS11-S02 satellite-constant-bias pilot. Every five-bank trial starts "
            "from its sealed finite-set linear-v2 parameters with omega=0. Omega is shared by "
            "receiver and channel for each selected satellite and has a fixed proper N(0, "
            "200 Hz^2) heuristic prior without a hard bound. Candidate banks, masses, finite-set "
            "probability, clutter rate, measurement sigma, tau prior and bounds, RX linear model "
            "and slope bounds remain frozen. Baseline trials remain explicit incumbents. No "
            "reference, known endpoint, curvature, relative-RX calibration, or categorical "
            "likelihood is read or fitted."
        ),
    }


def run_case(unit_id=PILOT_UNIT, run_id=DEFAULT_RUN_ID, *, budget_s_per_bank=15.0):
    if unit_id != PILOT_UNIT:
        raise ValueError(f"satellite-bias pilot is restricted to {PILOT_UNIT}")
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be one path component")
    source_path = ROOT / "runs" / SOURCE_RUN_ID / unit_id / "fit.json"
    source = json.loads(source_path.read_text())
    source_fit = _validate_source(source, unit_id)
    if len(source_fit["finite_set_trials"]) != EXPECTED_BANK_COUNT:
        raise ValueError("pilot source does not contain exactly five finite-set banks")
    output = ROOT / "runs" / run_id / unit_id
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    session_id = source["unit"]["session_ids"][0]
    bundle_path = ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py"
    bundle_directory = ROOT / "scans" / session_id
    source_paths = [ROOT / name for name in NUMERICAL_DEPENDENCIES] + [bundle_path]
    artifact_paths = [
        source_path,
        bundle_directory / "bundle.json",
        bundle_directory / "bundle.npz",
    ]
    source_hashes_prefit = snapshot_files(source_paths)
    artifact_hashes_prefit = snapshot_files(artifact_paths)
    bundle = load_module(f"finite_set_satellite_bias_bundle_{unit_id}", bundle_path)
    data = GroupMedianGeometryData(bundle.Data(bundle_directory))
    if data.geometry_receipt != source_fit["geometry"]:
        raise ValueError("pilot geometry does not reproduce sealed finite-set v2 geometry")
    started = time.monotonic()
    fitted = fit_satellite_bias_models(
        data,
        source,
        budget_s_per_bank=budget_s_per_bank,
    )
    assert_snapshot_unchanged(source_hashes_prefit)
    assert_snapshot_unchanged(artifact_hashes_prefit)
    source_hashes_postfit = snapshot_files(source_paths)
    artifact_hashes_postfit = snapshot_files(artifact_paths)
    receipt = {
        "schema": "finite-set-satellite-bias-fit/v1",
        "stage": "finite_set_satellite_bias",
        "unit": source["unit"],
        "dataset": source["dataset"],
        "run_id": run_id,
        "source_run_id": SOURCE_RUN_ID,
        "source_fit": str(source_path),
        "source_fit_sha256": digest(source_path),
        "source_hashes_prefit": source_hashes_prefit,
        "source_hashes_postfit": source_hashes_postfit,
        "bound_artifact_hashes_prefit": artifact_hashes_prefit,
        "bound_artifact_hashes_postfit": artifact_hashes_postfit,
        "prefit_hashes_reverified_unchanged_before_seal": True,
        "configuration": {
            "measurement_sigma_hz": MEASUREMENT_SIGMA_HZ,
            "omega_sigma_hz": OMEGA_SIGMA_HZ,
            "omega_sigma_semantics": "predeclared heuristic, not truth-calibrated",
            "omega_hard_bound_hz": None,
            "tau_sigma_s": TAU_SIGMA_S,
            "tau_bound_s": TAU_BOUND_S,
            "rx_slope_bound_hz_s": RX_SLOPE_BOUND_HZ_S,
            "finite_set_clutter_rate": float(source_fit["finite_set_clutter_rate"]),
            "finite_set_detection_probability": float(0.8 / len(source_fit["full_bank"])),
            "budget_s_per_bank": float(budget_s_per_bank),
            "external_case_deadline_s": 120.0,
            "optimizer": "analytic-gradient L-BFGS-B",
            "cpu_threads_required": 1,
        },
        "reference_read_before_seal": False,
        "known_endpoint_read_before_seal": False,
        "curvature_source_read": False,
        "relative_rx_calibration_read": False,
        "evaluation_written": False,
        "eligible_for_cohort": False,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "sealed_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "limitations": (
            "Omega is a fixed-scale phenomenological constant-Hz bias. Physical orbit Doppler "
            "errors scale with RF, while this pilot shares one additive Hz value across the "
            "10.94-11.69 GHz channels. Visibility connectivity does not prove assignment support, "
            "and the K-1 score penalty is a conditional penalized-MAP approximation."
        ),
    }
    output.mkdir(parents=True, exist_ok=False)
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    return fit_path, receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("unit_id", choices=(PILOT_UNIT,))
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--budget-s-per-bank", type=float, default=15.0)
    args = parser.parse_args()
    fit_path, receipt = run_case(
        args.unit_id,
        args.run_id,
        budget_s_per_bank=args.budget_s_per_bank,
    )
    selection = receipt["fit"]["satellite_bias_selection"]
    combined = receipt["fit"]["combined_penalized_selection"]
    print(
        json.dumps(
            {
                "unit_id": args.unit_id,
                "fit": str(fit_path),
                "fit_sha256": digest(fit_path),
                "elapsed_s": receipt["elapsed_s"],
                "satellite_bias_leader_k": selection["score_leader"]["satellite_count"],
                "satellite_bias_selection_resolved": selection["selection_resolved"],
                "combined_model": combined["score_leader"]["model"],
                "combined_leader_k": combined["score_leader"]["satellite_count"],
            }
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "BiasState",
    "evaluate_bias_state",
    "fit_satellite_bias_models",
    "fit_satellite_bias_trial",
    "receiver_satellite_topology",
    "run_case",
]
