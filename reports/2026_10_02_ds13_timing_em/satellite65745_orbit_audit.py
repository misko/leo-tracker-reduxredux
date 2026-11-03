"""Truth-conditioned timing and archived-orbit diagnostic for NORAD 65745."""

from __future__ import annotations

import inspect
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from all_visible_bank import load_expanded_scan
from compact_satellite_selection import _predict_matrix, timing_prior
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from finite_set_likelihood import circular_residual, prepare_finite_set_likelihood
from joint_inputs import LIGHT_SPEED_KM_S, _coordinates, _ecef
from plot_tle_doppler_overlay import CARRIER_HZ, orbital_curve
from prepare_scans import ROOT
from rf_calibration_diagnostic import rf_features
from rough_smoke import serializable

SESSION = "scan-fw-ffa1cc19d8d7c09f"
OUTPUT = ROOT / "satellite65745-orbit-audit"


def weighted_fit(design, residual, weights):
    design = np.asarray(design, dtype=float)
    residual = np.asarray(residual, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if (design.ndim != 2 or design.shape[0] != len(residual)
            or weights.shape != residual.shape or np.any(weights < 0)
            or not np.all(np.isfinite(design)) or not np.all(np.isfinite(residual))
            or not np.all(np.isfinite(weights)) or weights.sum() <= 0):
        raise ValueError("invalid weighted regression arrays")
    root = np.sqrt(weights)
    coefficients, _, rank, singular = np.linalg.lstsq(
        design * root[:, None], residual * root, rcond=None)
    error = residual - design @ coefficients
    return {"coefficients": coefficients, "rank": int(rank), "singular_values": singular,
            "weighted_rms_hz": float(np.sqrt(weights @ error**2 / weights.sum())),
            "effective_count": float(weights.sum()**2 / (weights @ weights))}


def physical_derivatives(data, parameters, satellite, times, step_s=0.02):
    center, _ = orbital_curve(data, parameters, [satellite], times)
    plus, _ = orbital_curve(data, parameters, [satellite], np.asarray(times) + step_s)
    minus, _ = orbital_curve(data, parameters, [satellite], np.asarray(times) - step_s)
    return center[:, 0], (plus[:, 0] - minus[:, 0]) / (2 * step_s), (
        plus[:, 0] - 2 * center[:, 0] + minus[:, 0]) / step_s**2


def direct_orbit_audit(data, parameters, satellite, receive_times):
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets

    provenance = data.bank_receipt["tle"]
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    matches = [item for item in archive.list_snapshots(provenance["provider"])
               if item.digest == provenance["digest"]
               and item.collected_utc_ns == provenance["collected_utc_ns"]]
    if len(matches) != 1:
        raise ValueError("pinned archived TLE is missing or ambiguous")
    payload = archive.read(matches[0])
    catalogue = parse_element_sets(payload)
    index = list(catalogue.satellite_numbers).index(65745)
    epoch_ns = catalogue.element_epoch_utc_ns()[index]
    origin = data.bank_receipt["ephemeris"]["origin_utc_ns"]
    position, velocity, valid = propagate_candidate_states(
        catalogue, [index], origin, receive_times,
        np.array([parameters[6 + satellite]]))
    if list(valid) != [index]:
        raise ValueError("direct pinned SGP4 propagation failed")
    delta = position[0, 0] - _ecef(*_coordinates(parameters[:2]))
    direction = delta / np.linalg.norm(delta, axis=1)[:, None]
    direct = -CARRIER_HZ * np.sum(direction * velocity[0, 0], axis=1) / LIGHT_SPEED_KM_S
    interpolated, _ = orbital_curve(data, parameters, [satellite], receive_times)
    error = interpolated[:, 0] - direct
    lines = payload.splitlines()
    element_lines = []
    for line_index, line in enumerate(lines):
        if line.startswith("1 65745"):
            element_lines = lines[line_index:line_index + 2]
            break
    paths = [inspect.getfile(propagate_candidate_states), inspect.getfile(TleArchiveReader),
             inspect.getfile(parse_element_sets), matches[0].path]
    return {
        "status": "complete", "pinned_snapshot": provenance,
        "element_epoch_utc_ns": epoch_ns,
        "element_epoch_utc": datetime.fromtimestamp(epoch_ns / 1e9, UTC).isoformat(),
        "capture_origin_utc_ns": origin, "age_at_capture_start_hours": (origin - epoch_ns) / 3.6e12,
        "element_lines": element_lines,
        "interpolation_minus_direct_max_abs_hz": float(np.max(np.abs(error))),
        "interpolation_minus_direct_rms_hz": float(np.sqrt(np.mean(error**2))),
        "interpolation_minus_direct_line": weighted_fit(
            np.column_stack([np.ones(len(receive_times)), receive_times - 265]),
            error, np.ones(len(error))),
        "receive_times_s": receive_times, "interpolation_minus_direct_hz": error,
        "source_hashes": snapshot_files(paths),
        "scope": "Direct SGP4 through the same pinned TEME-to-ECEF port; isolates interpolation. "
                 "Agreement cannot validate shared propagator/frame conventions or orbital truth.",
    }


def run():
    from scipy.optimize import minimize_scalar

    started = time.monotonic()
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    path = ROOT / "pruned-position-profile-grid" / f"{SESSION}.json"
    profile = json.loads(path.read_text())
    assert_snapshot_unchanged(profile["source_hashes"])
    hashes = {**profile["source_hashes"], **snapshot_files([
        __file__, path, ROOT / "plot_tle_doppler_overlay.py",
        ROOT / "all-visible-bank" / SESSION / "receipt.json",
        ROOT / "all-visible-bank" / SESSION / "expanded.npz",
    ])}
    point = next(item for item in profile["positions"] if item["label"] == "truth")
    fit = point["best"]
    data = load_expanded_scan(SESSION)
    parameters = np.asarray(fit["parameters"], dtype=float)
    if not np.array_equal(parameters[:2], point["fixed_position_km"]):
        raise ValueError("wrong fixed reference position")
    bank = np.asarray(profile["satellite_indices"], dtype=int)
    column = list(np.asarray(data.numbers)[bank]).index(65745)
    satellite = int(bank[column])
    prediction, visible = _predict_matrix(data, parameters, bank)
    _, features = rf_features(data.rf, data.receiver, False)
    coefficient = np.asarray(fit["rf_coefficient_hz_per_ghz"])
    rf_term = (features @ coefficient).ravel()
    prediction += rf_term[:, None]
    prepared = prepare_finite_set_likelihood(data.measured, data.group)
    options = {"sigma_hz": 200.0, "detection_probability": profile["detection_probability"],
               "clutter_rate": 2.0}
    baseline = prepared.evaluate(prediction, visible, **options)
    baseline_objective = -baseline["total_log_likelihood"] + timing_prior(parameters[6 + bank])
    if not np.isclose(baseline_objective, fit["objective"], rtol=0, atol=1e-6):
        raise ValueError("baseline does not reproduce")
    posterior = baseline["row_association_probability"][:, column]
    mask = (posterior >= 0.8) & (data.times >= 240) & (data.times <= 290)
    times = data.times[mask]
    weights = posterior[mask]
    if len(times) < 3:
        raise ValueError("insufficient 65745 support in requested interval")
    residual_raw = circular_residual(data.measured[mask], prediction[mask, column],
                                     prepared.alias_hz)
    residual = residual_raw * CARRIER_HZ / data.rf[mask]
    physical, derivative, curvature = physical_derivatives(data, parameters, satellite, times)
    linear = np.column_stack([np.ones(len(times)), times - 265])
    regressions = {
        "constant_only": weighted_fit(np.ones((len(times), 1)), residual, weights),
        "constant_and_time_slope": weighted_fit(linear, residual, weights),
        "extra_timing_only_s": weighted_fit(derivative[:, None], residual, weights),
        "constant_plus_timing_s": weighted_fit(
            np.column_stack([np.ones(len(times)), derivative]), residual, weights),
        "constant_plus_doppler_scale_fraction": weighted_fit(
            np.column_stack([np.ones(len(times)), physical]), residual, weights),
        "constant_plus_timing_rate_s_per_s": weighted_fit(
            np.column_stack([np.ones(len(times)), (times - 265) * derivative]), residual, weights),
    }
    channels = np.unique(data.channel[mask])
    channel_design = np.column_stack([data.channel[mask] == channel for channel in channels])
    regressions["channel_intercepts_only"] = weighted_fit(channel_design, residual, weights)
    for label, feature in (
        ("time_slope_hz_s", times - 265),
        ("extra_timing_s", derivative),
        ("doppler_scale_fraction", physical),
        ("timing_rate_s_per_s", (times - 265) * derivative),
    ):
        regressions["channel_intercepts_plus_" + label] = weighted_fit(
            np.column_stack([channel_design, feature]), residual, weights)
    trials = []
    timing_deadline = time.monotonic() + 30

    def objective(extra_tau):
        if time.monotonic() > timing_deadline:
            raise TimeoutError("scalar timing diagnostic deadline")
        trial_parameters = parameters.copy()
        trial_parameters[6 + satellite] += extra_tau
        new_prediction, new_visible = _predict_matrix(data, trial_parameters, [satellite])
        predictions = prediction.copy()
        visibility = visible.copy()
        predictions[:, column] = new_prediction[:, 0] + rf_term
        visibility[:, column] = new_visible[:, 0]
        likelihood = prepared.evaluate(predictions, visibility, **options)
        value = -likelihood["total_log_likelihood"] + timing_prior(trial_parameters[6 + bank])
        trials.append({"extra_tau_s": float(extra_tau), "objective": float(value)})
        return value

    status = "complete"
    success = False
    try:
        for extra in np.linspace(-3, 3, 13):
            objective(extra)
        best_grid = min(trials, key=lambda item: item["objective"])["extra_tau_s"]
        optimized = minimize_scalar(objective, bounds=(max(-3, best_grid - .5),
                                                       min(3, best_grid + .5)),
                                    method="bounded", options={"xatol": 1e-6, "maxiter": 40})
        success = bool(optimized.success)
    except TimeoutError:
        status = "budget_exhausted"
    winner = min(trials + [{"extra_tau_s": 0.0, "objective": baseline_objective}],
                 key=lambda item: item["objective"])
    amended = parameters.copy()
    amended[6 + satellite] += winner["extra_tau_s"]
    shifted, _ = orbital_curve(data, amended, [satellite], times)
    after = residual - (shifted[:, 0] - physical)
    direct = {"status": "unavailable"}
    try:
        direct = direct_orbit_audit(data, parameters, satellite, np.arange(240, 290.01, 0.125))
        hashes.update(direct["source_hashes"])
    except Exception as error:
        direct = {"status": "unavailable", "error": f"{type(error).__name__}: {error}"}
    receiver = np.asarray(data.receiver[mask], dtype=int)
    raw_derivative = derivative * data.rf[mask] / CARRIER_HZ
    result = {
        "schema": "ds13-satellite65745-orbit-audit/v1", "session": SESSION,
        "reference_position_conditioned": True, "existing_timing_s": parameters[6 + satellite],
        "existing_global_mean_timing_s": float(np.mean(parameters[6 + bank])),
        "existing_rx_slopes_hz_s": parameters[[3, 5]],
        "existing_rf_coefficient_hz_per_ghz": coefficient,
        "fixed_position_km": parameters[:2], "window_s": [240, 290],
        "high_posterior_row_count": len(times),
        "unique_group_count": len(np.unique(data.group[mask])),
        "points_by_rx": {str(rx): int(np.sum(receiver == rx)) for rx in (0, 1)},
        "derivatives": {
            "normalized_orbital_hz_s_range": [float(derivative.min()), float(derivative.max())],
            "raw_carrier_orbital_hz_s_range": [float(raw_derivative.min()),
                                              float(raw_derivative.max())],
            "raw_including_rx_slope_hz_s_range": [
                float(np.min(raw_derivative + parameters[3 + 2 * receiver])),
                float(np.max(raw_derivative + parameters[3 + 2 * receiver]))],
            "normalized_curvature_hz_s2_range": [float(curvature.min()), float(curvature.max())],
            "semantics": "Timing derivative of orbital Doppler; RX slope uses receive time and "
                         "is not shifted with orbital tau. Curvature at 0.02s finite steps may "
                         "include piecewise linear ephemeris knot effects.",
        },
        "frozen_posterior_window_regressions": regressions,
        "channel_intercept_column_order": channels,
        "channel_time_coverage": [{"channel": int(channel),
                                   "rows": int(np.sum(data.channel[mask] == channel)),
                                   "time_range_s": [
                                       float(times[data.channel[mask] == channel].min()),
                                       float(times[data.channel[mask] == channel].max())]}
                                  for channel in channels],
        "normalized_residual_line_after_single_tau": weighted_fit(linear, after, weights),
        "raw_residual_line_before": weighted_fit(linear, residual_raw, weights),
        "scalar_timing_refit": {"status": status, "optimizer_success": success,
                                "best": winner, "baseline_objective": baseline_objective,
                                "trials": trials, "bound_extra_tau_s": [-3, 3],
                                "scope": "Only 65745 total orbital timing changed; all stored "
                                         "rows, other satellite timings, RX/RF terms and position "
                                         "fixed. Existing full finite-set likelihood and zero-sum "
                                         "timing prior reevaluated; no additional prior or DOF."},
        "direct_orbit": direct, "source_hashes": hashes,
        "limitations": "Window regressions use frozen posterior-selected peaks and describe "
                       "correction shapes, not independently measured hardware/orbit errors. "
                       "Doppler scaling is a frequency fraction; timing rate is seconds/second "
                       "in orbital epoch only, not a demonstrated sample clock error. "
                       "A TLE age or numerical agreement alone cannot identify the residual cause.",
        "elapsed_s": time.monotonic() - started, "sealed_utc": datetime.now(UTC).isoformat(),
    }
    assert_snapshot_unchanged(hashes)
    OUTPUT.mkdir()
    with (OUTPUT / "receipt.json").open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    print(json.dumps({"output": str(OUTPUT), "elapsed_s": result["elapsed_s"],
                      "best_tau": winner, "direct_status": direct["status"]}))


if __name__ == "__main__":
    run()
