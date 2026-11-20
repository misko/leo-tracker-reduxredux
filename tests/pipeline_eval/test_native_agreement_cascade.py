from copy import deepcopy

from tools.pipeline_eval.variants import native_agreement_cascade as cascade


def position(c0=(37.0, -122.0), fitted=(37.0, -122.0), status="ok"):
    return dict(
        status=status,
        boundary="fixture",
        metrics={},
        arms={"c0": {"latlon": c0}, "fitted_c": {"latlon": fitted}},
    )


def test_fast_path_returns_smooth_both_arms_and_never_calls_compact():
    smooth = position(fitted=(37.0, -122.001))

    def unavailable():
        raise AssertionError("fast acceptance must defer compact")

    outcome = cascade.execute(
        lambda: {"result": smooth}, lambda: {"result": position()}, unavailable
    )
    assert outcome["calls"] == ["smooth-clock", "curve-anchors"]
    assert outcome["compact"] is None
    assert outcome["result"]["arms"] == smooth["arms"]


def test_disagreement_on_one_arm_runs_compact_and_keeps_it_for_both():
    compact = position(c0=(37.1, -122.0), fitted=(37.2, -122.0))
    outcome = cascade.execute(
        lambda: {"result": position(fitted=(37.0, -122.1))},
        lambda: {"result": position()},
        lambda: {"result": compact},
    )
    assert outcome["route"]["reason"] == "disagreement"
    assert outcome["calls"] == ["smooth-clock", "curve-anchors", "compact-secant"]
    assert outcome["result"]["arms"] == compact["arms"]


def test_forced_position_cannot_satisfy_publication():
    fresh = position()
    withheld = position(c0=None, fitted=None, status="withheld")
    withheld["arms"] = deepcopy(fresh["arms"])
    for arm in withheld["arms"].values():
        arm["forced_latlon"] = arm.pop("latlon")
    choice = cascade.route(fresh, withheld)
    assert choice["route"] == "fallback"
    assert choice["reason"] == "insufficient_publication"
    assert choice["agreement_km"] == {"c0": None, "fitted_c": None}
