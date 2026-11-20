import numpy as np
import pytest

from tools.pipeline_eval.qualification import edge_holdout_results as results
from tools.pipeline_eval.qualification import edge_holdouts as trial
from tools.pipeline_eval.qualification import screening_figures
from tools.pipeline_eval.qualification.native_joint_full_results import roi_margin
from tools.pipeline_eval.scoring import ARMS, distance_km


@pytest.mark.parametrize(("site", "band"), trial.SITES)
def test_guarded_edge_offers_share_opposite_physical_margins(site, band):
    center, inside, outside, far = trial.offers(site, np.random.default_rng(44714), band)
    assert 8 <= distance_km(center["center"], site) <= 10
    assert band[0] <= roi_margin(site, inside) <= band[1]
    assert roi_margin(site, outside) == pytest.approx(-roi_margin(site, inside), abs=1e-8)
    assert -65 <= roi_margin(site, far) <= -35


def test_only_a_complete_scientific_fit_qualifies_as_stock_shadow():
    arms = {arm: dict(latlon=[-12.0, 24.0], rf_rms_hz=49.0) for arm in ARMS}
    row = dict(result=dict(status="ok", arms=arms), wall_s=37.9)
    shadow = results.stock_for(row, None)
    assert shadow["comparison"] == "exact_endpoint_shadow"
    assert shadow["result"]["arms"] == arms
    assert shadow["wall_s"] is None
    for status in ("withheld", "failed", "timed_out"):
        attempt = results.stock_for(dict(result=dict(status=status)), None)
        assert attempt["comparison"] == "not_run"
        assert attempt["result"]["status"] == "unavailable"
        assert all(not attempt["result"]["arms"][arm]["latlon"] for arm in ARMS)


def test_three_site_card_keeps_all_offers_on_each_calibration_arm():
    [card] = screening_figures.charts(evidence=trial.REPORT)
    assert len(card.cases) == 12
    for arm in ARMS:
        marks = card.page(arm).rows
        assert {mark.dataset for mark in marks} == set(results.NAMES.values())
        for series in ("candidate", "stock"):
            assert len([mark for mark in marks if mark.series == series]) == 12
