import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[2] / "tools/research"))
from search_multiresolution_tle_coverage import CoverageEvaluator

sys.path.pop(0)

from leo.analysis.research.regional_doppler import Region


def test_residual_port_preserves_uncapped_results_and_returns_copy():
    sites = Region(38.0, -121.0, 1000.0, 1000.0).points(np.asarray([25.0]), np.asarray([-25.0]))
    key = (float(sites.latitude_deg[0]), float(sites.longitude_deg[0]), 0.0)
    instance = CoverageEvaluator.__new__(CoverageEvaluator)
    instance.evaluate_points = lambda _: []
    instance._details = {
        key: [
            {
                "tracklet_id": "track",
                "partition_seed": "frozen",
                "training_count": 4,
                "heldout_count": 2,
                "best_candidate": {"norad": 123, "heldout_rms_hz": 900.0},
            }
        ]
    }
    row = instance.evaluate_residual_points(sites)[0]
    assert row["east_km"] == 25.0
    assert row["tracks"][0]["heldout_rms_hz"] == 900.0
    row["tracks"][0]["best_candidate"]["norad"] = 456
    assert instance._details[key][0]["best_candidate"]["norad"] == 123


def test_residual_port_recomputes_missing_coverage_only_details():
    sites = Region(38.0, -121.0, 1000.0, 1000.0).points(np.asarray([0.0]), np.asarray([0.0]))
    instance = CoverageEvaluator.__new__(CoverageEvaluator)
    instance.evaluate_points = lambda _: []
    instance._details = {}
    calls = []

    def finalists(_):
        calls.append(True)
        return [
            {
                "tracks": [
                    {
                        "tracklet_id": "missing",
                        "partition_seed": "frozen",
                        "training_count": 4,
                        "heldout_count": 2,
                        "best_candidate": None,
                    }
                ]
            }
        ]

    instance.evaluate_finalists = finalists
    assert instance.evaluate_residual_points(sites)[0]["tracks"][0]["heldout_rms_hz"] is None
    instance.evaluate_residual_points(sites)
    assert calls == [True]
