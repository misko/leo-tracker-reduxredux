"""Training-only shared frequency-slope shadow at a frozen DS7 position."""

from __future__ import annotations

import math

import ds7_fast_baseline_adapter as baseline
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp


class SharedSlope:
    def __init__(self, tracks):
        self.tracks = tracks

    def evaluate(self, slope, held=False):
        total, derivative, held_total = 0.0, 0.0, 0.0
        receipts = []
        for track in self.tracks:
            mask = track["mask"]
            residual = track["y"][None, :] - track["prediction"] - slope * track["column"][None, :]
            scores, _, audits, offsets = baseline.profile(residual, mask)
            if not all(audit["converged"] for audit in audits):
                raise RuntimeError("offset profile failed stationarity")
            scores = np.where(track["visible"], scores, -np.inf)
            normal = float(logsumexp(scores))
            if not math.isfinite(normal):
                raise ValueError("no visible nominee")
            weights = np.exp(scores - normal)
            centered = residual[:, mask] - offsets[:, None]
            influence = 5 * centered / (40000 + centered**2)
            derivative += float(weights @ np.sum(influence * track["column"][None, mask], axis=1))
            total += normal - math.log(track["catalogue_size"])
            if held:
                centered_held = residual[:, ~mask] - offsets[:, None]
                z = centered_held / 100
                densities = (
                    baseline.baseline.gammaln(2.5)
                    - baseline.baseline.gammaln(2)
                    - 0.5 * math.log(4 * math.pi)
                    - math.log(100)
                    - 2.5 * np.log1p(z**2 / 4)
                )
                held_score = float(logsumexp(scores + densities.sum(axis=1)) - normal)
                held_total += held_score
                receipts.append(
                    {
                        "track_id": track["track_id"],
                        "held_log_score": held_score,
                        "weights": weights.tolist(),
                        "offsets": offsets.tolist(),
                        "map": int(np.argmax(weights)),
                        "effective_candidates": float(1 / (weights @ weights)),
                    }
                )
        return {
            "training_log_score": total,
            "gradient": derivative,
            "held_log_score": held_total if held else None,
            "tracks": receipts,
        }


def prepare(document, config, x):
    model = baseline.Stationary(document, config)
    tracks = []
    for track in document["tracks"]:
        prediction, visible = model.prediction(track, x)
        column = 11_200_000_000 / float(track["rf_hz"]) * np.asarray(track["times_s"])
        tracks.append({**track, "prediction": prediction, "visible": visible, "column": column})
    return SharedSlope(tracks)


def fit(shadow, bound):
    candidates = []
    for start in (0.0, -2.0, 2.0):

        def objective(x):
            value = shadow.evaluate(float(x[0]))
            return -value["training_log_score"], np.array([-value["gradient"]])

        result = minimize(
            objective,
            np.array([start]),
            method="L-BFGS-B",
            jac=True,
            bounds=[(-bound, bound)] if bound is not None else [(None, None)],
            options={"maxiter": 100, "maxfun": 300, "ftol": 1e-12, "gtol": 1e-6},
        )
        candidates.append(
            {
                "start": start,
                "slope_native_hz_s": float(result.x[0]),
                "success": bool(result.success),
                "message": str(result.message),
                "training_log_score": -float(result.fun),
                "iterations": int(result.nit),
                "evaluations": int(result.nfev),
                "gradient": -float(result.jac[0]),
            }
        )
    converged = [c for c in candidates if c["success"]]
    if not converged:
        raise RuntimeError("no slope start converged")
    selected = max(converged, key=lambda c: c["training_log_score"])
    return {"bound_native_hz_s": bound, "candidates": candidates, "selected": selected}
