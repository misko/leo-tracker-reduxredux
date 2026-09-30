#!/usr/bin/env python3
"""Corrected DS6 stationary Doppler solver over frozen DS7 numerical banks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import brentq, minimize
from scipy.special import gammaln, logsumexp

LIGHT_KM_S = 299_792.458
REFERENCE_RF_HZ = 11_200_000_000.0


def fit_stationary_offset(values: np.ndarray, sigma: float = 100.0) -> tuple[float, dict]:
    """Reproduce DS6's finite multimode Student-t4 offset profiler."""
    values = np.asarray(values, dtype=float)
    center = float(np.median(values))
    y = values - center

    def loss(v):
        return float(
            2.5 * np.log1p(((y - v) / sigma) ** 2 / 4).sum() + 0.5 * ((center + v) / 1e6) ** 2
        )

    def derivative(v):
        r = v - y
        return float(np.sum(5 * r / (4 * sigma * sigma + r * r)) + (center + v) / 1e12)

    def curvature(v):
        r = v - y
        den = 4 * sigma * sigma + r * r
        return float(np.sum(5 * (4 * sigma * sigma - r * r) / den**2) + 1e-12)

    lower, upper = min(float(y.min()), -center), max(float(y.max()), -center)
    if lower == upper:
        return center + lower, {"converged": True, "gradient": 0.0, "roots": 1}
    starts = np.unique(np.r_[np.quantile(y, np.linspace(0, 1, 9)), 0.0])
    guesses, active = starts.copy(), np.ones(len(starts), dtype=bool)
    for _ in range(100):
        r = (y[None, :] - guesses[:, None]) / sigma
        weights = 5 / (4 + r * r)
        new = ((weights * y).sum(axis=1) - sigma * sigma * center / 1e12) / (
            weights.sum(axis=1) + sigma * sigma / 1e12
        )
        done = np.abs(new - guesses) < 1e-6
        guesses = np.where(active, new, guesses)
        active &= ~done
        if not active.any():
            break
    distances = np.array([1e-4, 0.01, 1.0, 10.0, 100.0, 1000.0])
    nodes = np.unique(
        np.r_[
            lower,
            upper,
            starts,
            guesses,
            np.clip(guesses[:, None] - distances, lower, upper).ravel(),
            np.clip(guesses[:, None] + distances, lower, upper).ravel(),
        ]
    )
    residual = nodes[:, None] - y[None, :]
    gradients = (
        np.sum(5 * residual / (4 * sigma * sigma + residual * residual), axis=1)
        + (center + nodes) / 1e12
    )
    roots = []
    for i in range(len(nodes) - 1):
        if gradients[i] <= 0 <= gradients[i + 1]:
            root = brentq(derivative, nodes[i], nodes[i + 1], xtol=1e-9, rtol=1e-14)
            if curvature(root) > 0:
                roots.append(root)
    if not roots:
        raise RuntimeError("no positive-curvature stationary offset")
    best = min(roots, key=loss)
    gradient = derivative(best)
    return center + best, {
        "converged": abs(gradient) < 1e-7,
        "gradient": gradient,
        "roots": len(roots),
    }


def profile(residual: np.ndarray, mask: np.ndarray):
    offsets, audits = [], []
    for row in residual:
        offset, audit = fit_stationary_offset(row[mask])
        offsets.append(offset)
        audits.append(audit)
    offsets = np.asarray(offsets)
    z = (residual - offsets[:, None]) / 100.0
    density = (
        gammaln(2.5)
        - gammaln(2)
        - 0.5 * np.log(4 * np.pi)
        - np.log(100.0)
        - 2.5 * np.log1p(z * z / 4)
    )
    train = density[:, mask].sum(axis=1) - 0.5 * offsets**2 / 1e12
    joint = density.sum(axis=1) - 0.5 * offsets**2 / 1e12
    return train, joint, audits, offsets


def site(latitude_deg: float, longitude_deg: float) -> tuple[np.ndarray, np.ndarray]:
    lat, lon = np.radians([latitude_deg, longitude_deg])
    a, e2 = 6378.137, 6.69437999014e-3
    n = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    rec = np.array(
        [n * np.cos(lat) * np.cos(lon), n * np.cos(lat) * np.sin(lon), n * (1 - e2) * np.sin(lat)]
    )
    up = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    return rec, up


class Stationary:
    def __init__(self, document: dict, config: dict):
        self.document = document
        self.center = config["geographic_prior_center_deg"]
        self.taus = np.asarray(config["timing_grid_s"], dtype=float)

    def coordinates(self, x):
        lat = self.center[0] + x[1] / 111.195
        lon = self.center[1] + x[0] / (111.195 * math.cos(math.radians(self.center[0])))
        return float(lat), float(lon)

    def prediction(self, track, x):
        lat, lon = self.coordinates(x)
        rec, up = site(lat, lon)
        tau = x[2]
        hi = min(max(int(np.searchsorted(self.taus, tau, side="right")), 1), len(self.taus) - 1)
        lo = hi - 1
        weight = (tau - self.taus[lo]) / (self.taus[hi] - self.taus[lo])
        pos = (
            track["candidate_position_km"][:, lo] * (1 - weight)
            + track["candidate_position_km"][:, hi] * weight
        )
        vel = (
            track["candidate_velocity_km_s"][:, lo] * (1 - weight)
            + track["candidate_velocity_km_s"][:, hi] * weight
        )
        unit = pos - rec
        unit /= np.linalg.norm(unit, axis=-1)[..., None]
        prediction = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(unit * vel, axis=-1)
        return prediction, np.any((unit @ up)[:, track["mask"]] >= 0, axis=1)

    def evaluate(self, x, gradient=False):
        total = 0.0
        derivative = np.zeros(3)
        for track in self.document["tracks"]:
            prediction, visible = self.prediction(track, x)
            residual = track["y"][None, :] - prediction
            score, _, audits, offsets = profile(residual, track["mask"])
            if not all(a["converged"] for a in audits):
                raise RuntimeError("offset stationarity check failed")
            score = np.where(visible, score, -np.inf)
            normal = logsumexp(score)
            total += float(normal - math.log(track["catalogue_size"]))
            if gradient:
                centered = residual[:, track["mask"]] - offsets[:, None]
                slope = 5 * centered / (40000 + centered**2)
                responsibility = np.exp(score - normal)
                for axis in range(3):
                    step = 1e-4 if axis < 2 else 1e-5
                    plus, minus = x.copy(), x.copy()
                    plus[axis] += step
                    minus[axis] -= step
                    if axis == 2:
                        plus[axis], minus[axis] = min(5.0, plus[axis]), max(-5.0, minus[axis])
                    delta = (self.prediction(track, plus)[0] - self.prediction(track, minus)[0]) / (
                        plus[axis] - minus[axis]
                    )
                    derivative[axis] += float(
                        responsibility @ np.sum(slope * delta[:, track["mask"]], axis=1)
                    )
        return total, derivative


class JointObjective:
    def __init__(self, documents, config):
        self.models = [Stationary(document, config) for document in documents]

    def coordinates(self, x):
        return self.models[0].coordinates(x)

    def value_gradient(self, x):
        value, gradient = 0.0, np.zeros_like(x)
        for index, model in enumerate(self.models):
            local = np.array([x[0], x[1], x[index + 2]])
            score, local_gradient = model.evaluate(local, True)
            value += score
            gradient[:2] += local_gradient[:2]
            gradient[index + 2] += local_gradient[2]
        return -value, -gradient


def load_documents(request: dict) -> list[dict]:
    documents = []
    for row in request["inputs"]:
        observations = [a for a in row["artifacts"] if a["kind"] == "observations"]
        candidates = [a for a in row["artifacts"] if a["kind"] == "candidates"]
        candidate_json = [a for a in candidates if Path(a["path"]).suffix == ".json"]
        candidate_npz = [a for a in candidates if Path(a["path"]).suffix == ".npz"]
        if len(observations) != 1 or len(candidate_json) != 1 or len(candidate_npz) != 1:
            raise ValueError("one observations, candidate manifest and bank required")
        doc = json.loads(Path(observations[0]["path"]).read_text())
        if (
            doc.get("schema") != "ds7-baseline-track-export/v1"
            or doc.get("session_id") != row["session_id"]
            or doc.get("manifest_sha256") != row["manifest_sha256"]
        ):
            raise ValueError("observation binding mismatch")
        bank_path = Path(candidate_npz[0]["path"])
        manifest = json.loads(Path(candidate_json[0]["path"]).read_text())
        if (
            manifest["session_id"] != row["session_id"]
            or manifest["manifest_sha256"] != row["manifest_sha256"]
        ):
            raise ValueError("candidate binding mismatch")
        actual_tracks_sha256 = (
            "sha256:" + hashlib.sha256(Path(observations[0]["path"]).read_bytes()).hexdigest()
        )
        if manifest.get("tracks_sha256") != actual_tracks_sha256:
            raise ValueError("candidate bank does not bind observation bytes")
        banks = np.load(bank_path, allow_pickle=False)
        by_track = {t["track_id"]: t for t in doc["tracks"]}
        manifest_ids = [item["track_id"] for item in manifest["tracks"]]
        if len(by_track) != len(doc["tracks"]) or set(manifest_ids) != set(by_track):
            raise ValueError("candidate bank track coverage differs from observations")
        timing_grid = banks["timing_grid_s"]
        if not np.array_equal(timing_grid, np.asarray(request["config"]["timing_grid_s"])):
            raise ValueError("candidate timing grid differs from model config")
        combined = []
        for item in manifest["tracks"]:
            index = item["index"]
            track = dict(by_track[item["track_id"]])
            track["candidate_position_km"] = banks[f"position_km_{index}"]
            track["candidate_velocity_km_s"] = banks[f"velocity_km_s_{index}"]
            expected_shape = (
                item["candidate_count"],
                len(timing_grid),
                item["observation_count"],
                3,
            )
            if (
                track["candidate_position_km"].shape != expected_shape
                or track["candidate_velocity_km_s"].shape != expected_shape
                or not np.isfinite(track["candidate_position_km"]).all()
                or not np.isfinite(track["candidate_velocity_km_s"]).all()
            ):
                raise ValueError("candidate bank shape or values invalid")
            track["catalogue_size"] = manifest["catalogue_size"]
            track["y"] = np.asarray(track["measured_hz"], dtype=float)
            track["mask"] = np.asarray(track["training_mask"], dtype=bool)
            combined.append(track)
        doc["tracks"] = combined
        documents.append(doc)
    return documents


def estimate(request: dict) -> dict:
    base = {"schema": "ds7-response/v1", "unit_id": request["unit"]["unit_id"]}
    documents = load_documents(request)
    if any(not d.get("tracks") for d in documents):
        return {**base, "status": "abstained", "reason": "no qualified frozen tracks"}
    objective = JointObjective(documents, request["config"])
    bounds = [tuple(request["config"]["position_bounds_km"])] * 2 + [
        tuple(request["config"]["timing_bounds_s"])
    ] * len(documents)
    starts = request["config"]["timing_starts_s"]
    runs = []
    for tau in starts:
        fit = minimize(
            objective.value_gradient,
            np.r_[0.0, 0.0, [tau] * len(documents)],
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            options={
                "maxiter": 100,
                "maxfun": 180,
                "ftol": 1e-10,
                "gtol": 1e-5,
                "eps": 1e-4,
                "maxls": 30,
            },
        )
        runs.append(fit)
    fit = min(runs, key=lambda r: r.fun)
    lat, lon = objective.coordinates(fit.x)
    boundary = any(
        abs(v - a) < 1e-3 or abs(v - b) < 1e-3 for v, (a, b) in zip(fit.x, bounds, strict=True)
    )
    return {
        **base,
        "status": "ok",
        "estimate": {"latitude_deg": lat, "longitude_deg": lon},
        "converged": bool(fit.success),
        "boundary_hit": bool(boundary),
        "diagnostics": {
            "solver": "corrected_ds6_stationary_joint",
            "train_log_likelihood": -float(fit.fun),
            "recordings": len(documents),
            "tracks": sum(len(d["tracks"]) for d in documents),
            "nfev": int(fit.nfev),
            "total_nfev": sum(int(run.nfev) for run in runs),
            "starts": [
                {
                    "timing_start_s": starts[index],
                    "nfev": int(run.nfev),
                    "success": bool(run.success),
                    "objective": -float(run.fun),
                    "boundary_hit": any(
                        abs(value - low) < 1e-3 or abs(value - high) < 1e-3
                        for value, (low, high) in zip(run.x, bounds, strict=True)
                    ),
                }
                for index, run in enumerate(runs)
            ],
            "east_north_km": fit.x[:2].tolist(),
            "timing_offsets_s": fit.x[2:].tolist(),
            "runtime": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "scipy": scipy.__version__,
            },
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    result = estimate(json.loads(args.request.read_text()))
    with args.response.open("x") as stream:
        json.dump(result, stream, allow_nan=False)


if __name__ == "__main__":
    main()
