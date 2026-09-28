"""Two phenomenological receiver slopes shared across a pooled position fit."""

from __future__ import annotations

import ds7_fast_baseline_adapter as baseline
import numpy as np
from ds7_shared_slope_shadow import SharedSlope, prepare
from ds7_slope_identifiability import evaluate


class PooledReceiverSlope:
    def __init__(self, documents, config, model_factory=baseline.Stationary):
        if not documents or any(not d["tracks"] for d in documents):
            raise ValueError("nonempty documents and tracks required")
        receivers = {t["receiver_id"] for d in documents for t in d["tracks"]}
        if receivers != {0, 1}:
            raise ValueError("both software receiver IDs 0 and 1 required")
        self.documents, self.config = documents, config
        self.models = [model_factory(d, config) for d in documents]
        self.base_dimension = 2 + len(documents)
        self.dimension = self.base_dimension + 2
        self.groups = [
            [[t for t in d["tracks"] if t["receiver_id"] == rx] for rx in (0, 1)] for d in documents
        ]

    def coordinates(self, point):
        return self.models[0].coordinates(point[:3])

    def evaluate(self, point):
        point = np.asarray(point, dtype=float)
        if point.shape != (self.dimension,) or not np.isfinite(point).all():
            raise ValueError("finite pooled position/timing/two-slope vector required")
        score, gradient, visibility = 0.0, np.zeros_like(point), []
        for i, (model, groups) in enumerate(zip(self.models, self.groups, strict=True)):
            for rx, tracks in enumerate(groups):
                indices = [0, 1, i + 2, self.base_dimension + rx]
                result = evaluate(tracks, model.prediction, point[indices])
                score += result["score"]
                gradient[indices] += result["gradient"]
                visibility.append(result["visibility"])
        return {"score": score, "gradient": gradient, "visibility": visibility}

    def held(self, point):
        point = np.asarray(point, dtype=float)
        rows = []
        for i, document in enumerate(self.documents):
            local = np.array([point[0], point[1], point[i + 2]])
            shadow = prepare(document, self.config, local)
            groups = []
            for rx in (0, 1):
                tracks = [t for t in shadow.tracks if t["receiver_id"] == rx]
                result = SharedSlope(tracks).evaluate(point[self.base_dimension + rx], held=True)
                groups.append({"receiver_id": rx, **result})
            rows.append(
                {
                    "session_id": document["session_id"],
                    "receivers": groups,
                    "held_observations": sum(int((~t["mask"]).sum()) for t in document["tracks"]),
                    "tracks": len(document["tracks"]),
                    "training_log_score": sum(g["training_log_score"] for g in groups),
                    "held_log_score": sum(g["held_log_score"] for g in groups),
                }
            )
        return rows
