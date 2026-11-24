from math import sqrt

import pytest

from reports.ALGO08.v3.calibration_prediction_check import assess, predictive_mse


def arm(conditional_rms, prediction_mse):
    return dict(conditional_count=2, predictive_count=1, conditional_rms_hz=conditional_rms,
                all_owned_rms_hz=sqrt((2*conditional_rms**2 + prediction_mse)/3))


def test_worsening_prediction_under_improved_conditional_fit():
    good = {"c0": arm(5., 16.), "fitted_c": arm(4., 16.)}
    bad = {"c0": arm(5., 16.), "fitted_c": arm(4., 60.)}
    assert assess(good, True)["status"] == "pass"
    assert assess(bad, True)["status"] == "suspect"
    bad["fitted_c"] = arm(5., 60.)
    assert assess(bad, True)["status"] == "pass"


def test_unmatched_owners_or_missing_out_of_fit_data_abstain():
    arms = {"c0": arm(5., 16.), "fitted_c": arm(4., 60.)}
    assert assess(arms, False)["status"] == "unavailable"
    arms["fitted_c"]["predictive_count"] = 0
    assert assess(arms, True)["status"] == "unavailable"
    arms["fitted_c"] = arm(4., 60.) | {"all_owned_rms_hz": None}
    assert assess(arms, True)["status"] == "unavailable"


def test_role_weighting_and_bad_residual_authority():
    assert predictive_mse(5., arm(5., 16.)["all_owned_rms_hz"], 2, 1) == pytest.approx(16.)
    assert predictive_mse(0., 0., 2, 1) == 0
    with pytest.raises(ValueError, match="incompatible"):
        predictive_mse(5., 1., 2, 1)
