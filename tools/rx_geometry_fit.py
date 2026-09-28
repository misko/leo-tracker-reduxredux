"""Bounded calibration-only receiver-geometry association experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

from tools.rx_geometry_likelihood import (
    paired_log_likelihood,
    periodic_signal_ratio,
    update_score,
)

DIMENSIONS = {"D": 3, "S": 6, "T": 8}
PRIOR_SD = np.array([2.0, 1.0, 1.0, 0.5, 0.5, 0.5, 0.35, 0.35])
SIGMAS = (500.0, 2500.0, 10000.0)


def raw_features(lane, control=None):
    windows, components = lane["windows"], lane["components"]
    x = np.zeros((len(windows), len(components), 2, 8))
    visible = np.zeros((len(windows), len(components)), dtype=bool)
    mu = np.zeros_like(visible, dtype=float)
    for i, window in enumerate(windows):
        for j, prediction in enumerate(window["predictions"]):
            east, north, up = (prediction["los_enu_unit"][key] for key in ("east", "north", "up"))
            mu[i, j] = prediction["mu_canonical_rx0_hz"]
            visible[i, j] = prediction["visible"]
            for rid, sign in enumerate((-1.0, 1.0)):
                tilt = sign * math.sin(math.radians(10)) * east
                x[i, j, rid] = [
                    1.0,
                    sign,
                    math.log(window["sample_rate_hz"] / 5e6),
                    up,
                    north,
                    east,
                    tilt,
                    tilt * up,
                ]
    if control == "swap":
        x[..., 6:] *= -1
    elif control == "reverse":
        for role in ("reception", "held_frequency"):
            idx = np.array([i for i, w in enumerate(windows) if w["role"] == role])
            if len(idx):
                x[idx, ..., 3:] = x[idx[::-1], ..., 3:]
    return x, visible, mu


def prepare(document):
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported dataset schema")
    lanes = []
    for lane in document["lanes"]:
        if not lane["windows"]:
            continue
        x, visible, mu = raw_features(lane)
        roles = np.array([w["role"] for w in lane["windows"]])
        counts = np.array(
            [[len(w["observed"][rx]) for rx in ("rx0", "rx1")] for w in lane["windows"]], dtype=int
        )
        lanes.append(
            {
                "source": lane,
                "x": x,
                "visible": visible,
                "mu": mu,
                "roles": roles,
                "counts": counts,
                "prior": np.array(
                    [
                        c["log_prior"] if c["log_prior"] is not None else -np.inf
                        for c in lane["components"]
                    ]
                ),
            }
        )
    for split in ("calibration", "evaluation"):
        records = {
            item["source"]["lane"]["session_id"]
            for item in lanes
            if item["source"]["recording_split"] == split
        }
        if not records:
            raise ValueError(f"empty {split} population")
        for sid in records:
            record_roles = {
                r
                for item in lanes
                if item["source"]["lane"]["session_id"] == sid
                for r in item["roles"]
            }
            if not {"reception", "held_frequency"} <= record_roles:
                raise ValueError(f"incomplete temporal roles for {sid}")
    calibration = [
        item["x"][item["roles"] == "reception", :-1].reshape(-1, 8)
        for item in lanes
        if item["source"]["recording_split"] == "calibration"
    ]
    values = np.concatenate(calibration)
    center, scale = values.mean(axis=0), values.std(axis=0)
    center[0], scale[0] = 0.0, 1.0
    scale[scale < 1e-12] = 1.0
    for lane in lanes:
        lane["x"] = (lane["x"] - center) / scale
    return lanes, center, scale


def signal_arrays(lanes, sigma, *, calibration_only=False):
    for lane in lanes:
        source = lane["source"]
        sums = np.zeros((*lane["mu"].shape, 2))
        for i, window in enumerate(source["windows"]):
            if calibration_only and (
                source["recording_split"] != "calibration" or window["role"] != "reception"
            ):
                continue
            for rid, rx in enumerate(("rx0", "rx1")):
                f = np.array([c["canonical_rx0_hz"] for c in window["observed"][rx]])
                sums[i, :, rid] = periodic_signal_ratio(
                    f, lane["mu"][i], source["alias_period_hz"], sigma
                )
        lane["signal"] = sums


def lane_loglik(lane, beta, lambdas, *, x=None, selected=None):
    features = lane["x"] if x is None else x
    mask = slice(None) if selected is None else selected
    logits = features[mask, ..., : len(beta)] @ beta
    return paired_log_likelihood(
        lane["signal"][mask],
        lane["counts"][mask],
        logits,
        lane["visible"][mask],
        lambdas,
        lane["source"]["alias_period_hz"],
        latent_sd=1.0,
        quadrature_order=5,
    )


def objective(theta, lanes, dimension, fixed_lambdas=None):
    beta = theta[:dimension]
    lambdas = np.exp(theta[dimension:]) if fixed_lambdas is None else fixed_lambdas
    loss = 0.5 * np.sum((beta / PRIOR_SD[:dimension]) ** 2)
    if fixed_lambdas is None:
        loss += 0.5 * np.sum(((np.log(lambdas) - math.log(1.5)) / 1.5) ** 2)
    for lane in lanes:
        if lane["source"]["recording_split"] != "calibration":
            continue
        mask = lane["roles"] == "reception"
        ll = lane_loglik(lane, beta, lambdas, selected=mask)
        loss -= logsumexp(lane["prior"] + ll.sum(axis=0))
    return float(loss)


def fit(lanes, dimension, start, fixed_lambdas=None):
    bounds = [(None, None)] * dimension
    if fixed_lambdas is None:
        bounds += [(-5.0, 4.0)] * 2
    result = minimize(
        objective,
        start,
        args=(lanes, dimension, fixed_lambdas),
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 60, "maxfun": 600, "ftol": 1e-9},
    )
    return {
        "parameters": result.x.tolist(),
        "objective": float(result.fun),
        "success": bool(result.success),
        "message": str(result.message),
        "iterations": int(result.nit),
        "function_evaluations": int(result.nfev),
    }


def finite_logs(values):
    return [float(v) if np.isfinite(v) else None for v in values]


def evaluate(lanes, beta, lambdas, center, scale, control=None):
    recordings, posteriors = {}, []
    for lane in lanes:
        source = lane["source"]
        if source["recording_split"] != "evaluation":
            continue
        features = None
        if control:
            features = (raw_features(source, control)[0] - center) / scale
        ll = lane_loglik(lane, beta, lambdas, x=features)
        score = update_score(
            lane["prior"], ll, lane["roles"] == "reception", lane["roles"] == "held_frequency"
        )
        sid = source["lane"]["session_id"]
        record = recordings.setdefault(sid, {"held_windows": 0, "held_log_score": 0.0})
        record["held_windows"] += int(np.sum(lane["roles"] == "held_frequency"))
        record["held_log_score"] += float(np.sum(score.held_window_log_scores))
        posteriors.append(
            {
                "lane": source["lane"],
                "components": source["components"],
                "prior_log_weights": finite_logs(lane["prior"]),
                "reception_log_weights": finite_logs(score.reception_log_posterior),
                "held_log_weights": finite_logs(score.held_log_posterior),
                "held_window_log_scores": score.held_window_log_scores.tolist(),
            }
        )
    for row in recordings.values():
        row["log_score_per_window"] = row["held_log_score"] / row["held_windows"]
    return {
        "recordings": recordings,
        "lane_posteriors": posteriors,
        "equal_record_mean_log_score": float(
            np.mean([r["log_score_per_window"] for r in recordings.values()])
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payload = args.dataset.read_bytes()
    document = json.loads(payload)
    lanes, center, scale = prepare(document)
    grids = []
    for sigma in SIGMAS:
        signal_arrays(lanes, sigma, calibration_only=True)
        result = fit(lanes, 3, np.array([0.0, 0.0, 0.0, math.log(1.5), math.log(1.5)]))
        grids.append({"sigma_hz": sigma, **result})
        print(json.dumps({"nuisance_fit": grids[-1]}), flush=True)
    if not all(r["success"] for r in grids):
        raise RuntimeError("Nuisance grid did not converge; held evaluation not run")
    best = min(grids, key=lambda r: (r["objective"], r["sigma_hz"]))
    signal_arrays(lanes, best["sigma_hz"], calibration_only=True)
    lambdas = np.exp(best["parameters"][3:])
    fits, evaluations = {}, {}
    start = np.array(best["parameters"][:3])
    for arm, dimension in DIMENSIONS.items():
        start = np.pad(start, (0, dimension - len(start)))
        fitted = fit(lanes, dimension, start, lambdas)
        fits[arm] = fitted
        print(json.dumps({"arm": arm, "fit": fitted}), flush=True)
        if not fitted["success"]:
            raise RuntimeError(f"{arm} fit did not converge; held evaluation not run")
        start = np.array(fitted["parameters"])
    # Every calibration fit is frozen before any evaluation outcome is scored.
    signal_arrays(lanes, best["sigma_hz"])
    for arm, fitted in fits.items():
        evaluations[arm] = evaluate(lanes, np.array(fitted["parameters"]), lambdas, center, scale)
    for control in ("swap", "reverse"):
        evaluations[control] = evaluate(
            lanes, np.array(fits["T"]["parameters"]), lambdas, center, scale, control
        )
    contrasts = {}
    denominators = [
        {sid: row["held_windows"] for sid, row in e["recordings"].items()}
        for e in evaluations.values()
    ]
    if any(d != denominators[0] for d in denominators[1:]):
        raise ValueError("arm/control evaluation denominators differ")
    for left, right in (("T", "D"), ("S", "D"), ("T", "S"), ("T", "swap"), ("T", "reverse")):
        contrasts[f"{left}-{right}"] = {
            sid: evaluations[left]["recordings"][sid]["log_score_per_window"]
            - evaluations[right]["recordings"][sid]["log_score_per_window"]
            for sid in evaluations[left]["recordings"]
        }
    result = {
        "schema": "rx-geometry-association-pilot/v1",
        "status": "complete",
        "dataset_sha256": hashlib.sha256(payload).hexdigest(),
        "sigma_grid_fits": grids,
        "sigma_hz": best["sigma_hz"],
        "clutter_intensities": lambdas.tolist(),
        "feature_center": center.tolist(),
        "feature_scale": scale.tolist(),
        "fits": fits,
        "evaluations": evaluations,
        "contrasts_per_record": contrasts,
        "contrasts_equal_record_mean": {
            k: float(np.mean(list(v.values()))) for k, v in contrasts.items()
        },
        "interpretation": "Exploratory shared-window geometry association; no AR fit, "
        "satellite truth or geographic accuracy measurement.",
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
