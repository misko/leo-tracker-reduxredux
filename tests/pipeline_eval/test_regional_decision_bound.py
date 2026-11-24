from math import exp, log, log1p

import pytest

from reports.ALGO08.v3.regional_decision_bound import below, disprove, mixture_cap
from reports.ALGO08.v3.regional_lazy_geometry import cell_bound


@pytest.mark.parametrize("peak, visible,total", [(0., 1, 1), (35., 50, 1000), (3000., 100, 11177), (-50., 100, 1000)])
def test_cap_preserves_whole_catalogue_prior(peak, visible, total):
    odds = peak + log(visible/total)
    exact = max(0., odds) + log1p(exp(-abs(odds)))
    assert mixture_cap(peak, visible, total) >= exact
    assert mixture_cap(peak, 0, total) == 0.


def test_equal_or_invalid_receiver_evidence_cannot_certify():
    assert below([1., 2.], [3.], 1, 7.)
    assert not below([1., 2.], [3.], 1, 6.)
    assert not below([float("nan")], [], 1, 7.)
    assert not below([1.], [-1.], 1, 7.)


def test_witness_tests_only_far_exteriors_and_falls_back_when_unresolved():
    points = [dict(xy_km=(0., i/10), side="inside") for i in range(48)]
    points += [dict(xy_km=(20., i/10), side="exterior") for i in range(24)]
    points += [dict(xy_km=(40., i/10), side="exterior") for i in range(24)]
    seen = []

    def proves(point, score):
        seen.append(point["xy_km"])
        return point["xy_km"][0] == 40. and score == 2.

    assert disprove(points, 25., lambda _: 2., proves)["would_withhold"] is False
    assert len(seen) == 24
    assert disprove(points, 25., lambda _: 2., lambda *_: False) is None
    assert disprove(points[:-1], 25., lambda _: 2., proves) is None


def test_lazy_ceiling_keeps_all_cap_endpoints_even_for_unscored_tracks():
    receiver = [[1, 2, 3, 4], [4, 5, 6]]
    result = cell_bound([*receiver, [1, 9]], receiver, [0, 1, 2], 10)
    assert result["exterior_unique_times"] == [3, 5, 6]
    assert result["all_cells"] == 280
    assert result["receiver_only_cells"] == 240
    assert result["lazy_cells"] == 200
    assert result["prefix_only_avoided_cells"] == 40
