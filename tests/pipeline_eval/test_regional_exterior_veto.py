import pytest

from leo.analysis.localization_v3.region import SearchRegion
from tools.pipeline_eval.variants.experimental.regional_exterior_veto import evaluate
from tools.pipeline_eval.variants.experimental.regional_reassignment import probes


WIDTH = 20.


def fixture(second=(50., 0.)):
    points = list(probes(SearchRegion((46., 12.), WIDTH)))
    for point in points:
        coordinates = tuple(point["xy_km"])
        point["receiver_scores"] = {
            receiver: 2. if coordinates == exterior else float(point["side"] == "inside")
            for receiver, exterior in (("1", (30., 0.)), ("2", second))
        }
    return points


def scores_at(points, coordinates):
    return next(point["receiver_scores"] for point in points if point["xy_km"] == list(coordinates))


def test_accepts_inclusive_width_and_agreement_boundaries():
    points = fixture()
    result = evaluate(points, WIDTH)
    assert result["would_withhold"]
    assert result["exterior_separation_km"] == WIDTH
    assert result["receivers"]["1"]["exterior_clearance_km"] == WIDTH
    assert evaluate(reversed(points), WIDTH)["would_withhold"]


@pytest.mark.parametrize("second", ((-30., 0.), (50., 4.)))
def test_disagreement_rejects_two_favorable_deep_solutions(second):
    result = evaluate(fixture(second), WIDTH)
    assert all(receiver["gain"] > 0 for receiver in result["receivers"].values())
    assert result["exterior_separation_km"] > WIDTH
    assert not result["would_withhold"]


def test_better_near_solution_takes_precedence_over_deep_gain():
    points = fixture()
    scores_at(points, (12.5, 0.))["2"] = 3.
    result = evaluate(points, WIDTH)
    assert result["receivers"]["2"]["gain"] == 2.
    assert result["receivers"]["2"]["exterior_clearance_km"] == 2.5
    assert not result["would_withhold"]


@pytest.mark.parametrize("score", (0., 1.))
def test_each_receiver_must_strictly_improve_on_its_inside_best(score):
    points = fixture()
    scores_at(points, (50., 0.))["2"] = score
    assert not evaluate(points, WIDTH)["would_withhold"]


def test_ambiguous_exterior_maximum_cannot_veto():
    points = fixture()
    scores_at(points, (30., 4.))["1"] = 2.
    result = evaluate(points, WIDTH)
    assert not result["receivers"]["1"]["unique_exterior"]
    assert not result["would_withhold"]


@pytest.mark.parametrize("damage", ("missing", "duplicate", "nonfinite", "receiver", "side"))
def test_incomplete_probe_evidence_never_vetoes(damage):
    points = fixture()
    if damage == "missing":
        points.pop()
    elif damage == "duplicate":
        points[-1] = points[0]
    elif damage == "nonfinite":
        points[0]["receiver_scores"]["1"] = float("nan")
    elif damage == "receiver":
        del points[0]["receiver_scores"]["1"]
    else:
        points[0]["side"] = "exterior"
    assert evaluate(points, WIDTH) == {"would_withhold": False, "complete": False}
