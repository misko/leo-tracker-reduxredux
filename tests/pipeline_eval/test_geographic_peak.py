from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def peak(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import geographic_peak

    return geographic_peak


def square():
    return np.array([(x, y) for x in range(-2, 3) for y in range(-2, 3)], dtype=float)


def test_local_quadratic_recovers_strict_rotated_maximum_and_tie_order(peak):
    points = square()
    target = np.array([.15, -.25])
    x, y = (points - target).T
    scores = 4 - 3 * x*x + .6 * x*y - y*y
    result = peak.local_peak(points, scores, 4.)
    assert result["status"] == "interpolated"
    assert result["discrete"]["xy_km"] == [0., 0.]
    np.testing.assert_allclose(result["interpolated"]["xy_km"], target, rtol=0., atol=1e-13)
    distance = np.sum(points**2, axis=1)
    expected = sorted(range(len(points)), key=lambda i: (distance[i], i))[:12]
    assert result["diagnostics"]["neighbor_indices"] == expected


@pytest.mark.parametrize("case,reason", [("saddle", "nonconcave_quadratic"),
                                       ("outside", "stationary_outside_local_hull"),
                                       ("tie", "tied_sample_maximum"),
                                       ("collinear", "invalid_quadratic_design")])
def test_invalid_local_models_keep_the_original_discrete_maximum(peak, case, reason):
    points = square() if case != "collinear" else np.column_stack((np.arange(12.), np.zeros(12)))
    x, y = points.T
    if case == "saddle":
        scores = -x*x + .4*y*y + .13*y
    elif case == "outside":
        scores = -(x-3.2)**2 - (y-.25)**2
    elif case == "tie":
        scores = -(x-.5)**2 - y*y
    else:
        scores = -(x-5)**2
    result = peak.local_peak(points, scores, 4.)
    assert result["status"] == reason and result["interpolated"] is None
    assert result["discrete"]["index"] == np.argmax(scores)


def test_ordered_geographic_lattice_rejects_mutated_coordinates(peak):
    from leo.analysis.localization_v3.region import SearchRegion
    from tools.pipeline_eval.variants.experimental import regional_reassignment as kernel

    offer = dict(center=[1., 20.], width_km=25.)
    original = list(kernel.probes(SearchRegion(tuple(offer["center"]), width_km=25.)))
    archived = dict(offer=offer, points=json.loads(json.dumps(original)), complete_score_match=True)
    assert len(peak.bind_lattice(offer, archived, kernel)[1]) == 96
    later = deepcopy(archived)
    later["points"][1]["latlon"][0] += .001
    with pytest.raises(ValueError, match="ordered 96-point lattice"):
        peak.bind_lattice(offer, later, kernel)


def test_scoring_treats_the_original_closed_face_as_contained(peak):
    from geographic_peak_score import summarize_position

    point = dict(latlon=[1., 20.], xy_km=[12.5, 2.])
    edge = summarize_position(point, 25., [1., 20.])
    assert edge["contained"] and edge["clearance_km"] == edge["horizontal_error_km"] == 0.
    beyond = dict(point, xy_km=[np.nextafter(12.5, np.inf), 2.])
    assert not summarize_position(beyond, 25., [1., 20.])["contained"]
    assert summarize_position(None, 25., [1., 20.]) is None
