"""Constrained nominal two-receiver beam feature and D/E/B MAP fitter."""

from __future__ import annotations

import json
import math

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from tools.rx_joint_geometry_fit import BETA_SD, calibration_score

ARMS = {"D": 3, "E": 4, "B": 4}


def _raw_los(lane):
    windows, nominees = lane["x"].shape[:2]
    east = np.empty((windows, nominees), dtype=float)
    up = np.empty((windows, nominees), dtype=float)
    if len(lane["indices"]) != windows:
        raise ValueError("lane indices do not match feature windows")
    for local_index, source_index in enumerate(lane["indices"]):
        predictions = lane["source"]["windows"][source_index].get("predictions", [])
        if len(predictions) != nominees:
            raise ValueError("prediction/nominee cardinality mismatch")
        for nominee_index, prediction in enumerate(predictions):
            los = prediction.get("los_enu_unit", {})
            east[local_index, nominee_index] = float(los.get("east", np.nan))
            up[local_index, nominee_index] = float(los.get("up", np.nan))
    if np.any(~np.isfinite(east)) or np.any(~np.isfinite(up)):
        raise ValueError("LOS east/up values must be finite")
    return east, up


def beam_features(lanes, beam_scale, tilt_deg=10.0, control=None):
    """Return lane copies whose fourth feature is a reception-centered nominal beam term."""
    if not math.isfinite(float(beam_scale)) or beam_scale <= 0:
        raise ValueError("beam_scale must be positive and finite")
    if not math.isfinite(float(tilt_deg)):
        raise ValueError("tilt_deg must be finite")
    if control not in (None, "swap", "geometryreverse", "geometrypermute"):
        raise ValueError("unsupported nominal-beam control")
    angle = math.radians(float(tilt_deg))
    output = []
    for lane in lanes:
        x = np.asarray(lane["x"], dtype=float)
        if x.ndim != 4 or x.shape[2:] != (2, 8):
            raise ValueError("x must have shape (windows, nominees, 2, 8)")
        roles = np.asarray(lane["roles"])
        reception = roles == "reception"
        if roles.shape != (len(x),) or not np.any(reception):
            raise ValueError("each lane needs reception windows for beam centering")
        east, up = _raw_los(lane)
        centered_east = east - east[reception].mean(axis=0, keepdims=True)
        centered_up = up - up[reception].mean(axis=0, keepdims=True)
        signs = np.asarray([-1.0, 1.0])
        if control == "swap":
            signs = -signs
        beam = (
            math.cos(angle) * centered_up[..., None]
            + math.sin(angle) * centered_east[..., None] * signs
        ) / beam_scale
        if control == "geometryreverse":
            for role in ("reception", "held_frequency"):
                indices = np.flatnonzero(roles == role)
                if len(indices):
                    beam[indices] = beam[indices[::-1]]
        elif control == "geometrypermute" and beam.shape[1] > 1:
            beam = np.roll(beam, 1, axis=1)
        changed = {**lane, "x": x.copy()}
        changed["x"][..., 4:8] = 0.0
        changed["x"][..., 3] = beam
        output.append(changed)
    return output


def fit_shared_beam_scale(training_lanes):
    """Return the shared RMS reception-centered raw-up scale."""
    values = []
    for lane in training_lanes:
        roles = np.asarray(lane["roles"])
        reception = roles == "reception"
        if not np.any(reception):
            raise ValueError("training lane has no reception windows")
        _, up = _raw_los(lane)
        centered = up - up[reception].mean(axis=0, keepdims=True)
        values.append(np.repeat(centered[reception, ..., None], 2, axis=2).reshape(-1))
    if not values:
        raise ValueError("no training lanes for beam scaling")
    scale = math.sqrt(float(np.mean(np.concatenate(values) ** 2)))
    return 1.0 if scale < 1e-12 else scale


def _objective(theta, lanes, dimension):
    beta = np.asarray(theta[:dimension], dtype=float)
    logit_occupancy, log_tau = theta[-2:]
    occupancy = float(expit(logit_occupancy))
    tau = math.exp(log_tau)
    penalty = 0.5 * float(np.sum((beta / BETA_SD[:dimension]) ** 2))
    penalty += 0.5 * (logit_occupancy / 2.0) ** 2
    penalty += 0.5 * (log_tau / 1.5) ** 2
    return -calibration_score(lanes, beta, occupancy, tau) + penalty


def _receipt(result, lanes, dimension):
    theta = np.asarray(result.x, dtype=float)
    occupancy = float(expit(theta[-2]))
    tau = math.exp(theta[-1])
    score = calibration_score(lanes, theta[:dimension], occupancy, tau)
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


def _selected(receipts, dimension, arm):
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


def _fit(arm, lanes, starts, dimension):
    bounds = [(-12.0, 12.0)] * dimension
    if arm in ("E", "B"):
        bounds[-1] = (0.0, 12.0)
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
    return {"candidates": receipts, "selected": _selected(receipts, dimension, arm)}


def fit_beam_arms(e_lanes, b_lanes):
    """Fit D once, then equal-capacity monotone E and B models from the selected D seed."""
    neutral_d = np.asarray([-2.0, 0.0, 0.0, 0.0, 0.0])
    d_fit = _fit("D", e_lanes, (("neutral", neutral_d), ("nested", neutral_d.copy())), 3)
    selected_d = d_fit["selected"]
    if selected_d["null_selected"]:
        nested_nuisance = np.zeros(2)
    else:
        nested_nuisance = np.asarray(
            [
                math.log(selected_d["occupancy"] / (1.0 - selected_d["occupancy"])),
                math.log(selected_d["tau_s"]),
            ]
        )
    nested = np.r_[selected_d["beta"], 0.0, nested_nuisance]
    neutral = np.asarray([-2.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    e_fit = _fit("E", e_lanes, (("neutral", neutral), ("nested_D", nested)), 4)
    b_fit = _fit("B", b_lanes, (("neutral", neutral.copy()), ("nested_D", nested.copy())), 4)
    return {"schema": "rx-nominal-beam-fit/v1", "fits": {"D": d_fit, "E": e_fit, "B": b_fit}}
