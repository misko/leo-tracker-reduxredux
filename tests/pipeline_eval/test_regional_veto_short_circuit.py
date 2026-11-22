from random import Random
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.region import SearchRegion
from tests.pipeline_eval.test_regional_exterior_veto import WIDTH, fixture, scores_at
from tools.pipeline_eval.variants.experimental import regional_reassignment
from tools.pipeline_eval.variants.experimental.regional_exterior_veto import evaluate
from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal


def replay(points):
    visited = []

    def score(point):
        visited.append(point)
        return point["receiver_scores"]

    result = evaluate_terminal(points, WIDTH, score)
    assert result["probes_evaluated"] == len(visited)
    assert result["would_withhold"] == evaluate(points, WIDTH)["would_withhold"]
    if result["complete"]:
        assert len(visited) == 96
        assert {k: v for k, v in result.items() if k != "probes_evaluated"} == evaluate(points, WIDTH)
    return result, visited


def test_positive_case_keeps_full_original_diagnostics():
    assert replay(fixture())[0]["complete"]


@pytest.mark.parametrize("score", [2., 3.])
@pytest.mark.parametrize("side", ["inside", "exterior"])
def test_tied_or_higher_inspected_point_disproves_possible_veto(side, score):
    points = fixture()
    target = points[0] if side == "inside" else points[48]
    target["receiver_scores"]["1"] = score
    result, visited = replay(points)
    assert result["stop"] == ("inside_score" if side == "inside" else "ineligible_exterior_score")
    assert not result["complete"] and visited[-1] is target
    assert all(p["side"] == "exterior" and max(map(abs, p["xy_km"])) - WIDTH / 2 >= WIDTH
               for p in visited[:24])
    assert len(visited) == (25 if side == "inside" else 73)


def test_tied_or_separated_eligible_winners_disprove_veto():
    points = fixture()
    scores_at(points, (30., 4.))["1"] = 2.
    tie, _ = replay(points)
    separation, _ = replay(fixture(second=(-30., 0.)))
    assert tie["stop"] == "eligible_exterior_tie"
    assert separation["stop"] == "eligible_exterior_separation"
    assert tie["probes_evaluated"] == separation["probes_evaluated"] == 24


@pytest.mark.parametrize("kind", ["missing", "duplicate", "wrong_side"])
def test_malformed_layout_checks_all_geometry_before_scoring(kind):
    points = fixture()
    if kind == "missing":
        points.pop()
    elif kind == "duplicate":
        points[48] = points[49]
    else:
        points[48]["side"] = "inside"
    assert replay(points)[0] == dict(would_withhold=False, complete=False, probes_evaluated=0,
                                     stop="invalid_layout")


@pytest.mark.parametrize("malformed", [{"1": float("nan"), "2": 1.}, {"2": 1.}, [(1, 1.), (2, 2.)]])
def test_inspected_bad_score_remains_incomplete_and_cannot_veto(malformed):
    points = fixture()
    points[48]["receiver_scores"] = malformed
    result, _ = replay(points)
    assert not result["complete"] and result["stop"] == "invalid_score"


def test_uninspected_bad_score_cannot_turn_a_partial_disproof_into_a_veto():
    points = fixture()
    points[0]["receiver_scores"]["1"] = 3.
    points[48]["receiver_scores"]["1"] = float("inf")
    result, _ = replay(points)
    assert result == dict(would_withhold=False, complete=False, probes_evaluated=25, stop="inside_score")


def test_randomized_scores_including_ties_and_permuted_probe_orders():
    rng = Random(85)
    for _ in range(100):
        points = fixture()
        rng.shuffle(points)
        for point in points:
            point["receiver_scores"] = {r: rng.randrange(32) for r in ("1", "2")}
        replay(points)


def test_opt_in_uses_all_locations_for_geometry_then_scores_only_needed_points(monkeypatch):
    region = SearchRegion((46., 12.), WIDTH)
    prepared = dict(
        observations=[dict(observation_id=i, receiver=1 + (i >= 2)) for i in range(4)],
        tracks=[dict(key="track", receiver=1, observation_ids=[0, 1], times=np.array([1., 2.]),
                     values=np.array([0., 1.]), rf_hz=11.5e9)],
        metadata=dict(anchor_utc_ns=0),
    )
    expected = list(regional_reassignment.probes(region))
    locations = []

    def geometry(_catalogue, _origin, _times, _starts, _center, all_locations):
        assert all_locations == [row["latlon"] for row in expected]
        return object(), np.array([100])

    def projection(_geometry, *location):
        locations.append(location)
        shape = (1, 2)
        return np.zeros(shape), np.ones(shape), np.zeros(shape)

    monkeypatch.setattr(regional_reassignment, "orbit_geometry", geometry)
    monkeypatch.setattr(regional_reassignment, "phase_linear_frequency", projection)
    outcome = regional_reassignment.evaluate_veto(
        prepared, SimpleNamespace(satellite_numbers=(100,)), region,
    )
    assert locations == [row["latlon"] for row in expected[72:]]
    assert outcome["probes_evaluated"] == 24
    assert outcome["stop"] == "eligible_exterior_tie"
