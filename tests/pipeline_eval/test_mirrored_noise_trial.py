from importlib import import_module
from math import erfc, sqrt

import numpy as np
import pytest

study = import_module("reports.ALGO08.single-core-2x.mirrored_noise_trial")


def test_satellite_resampling_keeps_all_same_orbit_signs_together():
    noise = np.array([1., 2., 6.])
    norad = np.array([100, 100, 200])
    scores = study.satellite_sign_distribution(noise, norad, np.ones(3))
    np.testing.assert_array_equal(np.sort(scores), [-9., -3., 3., 9.])


def test_oracle_and_shifted_nominal_risks_record_both_conditional_errors():
    exact = np.array([[-1., 1.]])
    proxy = np.array([1.])
    norad = np.array([100])
    oracle = study.template_risk(exact, exact, proxy, norad)
    assert oracle["iid_class_error"] == pytest.approx([erfc(1 / sqrt(2.)) / 2.] * 2)
    assert oracle["satellite_sign_class_error"] == [0.25, 0.25]
    assert oracle["margin_equivalent_m"] == [-100., 100.]
    assert oracle["noiseless_class"] == ["A", "B"]

    nominal = study.template_risk(exact + 3, exact, proxy, norad)
    assert nominal["noiseless_class"] == ["A", "A"]
    assert nominal["satellite_sign_class_error"] == [0., 1.]
    assert nominal["iid_worst_error"] > 0.97


def test_degenerate_likelihood_axes_cannot_create_confidence():
    identical = np.array([[1., 1.]])
    with pytest.raises(ValueError, match="distinct finite prediction templates"):
        study.template_risk(identical, identical, np.array([1.]), np.array([100]))
