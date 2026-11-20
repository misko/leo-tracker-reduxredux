import numpy as np
import pytest

from tools.pipeline_eval.qualification import (
    edge_interval_results,
    edge_interval_trial,
    screening_figures,
)
from tools.pipeline_eval.scoring import ARMS
from tools.pipeline_eval.variants import edge_interval


def test_subscans_keep_matching_rx_times_and_partition_whole_time_blocks():
    t = np.repeat(np.arange(240.0), 2)
    groups = edge_interval.time_groups(t)
    assert np.array_equal(groups[::2], groups[1::2])
    assert np.array_equal(groups[::24], np.arange(20) % 4)
    assert np.array_equal(np.bincount(groups), [120] * 4)


@pytest.mark.parametrize(
    ("points", "state"),
    [
        ([0.6, 0.7, 0.5, 0.6], "inside"),
        ([-0.6, -0.7, -0.5, -0.6], "outside"),
        ([-0.7, 1.2, -0.4, 0.6], "weak"),
        ([0.01, 0.01, 0.01, 0.01], "weak"),
        ([0.5, 0.6, 0.7], "insufficient"),
    ],
)
def test_signed_interval_requires_four_estimates_and_strict_face_exclusion(points, state):
    assert edge_interval.interval(points)["state"] == state


def test_chart_reference_uses_same_signed_face_even_for_forced_endpoints():
    tile = dict(center=[40.0, -90.0], width_km=25.0)
    sides = {a: dict(latlon=None, forced_latlon=[40.0 + 12.5 / 111, -90.0]) for a in ARMS}
    truth = [40.0 + 11.9 / 111, -90.0]
    assert edge_interval_results.face_truth(dict(arms=sides), tile, truth) == pytest.approx(0.6)


def test_subscan_transfer_artifacts_cover_both_arms_and_separate_measured_input():
    studies = {
        chart.id: chart for chart in screening_figures.charts(evidence=edge_interval_trial.REPORT)
    }
    for scope, count in (("synthetic", 8), ("measured", 1), ("independent", 1)):
        chart = studies[f"compact-subscan-interval-{scope}"]
        assert len(chart.cases) == count
        for arm in ARMS:
            for key in ("candidate", "stock"):
                assert len([r for r in chart.page(arm).rows if r.series == key]) == count
