import math
from pathlib import Path
import importlib.util
import sys

import numpy as np
import pytest


PATH = Path(__file__).with_name("location_core.py")
SPEC = importlib.util.spec_from_file_location("roof_location_core", PATH)
CORE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = CORE
SPEC.loader.exec_module(CORE)


def fixture():
    measured = np.array([10., 20., 31., 41.])
    predicted = np.array([[0., 10., 20., 30.], [20., 30., 40., 50.], [0., 50., 0., 50.]])
    train = np.array([True, True, False, False])
    visible = np.array([True, True, True])
    east = np.array([[1., 1., 1., 1.], [-1., -1., -1., -1.], [0., 0., 0., 0.]])
    return predicted, east, measured, train, visible


def test_shortlist_profiles_constant_and_uses_training_only():
    predicted, _, measured, train, visible = fixture()
    first = CORE.train_shortlist(predicted, measured, train, visible, sigma_hz=100, top_k=2)
    changed = measured.copy(); changed[~train] = 1e9
    second = CORE.train_shortlist(predicted, changed, train, visible, sigma_hz=100, top_k=2)
    assert first == second
    assert first["candidate_indices"] == [0, 1]
    assert first["profiled_cfo_hz"] == pytest.approx([10., -10.])
    assert sum(first["weights"]) == pytest.approx(1.)


def test_doppler_score_is_exact_gaussian_mixture_with_constants():
    predicted, _, measured, train, visible = fixture()
    shortlist = CORE.train_shortlist(predicted, measured, train, visible, sigma_hz=2, top_k=2)
    result = CORE.doppler_heldout_score(predicted, measured, train, shortlist)
    # Both profiled candidates predict [30, 40], residual [1, 1].
    expected = .5 * (math.log(2 * math.pi) + 2 * math.log(2) + .25)
    assert result["mean_nll"] == pytest.approx(expected)
    assert result["map_heldout_rms_hz"] == pytest.approx(1.)


def test_reception_uses_prior_mean_east_and_conditional_ratio_only():
    _, east, _, _, _ = fixture()
    shortlist = {"candidate_indices": [0, 1], "weights": [.75, .25],
                 "profiled_cfo_hz": [0., 0.], "sigma_hz": 100.}
    rows = [
        {"observation_index": 2, "matched": True, "detection_logit_east0": 0.,
         "detection_east_slope": 2., "ratio_mean_east0": 1.,
         "ratio_east_slope": 2., "log_margin_ratio_rx1_rx0": 2.},
        {"observation_index": 3, "matched": False, "detection_logit_east0": 0.,
         "detection_east_slope": 2., "ratio_mean_east0": 999.,
         "ratio_east_slope": 999., "log_margin_ratio_rx1_rx0": None},
    ]
    result = CORE.reception_geometry_score(east, shortlist, rows, ratio_variance=4.)
    # Posterior/prior shortlist mean east is 0.5; matched ratio prediction is 2.
    assert result["detection_mean_nll"] == pytest.approx(
        (np.logaddexp(0, -1.) + np.logaddexp(0, 1.)) / 2
    )
    matched_only = .5 * math.log(8 * math.pi)
    assert result["conditional_ratio_mean_nll"] == pytest.approx(matched_only / 2)
    assert result["conditional_ratio_matched_only_mean_nll"] == pytest.approx(matched_only)
    assert result["conditional_ratio_observations"] == 1


def test_score_track_reports_fixed_natural_composite_and_ablations():
    predicted, east, measured, train, visible = fixture()
    rows = [{"observation_index": 2, "matched": False,
             "detection_logit_east0": 0., "detection_east_slope": 0.,
             "ratio_mean_east0": 0., "ratio_east_slope": 0.,
             "log_margin_ratio_rx1_rx0": None}]
    result = CORE.score_track(predicted, east, measured, train, visible, rows,
                              ratio_variance=1.)
    scores = result["scores"]
    assert scores["D_plus_detection"] == pytest.approx(scores["D"] + math.log(2))
    assert scores["D_plus_geometry"] == scores["D_plus_detection"]


def test_invalid_or_empty_inputs_fail_closed():
    predicted, east, measured, train, visible = fixture()
    with pytest.raises(ValueError, match="training"):
        CORE.train_shortlist(predicted, measured, np.zeros(4, bool), visible)
    with pytest.raises(ValueError, match="visible"):
        CORE.train_shortlist(predicted, measured, train, np.zeros(3, bool))
    shortlist = CORE.train_shortlist(predicted, measured, train, visible)
    with pytest.raises(ValueError, match="reception"):
        CORE.reception_geometry_score(east, shortlist, [], ratio_variance=1.)
    with pytest.raises(ValueError, match="variance"):
        CORE.reception_geometry_score(east, shortlist, [{}], ratio_variance=0.)
    training_row = [{"observation_index": 0, "matched": False,
                     "detection_logit_east0": 0., "detection_east_slope": 0.,
                     "ratio_mean_east0": 0., "ratio_east_slope": 0.,
                     "log_margin_ratio_rx1_rx0": None}]
    with pytest.raises(ValueError, match="reserve"):
        CORE.score_track(predicted, east, measured, train, visible, training_row,
                         ratio_variance=1.)


def test_extreme_training_contrast_preserves_log_domain_mixture():
    predicted = np.array([[0., 0., 1e4], [0., 1e4, 0.]])
    measured = np.zeros(3)
    train = np.array([True, True, False])
    shortlist = CORE.train_shortlist(predicted, measured, train, [True, True],
                                     sigma_hz=1., top_k=2)
    assert shortlist["weights"][1] == 0.0
    assert math.isfinite(shortlist["log_weights"][1])
    result = CORE.doppler_heldout_score(predicted, measured, train, shortlist)
    assert math.isfinite(result["mean_nll"])
    east = np.zeros_like(predicted)
    row = [{"observation_index": 2, "matched": False,
            "detection_logit_east0": 0., "detection_east_slope": 0.,
            "ratio_mean_east0": 0., "ratio_east_slope": 0.,
            "log_margin_ratio_rx1_rx0": None}]
    assert math.isfinite(CORE.reception_geometry_score(
        east, shortlist, row, ratio_variance=1.
    )["detection_mean_nll"])
