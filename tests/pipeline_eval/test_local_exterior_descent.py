from math import nextafter

import pytest

from leo.analysis.localization_v3.region import SearchRegion
from tools.pipeline_eval.variants.experimental.local_exterior_descent import evaluate, shared_face
from tools.pipeline_eval.variants.experimental.regional_reassignment import probes

WIDTH = 32.0
ENDPOINTS = {"c0": (16.0, 0.3), "fitted_c": (16.0, -0.2)}
AXIS_SCORES = {(12, 0): (1, 2), (15.875, 0): (2, 3),
               (16.125, 0): (3, 4), (20, 0): (4, 5)}


def run(values, endpoints=ENDPOINTS, *, layout=None, default=(0, 0)):
    if layout is None:
        layout = tuple(probes(SearchRegion((12.0, -30.0), WIDTH)))
    received = []

    def score(point):
        xy = tuple(point["xy_km"])
        received.append(xy)
        return dict(zip(("1", "2"), values.get(xy, default), strict=True))

    result = evaluate(endpoints, WIDTH, layout, score)
    assert result["probes_evaluated"] == len(received) == len(set(received))
    return result, received


def test_sustained_exterior_gain_beats_every_sampled_interior():
    result, received = run(AXIS_SCORES)
    assert result["would_withhold"] is True
    assert result["witness"]["xy_km"] == (20., 0.)
    assert result["witness"]["gain"] == {"1": 2, "2": 2}
    assert len(received) == 52
    assert max(abs(x) for xy in received for x in xy) == 20


@pytest.mark.parametrize("position", [(4, 0), (-8, 0), (0, -12)])
def test_interior_tie_on_either_receiver_blocks_veto(position):
    result, received = run(AXIS_SCORES | {position: (1, 5)})
    assert result["stop"] == "viable_interior"
    assert result["witness"]["xy_km"] == list(position)
    assert len(received) < 52


def test_positive_near_gain_without_sustained_rise_abstains():
    result, received = run(AXIS_SCORES | {(20, 0): (3.5, 3.5)})
    assert result["stop"] == "no_outward_rise"
    assert len(received) == 8


def test_bilateral_comparison_and_strict_tie_abstain():
    result, received = run(AXIS_SCORES | {(16.125, 0): (4, 3)})
    assert result["stop"] == "no_outward_rise"
    assert len(received) == 6


@pytest.mark.parametrize("fitted", [(15.9, 1), (-16, 0), (16, 16), (0, 16), (16.001, 0)])
def test_only_one_shared_clipped_face_starts_work(fitted):
    result, received = run(AXIS_SCORES, ENDPOINTS | {"fitted_c": fitted})
    assert result["stop"] == "no_shared_face"
    assert received == []


def test_native_one_ulp_inward_face_is_active():
    assert shared_face(ENDPOINTS | {"fitted_c": (nextafter(16., 0.), 1)}, WIDTH) == (0, 1)


def test_incomplete_layout_fails_without_calling_score():
    result, received = run(AXIS_SCORES, layout=())
    assert result["stop"] == "invalid_layout"
    assert received == []


def test_invalid_receiver_score_abstains():
    points = tuple(probes(SearchRegion((12.0, -30.0), WIDTH)))
    result = evaluate(ENDPOINTS, WIDTH, points, lambda point: {"1": float("nan"), "2": 1.})
    assert result["stop"] == "unavailable_score"
    assert result["would_withhold"] is False
