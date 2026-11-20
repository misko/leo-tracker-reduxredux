from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import outside_predictive_trial as study
from tools.pipeline_eval.qualification import screening_figures
from tools.pipeline_eval.variants import outside_predictive as method


def test_holdout_uses_entire_reciprocal_time_blocks():
    lane = (11e9, 1, 3)
    points = [(t, t + 100) for t in (0.2, 5.99, 6, 11.99, 12, 19)]
    train, held = method.partition({lane: points}, 0)
    reverse_train, reverse_held = method.partition({lane: points}, 1)
    assert train == reverse_held
    assert held == reverse_train
    assert [t for t, _ in train[lane]] == [0.2, 5.99, 12]
    assert [t for t, _ in held[lane]] == [6, 11.99, 19]


def test_equal_node_budgets_and_disjoint_square_regions():
    for half in (12.5, 25):
        xy = method.nodes(half)
        assert xy.shape == (96, 2)
        assert len(np.unique(xy, axis=0)) == 96
        extent = np.max(np.abs(xy), axis=1)
        assert np.all(extent[:48] < half)
        assert np.all(extent[48:] > half)
        assert xy.mean(axis=0) == pytest.approx([0, 0], abs=1e-10)


def test_training_only_nomination_rejects_overlapping_time_and_lane():
    def assigned(start, stop):
        return SimpleNamespace(
            arc=SimpleNamespace(
                track=SimpleNamespace(
                    rf=11e9,
                    lane=0,
                    t=np.array([start, stop]),
                )
            )
        )

    candidates = [assigned(0, 10), assigned(8, 20)]
    peaks = {(11e9, 1, 3): [(2, 100), (9, 101), (17, -70), (25, 105)]}
    matched, collisions = method.unique_held(candidates, peaks)
    assert matched == {0: [(2, 100)], 1: [(17, -70)]}
    assert collisions == 1
    swapped = {(11e9, 1, 3): [(t, -y) for t, y in peaks[11e9, 1, 3]]}
    changed, same_collisions = method.unique_held(candidates, swapped)
    assert same_collisions == collisions
    assert {k: [t for t, _ in points] for k, points in changed.items()} == {0: [2], 1: [17]}


def test_reciprocal_vote_requires_agreement_of_both_arms_and_both_folds():
    def fold(a, b):
        return {"c0": {"exterior_gain": a}, "fitted_c": {"exterior_gain": b}}

    assert method.verdict([fold(4, 4), fold(4, 4)]) == "outside"
    assert method.verdict([fold(-4, -4), fold(-4, -4)]) == "inside"
    assert method.verdict([fold(-4, -4), fold(4, 4)]) == "ambiguous"
    assert method.verdict([fold(4, 4), fold(4, -4)]) == "ambiguous"
    assert method.verdict([fold(4, 4), {}]) == "insufficient"


def test_wrapped_predictive_score_has_the_fixed_uniform_tail():
    score = method.wrap_score(np.array([0, method.SIGMA_HZ, 1e6]))
    assert score[0] > score[1] > score[2]
    assert score[2] == pytest.approx(np.log(method.CONTAMINATION))
    assert method.SIGMA_HZ == 250


def test_chart_scopes_separate_simulated_sites_from_measured_roof_errors():
    plots = screening_figures.charts(evidence=study.REPORT)
    assert {p.id: len(p.cases) for p in plots} == {
        f"{study.METHOD}-fresh-synthetic": 8,
        f"{study.METHOD}-archived-roof": 8,
    }
