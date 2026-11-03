"""Joint MAP calibration of geometry emissions and reset-process presence."""

from __future__ import annotations

import json
import math

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logsumexp

from tools.rx_empirical_signal import paired_relative_log_likelihood

DIMENSIONS = {"D": 3, "E": 4, "S": 6, "T": 8}
BETA_SD = np.array([2.0, 1.0, 1.0, 0.5, 0.5, 0.5, 0.35, 0.35])


def _validate_lane(lane, dimension):
    x = np.asarray(lane["x"], dtype=float)
    signal = np.asarray(lane["signal"], dtype=float)
    counts = np.asarray(lane["counts"])
    visible = np.asarray(lane["visible"], dtype=bool)
    prior = np.asarray(lane["prior"], dtype=float)
    times = np.asarray(lane["times"], dtype=float)
    count_logs = np.asarray(lane["log_count_probabilities"], dtype=float)
    if x.ndim != 4 or x.shape[2:] != (2, 8):
        raise ValueError("x must have shape (windows, nominees, 2, 8)")
    windows, nominees = x.shape[:2]
    if signal.shape != (windows, nominees, 2):
        raise ValueError("signal has incompatible shape")
    if counts.shape != (windows, 2) or visible.shape != (windows, nominees):
        raise ValueError("counts or visibility has incompatible shape")
    if prior.shape != (nominees,) or not np.isfinite(logsumexp(prior)):
        raise ValueError("prior must contain finite nomination mass")
    if abs(float(logsumexp(prior))) > 1e-8:
        raise ValueError("prior must be log normalized")
    if times.shape != (windows,) or not np.all(np.isfinite(times)) or np.any(np.diff(times) < 0):
        raise ValueError("times must be finite and sorted")
    if count_logs.shape not in {(windows, 2, 2), (windows, nominees, 2, 2)}:
        raise ValueError("log_count_probabilities has incompatible shape")
    if dimension < 1 or dimension > 8:
        raise ValueError("invalid beta dimension")
    return x, signal, counts, visible, prior, times, count_logs


def calibration_score(lanes, beta, occupancy, tau):
    """Return summed calibration relative evidence using a batched forward pass."""
    coefficient = np.asarray(beta, dtype=float)
    if coefficient.ndim != 1 or not np.all(np.isfinite(coefficient)):
        raise ValueError("beta must be a finite one-dimensional array")
    if not np.isfinite(occupancy) or not 0.0 <= occupancy <= 1.0:
        raise ValueError("occupancy must lie in [0, 1]")
    if not np.isfinite(tau) or tau <= 0:
        raise ValueError("tau must be positive and finite")
    if not lanes:
        raise ValueError("at least one calibration lane is required")

    validated = [_validate_lane(lane, len(coefficient)) for lane in lanes]
    lane_count = len(validated)
    max_windows = max(len(item[5]) for item in validated)
    max_states = max(len(item[4]) + 1 for item in validated)
    max_nominees = max_states - 1
    total_windows = sum(len(item[5]) for item in validated)
    emissions = np.full((lane_count, max_windows, max_states), -np.inf)
    stationary = np.full((lane_count, max_states), -np.inf)
    times = np.zeros((lane_count, max_windows), dtype=float)
    active = np.zeros((lane_count, max_windows), dtype=bool)
    log_absent = -np.inf if occupancy == 1.0 else math.log1p(-occupancy)
    log_present = -np.inf if occupancy == 0.0 else math.log(occupancy)
    batch_x = np.zeros((total_windows, max_nominees, 2, 8), dtype=float)
    batch_signal = np.zeros((total_windows, max_nominees, 2), dtype=float)
    batch_counts = np.zeros((total_windows, 2), dtype=int)
    batch_visible = np.zeros((total_windows, max_nominees), dtype=bool)
    batch_count_logs = np.full((total_windows, max_nominees, 2, 2), -np.inf)
    # Dummy padded components need a finite observed-count baseline even though
    # visibility forces their final relative likelihood to zero.
    batch_count_logs[..., 0, 0] = 0.0
    slices = []
    offset = 0
    for lane_index, (x, signal, counts, visible, prior, lane_times, count_logs) in enumerate(
        validated
    ):
        windows, nominees = signal.shape[:2]
        selected = slice(offset, offset + windows)
        slices.append(selected)
        batch_x[selected, :nominees] = x
        batch_signal[selected, :nominees] = signal
        batch_counts[selected] = counts
        batch_visible[selected, :nominees] = visible
        if count_logs.ndim == 3:
            batch_count_logs[selected, :nominees] = count_logs[:, None]
        else:
            batch_count_logs[selected, :nominees] = count_logs
        stationary[lane_index, 0] = log_absent
        stationary[lane_index, 1 : nominees + 1] = log_present + prior
        times[lane_index, :windows] = lane_times
        active[lane_index, :windows] = True
        offset += windows

    batch_logits = batch_x[..., : len(coefficient)] @ coefficient
    batch_relative = paired_relative_log_likelihood(
        batch_count_logs,
        batch_signal,
        batch_counts,
        batch_logits,
        batch_visible,
        latent_sd=1.0,
        quadrature_order=5,
    )
    for lane_index, (selected, item) in enumerate(zip(slices, validated, strict=True)):
        windows, nominees = item[1].shape[:2]
        emissions[lane_index, :windows, 0] = 0.0
        emissions[lane_index, :windows, 1 : nominees + 1] = batch_relative[selected, :nominees]

    alpha = stationary.copy()
    total = 0.0
    for window in range(max_windows):
        current = active[:, window]
        if window:
            continuing = current & active[:, window - 1]
            gaps = times[:, window] - times[:, window - 1]
            log_persist = -gaps / tau
            log_refresh = np.full(lane_count, -np.inf)
            positive_gap = gaps > 0
            log_refresh[positive_gap] = np.log(-np.expm1(log_persist[positive_gap]))
            predicted = np.logaddexp(
                alpha + log_persist[:, None], stationary + log_refresh[:, None]
            )
            alpha[continuing] = predicted[continuing]
        updated = alpha + emissions[:, window]
        scores = logsumexp(updated, axis=1)
        if np.any(~np.isfinite(scores[current])):
            raise ValueError("calibration window has zero predictive density")
        total += float(scores[current].sum())
        alpha[current] = updated[current] - scores[current, None]
    return total


def _objective(theta, lanes, dimension):
    beta = theta[:dimension]
    logit_occupancy, log_tau = theta[-2:]
    occupancy = float(expit(logit_occupancy))
    tau = math.exp(log_tau)
    penalty = 0.5 * float(np.sum((beta / BETA_SD[:dimension]) ** 2))
    penalty += 0.5 * (logit_occupancy / 2.0) ** 2
    penalty += 0.5 * (log_tau / 1.5) ** 2
    return -calibration_score(lanes, beta, occupancy, tau) + penalty


def _receipt(result, lanes, dimension):
    theta = np.asarray(result.x, dtype=float)
    beta = theta[:dimension]
    occupancy = float(expit(theta[-2]))
    tau = math.exp(theta[-1])
    score = calibration_score(lanes, beta, occupancy, tau)
    penalty = float(result.fun + score)
    return {
        "parameters": theta.tolist(),
        "success": bool(result.success),
        "message": str(result.message),
        "iterations": int(result.nit),
        "function_evaluations": int(result.nfev),
        "calibration_relative_log_evidence": score,
        "map_penalty": penalty,
        "map_gain": score - penalty,
    }


def fit_arms(lanes, old_fits):
    """Fit D/E/S/T in order and return optimizer receipts plus null-safe selections."""
    output = {}
    previous_theta = None
    previous_was_null = False
    for arm, dimension in DIMENSIONS.items():
        neutral = np.r_[[-2.0], np.zeros(dimension - 1), 0.0, 0.0]
        if arm == "D":
            nested_beta = np.asarray(old_fits["D"]["parameters"], dtype=float)
            if nested_beta.shape != (dimension,):
                raise ValueError("old D fit has incompatible parameters")
            nested_nuisance = np.zeros(2)
        else:
            nested_beta = np.pad(previous_theta[:-2], (0, dimension - len(previous_theta[:-2])))
            nested_nuisance = np.zeros(2) if previous_was_null else previous_theta[-2:]
        nested = np.r_[nested_beta, nested_nuisance]
        bounds = [(-12.0, 12.0)] * dimension + [(-7.0, 7.0), (math.log(0.1), math.log(10.0))]
        receipts = []
        for name, start in (("neutral", neutral), ("nested", nested)):
            result = minimize(
                _objective,
                start,
                args=(lanes, dimension),
                method="L-BFGS-B",
                bounds=bounds,
                options={"maxiter": 100, "maxfun": 2000, "ftol": 1e-9, "gtol": 1e-5},
            )
            receipt = {"start": name, **_receipt(result, lanes, dimension)}
            receipts.append(receipt)
            print(json.dumps({"arm": arm, "candidate": receipt}), flush=True)
        converged = [receipt for receipt in receipts if receipt["success"]]
        if not converged:
            raise RuntimeError(f"no {arm} optimizer start converged")
        best = max(converged, key=lambda receipt: receipt["map_gain"])
        if best["map_gain"] <= 0:
            selected = {
                "beta": [0.0] * dimension,
                "occupancy": 0.0,
                "tau_s": 1.0,
                "calibration_relative_log_evidence": 0.0,
                "map_penalty": 0.0,
                "map_gain": 0.0,
                "null_selected": True,
            }
            selected_theta = np.r_[np.zeros(dimension), 0.0, 0.0]
        else:
            parameters = np.asarray(best["parameters"], dtype=float)
            selected = {
                "beta": parameters[:dimension].tolist(),
                "occupancy": float(expit(parameters[-2])),
                "tau_s": math.exp(parameters[-1]),
                "calibration_relative_log_evidence": best["calibration_relative_log_evidence"],
                "map_penalty": best["map_penalty"],
                "map_gain": best["map_gain"],
                "null_selected": False,
            }
            selected_theta = parameters
        output[arm] = {"candidates": receipts, "selected": selected}
        previous_theta = selected_theta
        previous_was_null = selected["null_selected"]
    return {"schema": "rx-joint-geometry-fit/v1", "fits": output}
