"""Fixed per-track constant-frequency null alongside the frozen satellite mixture."""

from __future__ import annotations

import numpy as np


class NullMixtureJoint:
    def __init__(self, documents, config, baseline):
        self.baseline = baseline
        self.mass = float(config["null_prior_mass"])
        if not 0 < self.mass < 1:
            raise ValueError("null prior must be strictly inside (0,1)")
        self.records = []
        for document in documents:
            tracks = []
            for track in document["tracks"]:
                score, _, audits, _ = baseline.profile(track["y"][None, :], track["mask"])
                if not all(a["converged"] for a in audits):
                    raise ValueError("null offset stationarity failed")
                model = baseline.Stationary({"tracks": [track]}, config)
                tracks.append((model, float(score[0])))
            self.records.append(tracks)

    def coordinates(self, x):
        return self.records[0][0][0].coordinates(x)

    def value_gradient(self, x):
        total, gradient = 0.0, np.zeros_like(x)
        for number, tracks in enumerate(self.records):
            local = np.array([x[0], x[1], x[number + 2]])
            for model, null_score in tracks:
                satellite_score, derivative = model.evaluate(local, True)
                satellite_term = np.log1p(-self.mass) + satellite_score
                null_term = np.log(self.mass) + null_score
                mixture = np.logaddexp(satellite_term, null_term)
                probability = np.exp(satellite_term - mixture)
                total += mixture
                gradient[:2] += probability * derivative[:2]
                gradient[number + 2] += probability * derivative[2]
        return -float(total), -gradient

    def null_responsibilities(self, x):
        values = []
        for number, tracks in enumerate(self.records):
            local = np.array([x[0], x[1], x[number + 2]])
            for model, null_score in tracks:
                satellite_score, _ = model.evaluate(local)
                null_term = np.log(self.mass) + null_score
                mixture = np.logaddexp(np.log1p(-self.mass) + satellite_score, null_term)
                values.append(float(np.exp(null_term - mixture)))
        return values
