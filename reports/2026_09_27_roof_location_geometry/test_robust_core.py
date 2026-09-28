import math
from pathlib import Path
import importlib.util
import sys

import numpy as np
import pytest


PATH = Path(__file__).with_name("robust_core.py")
SPEC = importlib.util.spec_from_file_location("roof_robust_core", PATH)
CORE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = CORE
SPEC.loader.exec_module(CORE)


def test_normalized_logdensity_matches_scipy():
    residual = np.array([-1e6, -10., 0., 20., 1e6])
    actual = CORE.student_t_logpdf(residual, scale_hz=123., degrees_of_freedom=3.5)
    # scipy.stats.t.logpdf(residual / 123, df=3.5) - log(123), captured
    # as a fixed oracle so this pure report module does not depend on SciPy.
    scipy_reference = [-43.49790929832157, -5.805903110763991,
                       -5.801657946631919, -5.818590756575204,
                       -43.49790929832157]
    assert actual == pytest.approx(scipy_reference)
    assert np.all(np.isfinite(actual))


def test_gaussian_limit():
    residual = np.array([-3., 0., 2.])
    actual = CORE.student_t_logpdf(residual, scale_hz=2., degrees_of_freedom=1e8)
    expected = -.5 * (math.log(2 * math.pi * 4) + (residual / 2.) ** 2)
    assert actual == pytest.approx(expected, abs=2e-7)


def test_shortlist_and_profile_use_training_only():
    predicted = np.array([[0., 1., 2., 3.], [5., 6., 7., 8.]])
    measured = np.array([10., 11., 12., 13.])
    mask = np.array([True, True, False, False])
    first = CORE.robust_train_shortlist(predicted, measured, mask, [True, True],
                                       scale_hz=100., degrees_of_freedom=4.)
    changed = measured.copy(); changed[~mask] = [1e8, -1e8]
    second = CORE.robust_train_shortlist(predicted, changed, mask, [True, True],
                                        scale_hz=100., degrees_of_freedom=4.)
    assert first == second
    assert sum(first["weights"]) == pytest.approx(1.)


def test_vectorized_locations_match_scalar_profiles_across_chunks():
    residual = np.array([[0., 1., 100.], [-50., 3., 4.], [8., 8., 8.]])
    vector = CORE.robust_locations(residual, scale_hz=7., degrees_of_freedom=4.)
    scalar = np.array([CORE.robust_location(
        row, scale_hz=7., degrees_of_freedom=4.
    ) for row in residual])
    assert vector == pytest.approx(scalar)
    predicted = -residual
    measured = np.zeros(4)
    predicted = np.column_stack([predicted, np.zeros(3)])
    mask = np.array([True, True, True, False])
    a = CORE.robust_train_shortlist(predicted, measured, mask, [True]*3,
                                    scale_hz=7., degrees_of_freedom=4.,
                                    candidate_chunk_size=1)
    b = CORE.robust_train_shortlist(predicted, measured, mask, [True]*3,
                                    scale_hz=7., degrees_of_freedom=4.,
                                    candidate_chunk_size=100)
    assert a == b


def test_extreme_tails_and_log_weights_remain_finite():
    predicted = np.array([[0., 0., 0.], [0., 1e100, -1e100]])
    measured = np.zeros(3); mask = np.array([True, True, False])
    shortlist = CORE.robust_train_shortlist(
        predicted, measured, mask, [True, True], scale_hz=1.,
        degrees_of_freedom=2., top_k=2,
    )
    assert np.all(np.isfinite(shortlist["log_weights"]))
    result = CORE.robust_heldout_score(predicted, measured, mask, shortlist)
    assert math.isfinite(result["mean_nll"])


def test_reserve_marginalization_uses_one_shared_identity():
    predicted = np.array([[0., 100.], [100., 0.]])
    measured = np.array([0., 0.])
    # Construct an explicit shortlist because both observations are reserve for
    # this likelihood identity test.
    shortlist = {"candidate_indices": [0, 1], "profiled_cfo_hz": [0., 0.],
                 "log_weights": [-math.log(2), -math.log(2)],
                 "scale_hz": 1., "degrees_of_freedom": 3.}
    result = CORE.robust_heldout_score(predicted, measured, [False, False], shortlist)
    lp_good = float(CORE.student_t_logpdf(np.array([0.]), scale_hz=1., degrees_of_freedom=3.)[0])
    lp_bad = float(CORE.student_t_logpdf(np.array([100.]), scale_hz=1., degrees_of_freedom=3.)[0])
    expected_shared = -CORE._logsumexp(np.array([
        -math.log(2) + lp_good + lp_bad,
        -math.log(2) + lp_bad + lp_good,
    ])) / 2
    redrawn = -(CORE._logsumexp(np.array([-math.log(2)+lp_good, -math.log(2)+lp_bad])) * 2) / 2
    assert result["mean_nll"] == pytest.approx(expected_shared)
    assert result["mean_nll"] > redrawn


def test_joint_score_shares_identity_across_frequency_and_reception():
    # Frequency favors candidate 0 while matched reception favors candidate 1.
    predicted = np.array([[0., 0.], [0., 10.]])
    east = np.array([[-1., -1.], [1., 1.]])
    measured = np.array([0., 0.])
    shortlist = {"candidate_indices": [0, 1], "profiled_cfo_hz": [0., 0.],
                 "log_weights": [-math.log(2), -math.log(2)],
                 "scale_hz": 1., "degrees_of_freedom": 3.}
    rows = [{"observation_index": 1, "matched": True,
             "detection_logit_east0": 0., "detection_east_slope": 3.,
             "ratio_mean_east0": 0., "ratio_east_slope": 0.,
             "log_margin_ratio_rx1_rx0": 0.}]
    result = CORE.joint_heldout_score(
        predicted, east, measured, [True, False], shortlist, rows,
        ratio_variance=1.,
    )
    freq = np.asarray(result["candidate_frequency_log_likelihood"])
    det = np.asarray(result["candidate_detection_log_likelihood"])
    expected = -CORE._logsumexp(np.array(shortlist["log_weights"]) + freq + det)
    separately_marginalized = (-CORE._logsumexp(np.array(shortlist["log_weights"]) + freq)
                               - CORE._logsumexp(np.array(shortlist["log_weights"]) + det))
    assert result["scores"]["D_plus_detection"] == pytest.approx(expected)
    assert result["scores"]["D_plus_detection"] != pytest.approx(separately_marginalized)
