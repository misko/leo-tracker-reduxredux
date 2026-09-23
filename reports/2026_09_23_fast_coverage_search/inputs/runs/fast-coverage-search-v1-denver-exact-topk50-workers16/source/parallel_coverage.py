"""Bounded Linux fork workers for exact fixed-grid coverage searches.

Each disjoint shard retains K cells. Their union necessarily contains the
global top K under the same total ordering. Satellite state arrays are shared
copy-on-write; mutable evaluator caches belong to each worker.
"""

from __future__ import annotations

import multiprocessing
import time

import numpy as np
from search_multiresolution_tle_coverage import rank_coverage_cells

from leo.analysis.research.regional_doppler import Grid

_EVALUATOR = None


def _initialize(evaluator):
    global _EVALUATOR
    _EVALUATOR = evaluator


def _evaluate(payload):
    shard_id, sites, top_k, threshold_hz = payload
    before = _EVALUATOR.metrics()
    scores, bounds = _EVALUATOR.evaluate_top_k(
        sites, top_k=top_k, threshold_hz=threshold_hz
    )
    after = _EVALUATOR.metrics()
    return scores, [dict(row, shard_id=shard_id) for row in bounds], {
        "shard_id": shard_id,
        "requested_points": len(sites),
        "cache_hits": after["cache_hits"] - before["cache_hits"],
        "fully_scored_cell_count": (
            after["fully_scored_cell_count"] - before["fully_scored_cell_count"]
        ),
        "early_abandoned_cell_count": (
            after["early_abandoned_cell_count"] - before["early_abandoned_cell_count"]
        ),
        "evaluation_elapsed_s": (
            after["evaluation_elapsed_s"] - before["evaluation_elapsed_s"]
        ),
    }


def evaluate_top_k_parallel(evaluator, sites, *, top_k, threshold_hz, workers):
    """Return exact global leaders, shard pruning receipts, and worker metrics.

    Parent caches are not populated by workers. Recompute finalists in the
    parent when full per-track diagnostics are needed. Bounds are local to the
    stated shard; they certify local top K and thus the merged global top K.
    """
    if workers < 1 or top_k < 1:
        raise ValueError("positive worker and top-K counts required")
    if not len(sites):
        return [], [], {"workers": 0, "wall_s": 0.0, "shards": []}
    worker_count = min(workers, len(sites))
    fields = ("east_km", "north_km", "latitude_deg", "longitude_deg",
              "altitude_m", "ecef_km", "up")
    # Interleaving distributes expensive geographical regions among workers.
    partitions = [np.arange(i, len(sites), worker_count) for i in range(worker_count)]
    payloads = [
        (i, Grid(*(getattr(sites, field)[indices] for field in fields)), top_k, threshold_hz)
        for i, indices in enumerate(partitions)
    ]
    started = time.monotonic()
    context = multiprocessing.get_context("fork")
    with context.Pool(worker_count, initializer=_initialize, initargs=(evaluator,)) as pool:
        results = pool.map(_evaluate, payloads, chunksize=1)
    scores = rank_coverage_cells(
        [score for shard, _, _ in results for score in shard], threshold_hz, top_k
    )
    return scores, [row for _, rows, _ in results for row in rows], {
        "workers": worker_count,
        "wall_s": time.monotonic() - started,
        "shards": [metrics for _, _, metrics in results],
        "parent_cache_populated": False,
        "exactness": "disjoint shard top-K union, identical total ordering",
    }
