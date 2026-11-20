import json

import pytest

from tools.pipeline_eval.qualification import recenter_verify_trial as trial
from tools.pipeline_eval.scoring import ARMS
from tools.pipeline_eval.variants import recenter_verify as variant

TILE = dict(id="opaque", center=[37.9, -122.5], width_km=25)


def fit(c0=None, fitted=None, status="ok"):
    return dict(
        status=status,
        reason=None,
        arms={
            arm: dict(latlon=point, forced_latlon=point, region_id=TILE["id"])
            for arm, point in zip(ARMS, (c0, fitted), strict=True)
        },
    )


def test_verifier_reuses_first_fix_and_serializes_both_containment_flags():
    first = fit([37.91, -122.51], [37.9, -122.5])

    def expanded(offer):
        assert offer == dict(id="opaque-verify", center=[37.91, -122.51], width_km=50)
        return fit([37.911, -122.51], [37.9, -122.49])

    decision, receipt = variant.verify(first, TILE, expanded)
    assert decision["arms"] == first["arms"]
    assert decision["status"] == "ok"
    assert receipt["expanded_inside_original"] == dict.fromkeys(ARMS, True)
    json.dumps(receipt)


@pytest.mark.parametrize(
    ("other", "why"),
    [
        (fit(status="withheld"), "expanded_fit_withheld"),
        (fit([37.9, -122.5], [37.9, -122.8]), "expanded_fit_outside_original"),
        (fit([37.9, -122.5], [37.9, -122.473]), "expanded_fit_disagrees"),
    ],
)
def test_either_arm_can_withhold_while_preserving_the_original_forced_fix(other, why):
    center = TILE["center"]
    first = fit(center, center)
    result, receipt = variant.verify(first, TILE, lambda _tile: other)
    assert result["status"] == "withheld"
    assert result["reason"] == why
    assert result["arms"]["fitted_c"]["latlon"] is None
    assert result["arms"]["fitted_c"]["forced_latlon"] == center
    assert receipt["attempted"]


def test_a_first_pass_withholding_never_attempts_the_wider_search():
    first = fit(status="withheld")
    decision, receipt = variant.verify(first, TILE, lambda _tile: pytest.fail("unexpected search"))
    assert decision["status"] == "withheld"
    assert receipt == {"attempted": False}


def test_vary_only_the_offer_on_ten_disjoint_recordings():
    plan = trial.phase._read(trial.clock.REPORT / "plan.json")
    excluded = {i for group in trial.geom.roster(plan).values() for i in group}
    ids = trial.roster(plan)
    assert len(ids) == 10 and all(ident.startswith("DS26-") for ident in ids)
    assert not set(ids) & excluded
    study = list(trial.new_offers(ids[0], TILE["center"], TILE))
    assert [
        float(12.5 - max(abs(trial.geom.tangent(TILE["center"], t["center"])))) for t, _ in study
    ] == pytest.approx([12.5, 1.5, -1.5, -6])
