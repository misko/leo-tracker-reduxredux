from tools.pipeline_eval.qualification.cavity_replay_results import outcome
from tools.pipeline_eval.qualification.cavity_replay_worker import priors, select


def family(source, alternate, gain, ids):
    return dict(
        original_norad=source,
        best=dict(norad=alternate) if alternate else None,
        predictive_gain=gain,
        held_observation_ids=ids,
        held_points=len(ids),
    )


def test_cavity_hint_ranks_actual_alternatives_without_geo_and_retains_negative_gain():
    measurements = dict(
        families=[
            family(99, 100, -1, ["x"]),
            family(57, 108, 2, ["a"]),
            family(42, 54, 2, ["b"]),
            family(90, None, None, []),
        ]
    )
    observed = priors(measurements)
    assert [(r["source"], r["alternate"]) for r in observed] == [
        (42, 54),
        (57, 108),
        (99, 100),
    ]
    assert observed[-1]["stock_predictive_gain"] == -1


def test_cavity_hint_can_challenge_stock_prior_when_union_already_uses_stock_alternative():
    rows = priors(dict(families=[family(11, 22, 3, ["a", "b", "c", "d"])]))
    agreed = {k: {"norad": 22} for k in "abcd"}
    result = select(rows, agreed, {11, 22, 33})
    assert (result["target"], result["challenger"], result["matched_points"]) == (22, 11, 4)
    assert select(rows, agreed, {22, 33}) is None
    assert select(rows, {k: agreed[k] for k in "abc"}, {11, 22, 33}) is None
    assert select(rows, agreed | {"a": {"norad": 11}}, {11, 22, 33}) is None


def test_rejected_real_fit_is_reported_as_diagnostic_and_preserves_published_pair():
    incumbent = dict(
        status="ok",
        boundary="production",
        arms={arm: dict(latlon=[37.8, -122.4], rf_rms_hz=80.0) for arm in ("c0", "fitted_c")},
        metrics={f"{arm}_frequency_score": 40000 for arm in ("c0", "fitted_c")},
    )
    fit = dict(
        production=incumbent,
        accepted=False,
        ordinary_arms={
            arm: info | {"frequency_objective": 40000} for arm, info in incumbent["arms"].items()
        },
        forced={arm: dict(latlon=[37.81, -122.39], rf_rms_hz=81.0) for arm in incumbent["arms"]},
    )
    result = outcome(({}, fit), {"result": incumbent}, True)
    assert all(arm["latlon"] == [37.8, -122.4] for arm in result["arms"].values())
    assert all(arm["forced_latlon"] == [37.81, -122.39] for arm in result["arms"].values())
    assert result["arms"]["fitted_c"]["forced_rf_rms_hz"] == 81.0
