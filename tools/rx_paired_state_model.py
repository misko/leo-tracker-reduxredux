"""Frequency-free paired binary-detection HMM with P/U/O response arms."""

from __future__ import annotations

import json
import math

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logsumexp

from tools.rx_presence_filter import forward_score

DIMENSIONS = {"P": 7, "U": 9, "O": 10}
BETA_SD = np.asarray([2.0, 1.0, 1.0, 2.0, 1.0, 1.0, 2.0, 0.5, 0.5, 0.5])


def _validated(lane):
    times = np.asarray(lane["times"], dtype=float)
    roles = np.asarray(lane["roles"])
    y = np.asarray(lane["y"])
    nuisance = np.asarray(lane["nuisance"], dtype=float)
    geometry = np.asarray(lane["geometry"], dtype=float)
    visible = np.asarray(lane["visible"])
    prior = np.asarray(lane["prior"], dtype=float)
    background = np.asarray(lane["background"], dtype=float)
    windows = len(times)
    if not np.all(np.isfinite(times)) or np.any(np.diff(times) < 0):
        raise ValueError("times must be finite and nondecreasing")
    if roles.shape != (windows,) or any(
        role not in {"reception", "held_frequency"} for role in roles
    ):
        raise ValueError("roles must contain only reception and held_frequency")
    if y.shape != (windows,) or not np.issubdtype(y.dtype, np.integer) or np.any((y < 0) | (y > 3)):
        raise ValueError("y must contain four-state integer receiver bits")
    if nuisance.shape != (windows, 3) or np.any(~np.isfinite(nuisance)):
        raise ValueError("nuisance must have shape (windows, 3) and be finite")
    if geometry.ndim != 3 or geometry.shape[0] != windows or geometry.shape[2] != 3:
        raise ValueError("geometry must have shape (windows, nominees, 3)")
    nominees = geometry.shape[1]
    if (
        np.any(~np.isfinite(geometry))
        or visible.shape != (windows, nominees)
        or visible.dtype != bool
    ):
        raise ValueError("geometry or visibility has incompatible values")
    if prior.shape != (nominees + 1,) or np.any(np.isnan(prior)) or np.any(np.isposinf(prior)):
        raise ValueError("prior must contain nominees plus final other")
    if not np.isfinite(logsumexp(prior)) or abs(float(logsumexp(prior))) > 1e-8:
        raise ValueError("prior must be log normalized")
    if (
        background.shape != (4,)
        or np.any(~np.isfinite(background))
        or np.any(background <= 0)
        or not math.isclose(float(background.sum()), 1.0, rel_tol=0, abs_tol=1e-10)
    ):
        raise ValueError("background must be four positive normalized probabilities")
    reception = roles == "reception"
    held = roles == "held_frequency"
    if np.any(held & ((np.cumsum(reception[::-1])[::-1] - reception) > 0)):
        raise ValueError("reception windows must precede held windows")
    return times, roles, y.astype(int), nuisance, geometry, visible, prior, background


def state_log_probabilities(lane, beta):
    """Return nominee four-state log probabilities with shape (W,K,4)."""
    _, _, _, nuisance, geometry, _, _, _ = _validated(lane)
    coefficient = np.asarray(beta, dtype=float)
    if (
        coefficient.ndim != 1
        or len(coefficient) not in DIMENSIONS.values()
        or np.any(~np.isfinite(coefficient))
    ):
        raise ValueError("beta must have P/U/O dimension and finite values")
    common = nuisance @ coefficient[:3]
    differential = nuisance @ coefficient[3:6]
    common = np.broadcast_to(common[:, None], geometry.shape[:2]).copy()
    differential = np.broadcast_to(differential[:, None], geometry.shape[:2]).copy()
    if len(coefficient) >= 9:
        common += coefficient[7] * geometry[..., 0] + coefficient[8] * geometry[..., 1]
    if len(coefficient) == 10:
        differential += coefficient[9] * geometry[..., 2]
    eta0 = common - differential
    eta1 = common + differential
    energies = np.stack(
        (
            np.zeros_like(eta0),
            eta0,
            eta1,
            eta0 + eta1 + coefficient[6],
        ),
        axis=-1,
    )
    return energies - logsumexp(energies, axis=-1, keepdims=True)


def relative_emissions(lane, beta):
    """Return absent, nominee, and other log likelihood ratios."""
    _, _, y, _, geometry, visible, _, background = _validated(lane)
    log_probability = state_log_probabilities(lane, beta)
    selected = np.take_along_axis(log_probability, y[:, None, None], axis=2)[..., 0]
    relative = selected - np.log(background[y])[:, None]
    relative[~visible] = 0.0
    # State zero is explicit absence; the final present state is catalogue-other.
    return np.column_stack((np.zeros(len(y)), relative, np.zeros(len(y))))


def score_lane(lane, selected):
    """Sequentially score one lane and export reference and state posteriors."""
    times, roles, y, _, _, _, prior, background = _validated(lane)
    beta = np.asarray(selected["beta"], dtype=float)
    emission = relative_emissions(lane, beta)
    score = forward_score(
        prior,
        emission,
        times,
        roles == "reception",
        roles == "held_frequency",
        float(selected["occupancy"]),
        float(selected["tau_s"]),
    )
    reference = np.log(background[y])
    return {
        "relative_log_scores": score.window_log_scores.tolist(),
        "reference_log_scores": reference.tolist(),
        "full_log_scores": (score.window_log_scores + reference).tolist(),
        "state_log_posteriors": score.state_log_posteriors.tolist(),
        "posterior_presence": score.posterior_presence.tolist(),
        "reception_log_posterior": score.reception_log_posterior.tolist(),
        "held_log_posterior": score.held_log_posterior.tolist(),
    }


def calibration_score(lanes, beta, occupancy, tau):
    """Exact batched reset recurrence; the scalar log-domain scorer is the oracle."""
    data = lanes if isinstance(lanes, dict) else _pack(lanes)
    if not 0 <= occupancy <= 1 or not np.isfinite(tau) or tau <= 0:
        raise ValueError("invalid occupancy or persistence")
    beta = np.asarray(beta)
    common = data["nuisance"] @ beta[:3]
    differential = data["nuisance"] @ beta[3:6]
    common = np.broadcast_to(common[..., None], data["geometry"].shape[:-1]).copy()
    differential = np.broadcast_to(differential[..., None], common.shape).copy()
    if len(beta) >= 9:
        common += beta[7] * data["geometry"][..., 0] + beta[8] * data["geometry"][..., 1]
    if len(beta) == 10:
        differential += beta[9] * data["geometry"][..., 2]
    energy = np.stack(
        (np.zeros_like(common), common - differential, common + differential, 2 * common + beta[6]),
        axis=-1,
    )
    logp = energy - logsumexp(energy, axis=-1, keepdims=True)
    chosen = np.take_along_axis(logp, data["y"][..., None, None], axis=-1)[..., 0]
    ratios = chosen - data["reference"][..., None]
    ratios[~data["visible"]] = 0.0
    emissions = np.pad(ratios, ((0, 0), (0, 0), (1, 1)))
    offsets = emissions.max(axis=-1)
    likelihood = np.exp(emissions - offsets[..., None])
    stationary = data["prior"] * occupancy
    stationary[:, 0] = 1 - occupancy
    alpha = stationary.copy()
    total = 0.0
    for i in range(data["active"].shape[1]):
        if i:
            persist = np.exp(-data["gaps"][:, i] / tau)
            alpha = alpha * persist[:, None] + stationary * (1 - persist[:, None])
        updated = alpha * likelihood[:, i]
        norm = updated.sum(axis=-1)
        if np.any(norm <= 0):
            raise ValueError("zero predictive probability")
        total += float(np.sum((np.log(norm) + offsets[:, i])[data["active"][:, i]]))
        alpha = updated / norm[:, None]
    return total


def _pack(lanes):
    if not lanes:
        raise ValueError("at least one calibration lane is required")
    validated = [_validated(lane) for lane in lanes]
    length = max(len(item[0]) for item in validated)
    nominees = max(item[4].shape[1] for item in validated)
    shape = (len(lanes), length)
    data = {
        "nuisance": np.zeros((*shape, 3)),
        "geometry": np.zeros((*shape, nominees, 3)),
        "visible": np.zeros((*shape, nominees), dtype=bool),
        "y": np.zeros(shape, dtype=int),
        "reference": np.zeros(shape),
        "prior": np.zeros((len(lanes), nominees + 2)),
        "gaps": np.zeros(shape),
        "active": np.zeros(shape, dtype=bool),
    }
    for index, (times, _, y, nu, geom, visible, prior, bg) in enumerate(validated):
        w, k = geom.shape[:2]
        data["nuisance"][index, :w] = nu
        data["geometry"][index, :w, :k] = geom
        data["visible"][index, :w, :k] = visible
        data["y"][index, :w] = y
        data["reference"][index, :w] = np.log(bg[y])
        data["prior"][index, 1 : k + 1] = np.exp(prior[:-1])
        data["prior"][index, -1] = np.exp(prior[-1])
        data["gaps"][index, 1:w] = np.diff(times)
        data["active"][index, :w] = True
    return data


def _objective(theta, lanes, dimension):
    beta = theta[:dimension]
    occupancy = float(expit(theta[-2]))
    tau = math.exp(theta[-1])
    penalty = 0.5 * float(np.sum((beta / BETA_SD[:dimension]) ** 2))
    penalty += 0.5 * (theta[-2] / 2.0) ** 2
    penalty += 0.5 * (theta[-1] / 1.5) ** 2
    return -calibration_score(lanes, beta, occupancy, tau) + penalty


def _receipt(result, lanes, dimension):
    theta = np.asarray(result.x, dtype=float)
    score = calibration_score(
        lanes, theta[:dimension], float(expit(theta[-2])), math.exp(theta[-1])
    )
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


def _select(receipts, dimension, arm):
    converged = [receipt for receipt in receipts if receipt["success"]]
    if not converged:
        raise RuntimeError(f"no {arm} optimizer start converged")
    best = max(converged, key=lambda receipt: receipt["map_gain"])
    if best["map_gain"] <= 0:
        return {
            "beta": [0.0] * dimension,
            "occupancy": 0.0,
            "tau_s": 1.0,
            "calibration_relative_log_evidence": 0.0,
            "map_penalty": 0.0,
            "map_gain": 0.0,
            "null_selected": True,
        }
    parameters = np.asarray(best["parameters"], dtype=float)
    return {
        "beta": parameters[:dimension].tolist(),
        "occupancy": float(expit(parameters[-2])),
        "tau_s": math.exp(parameters[-1]),
        "calibration_relative_log_evidence": best["calibration_relative_log_evidence"],
        "map_penalty": best["map_penalty"],
        "map_gain": best["map_gain"],
        "null_selected": False,
    }


def _fit_arm(arm, lanes, starts):
    dimension = DIMENSIONS[arm]
    bounds = [(-8.0, 8.0)] * dimension
    if arm == "O":
        bounds[9] = (0.0, 8.0)
    bounds += [(-7.0, 7.0), (math.log(0.1), math.log(10.0))]
    receipts = []
    for name, start in starts:
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
    return {"candidates": receipts, "selected": _select(receipts, dimension, arm)}


def fit_arms(lanes):
    """Fit nested P/U/O arms with two starts and null-safe MAP selection."""
    lanes = _pack(lanes)
    fits = {}
    neutral_p = np.zeros(DIMENSIONS["P"] + 2)
    fits["P"] = _fit_arm("P", lanes, (("neutral", neutral_p), ("nested", neutral_p.copy())))
    parent = fits["P"]["selected"]
    parent_nuisance = (
        np.zeros(2)
        if parent["null_selected"]
        else np.asarray(
            [math.log(parent["occupancy"] / (1 - parent["occupancy"])), math.log(parent["tau_s"])]
        )
    )
    nested_u = np.r_[parent["beta"], np.zeros(2), parent_nuisance]
    neutral_u = np.zeros(DIMENSIONS["U"] + 2)
    fits["U"] = _fit_arm("U", lanes, (("neutral", neutral_u), ("nested_P", nested_u)))
    parent = fits["U"]["selected"]
    parent_nuisance = (
        np.zeros(2)
        if parent["null_selected"]
        else np.asarray(
            [math.log(parent["occupancy"] / (1 - parent["occupancy"])), math.log(parent["tau_s"])]
        )
    )
    nested_o = np.r_[parent["beta"], 0.0, parent_nuisance]
    neutral_o = np.zeros(DIMENSIONS["O"] + 2)
    fits["O"] = _fit_arm("O", lanes, (("neutral", neutral_o), ("nested_U", nested_o)))
    return {"schema": "rx-paired-state-fit/v1", "fits": fits}
