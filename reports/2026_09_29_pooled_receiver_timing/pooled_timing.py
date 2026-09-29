"""Linear shared-receiver timing constraint over the existing track model."""

import numpy as np


class PooledTiming:
    def __init__(self, model, recordings):
        self.model = model
        self.recordings = recordings

    def expand(self, x):
        x = np.asarray(x, dtype=float)
        if x.shape != (self.recordings + 3,):
            raise ValueError("Expected E/N, one center per recording, one receiver difference")
        return np.r_[x[:2], x[2:-1] - x[-1] / 2, x[2:-1] + x[-1] / 2]

    def coordinates(self, x):
        return self.model.coordinates(self.expand(x))

    def evaluate(self, x, gradient=True, held=False):
        result = self.model.evaluate(self.expand(x), gradient=gradient, held=held)
        g = result["gradient"]
        n = self.recordings
        zero, one = g[2 : 2 + n], g[2 + n :]
        return {**result, "gradient": np.r_[g[:2], zero + one, (one - zero).sum() / 2]}

    def value_gradient(self, x):
        result = self.evaluate(x)
        return -result["score"], -result["gradient"]
