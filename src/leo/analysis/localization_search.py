"""Within-scan reuse of deterministic point likelihoods, without quantization."""
from collections.abc import Callable

import numpy as np


class MemoizedPointScorer:
    """Cache exact float64 point keys for one fixed observation/model context.

    The callback must score each point independently of batch composition.
    Never reuse an instance across scans or changes to the likelihood model.
    Returned arrays are copies, so caller mutation cannot change stored scores.
    """

    def __init__(self, score: Callable[[np.ndarray], np.ndarray]):
        self.score = score
        self._cache: dict[bytes, float] = {}
        self.requested_points = 0
        self.evaluated_points = 0

    def __call__(self, points: np.ndarray) -> np.ndarray:
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2 or not np.all(np.isfinite(points)):
            raise ValueError("points must be finite east/north pairs")
        keys = [row.tobytes() for row in points]
        missing = {}
        for key, row in zip(keys, points, strict=True):
            if key not in self._cache and key not in missing:
                missing[key] = row.copy()
        if missing:
            values = np.asarray(self.score(np.stack(list(missing.values()))), dtype=float)
            if (values.shape != (len(missing),) or np.any(np.isnan(values))
                    or np.any(np.isposinf(values))):
                raise ValueError("scorer must return a finite or negative-infinite score per point")
            self._cache.update(zip(missing, map(float, values), strict=True))
            self.evaluated_points += len(missing)
        self.requested_points += len(points)
        return np.array([self._cache[key] for key in keys])
