import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools/research"))
from parallel_coverage import evaluate_top_k_parallel
from search_multiresolution_tle_coverage import CellScore, ThresholdCoverage, rank_coverage_cells

sys.path.pop(0)

from leo.analysis.research.regional_doppler import Region


class FakeEvaluator:
    def __init__(self):
        self.count = 0

    def metrics(self):
        return {"cache_hits": 0, "fully_scored_cell_count": self.count,
                "early_abandoned_cell_count": 0, "evaluation_elapsed_s": 0.0}

    def evaluate_top_k(self, sites, *, top_k, threshold_hz):
        self.count += len(sites)
        rows = [CellScore(float(e), float(n), (
            ThresholdCoverage(threshold_hz, int(abs(e)) % 4, 1., 1,
                              float(abs(n)), 1.),
        )) for e, n in zip(sites.east_km, sites.north_km, strict=True)]
        return rank_coverage_cells(rows, threshold_hz, top_k), []


@pytest.mark.parametrize("workers,top_k", [(1, 5), (3, 5), (4, 1), (3, 100)])
def test_fork_shard_merge_matches_global_ranking_and_preserves_parent(workers, top_k):
    sites = Region(38., -121., 100., 100.).points(
        np.arange(-16., 16.), np.arange(32.) % 3
    )
    expected, _ = FakeEvaluator().evaluate_top_k(sites, top_k=top_k, threshold_hz=200.)
    parent = FakeEvaluator()
    actual, bounds, metrics = evaluate_top_k_parallel(
        parent, sites, top_k=top_k, threshold_hz=200., workers=workers
    )
    assert actual == expected
    assert bounds == []
    assert parent.count == 0
    assert sum(row["requested_points"] for row in metrics["shards"]) == len(sites)
    assert sum(row["fully_scored_cell_count"] for row in metrics["shards"]) == len(sites)


def test_invalid_parallel_worker_count_rejected():
    with pytest.raises(ValueError, match="positive"):
        evaluate_top_k_parallel(None, None, top_k=1, threshold_hz=200., workers=0)
