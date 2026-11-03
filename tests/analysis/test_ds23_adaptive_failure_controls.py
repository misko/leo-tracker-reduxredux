"""Controls for causal prior differences and independently scaled residual gates."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from investigate_ds23_adaptive_failures import (  # noqa: E402
    causal_phase_sigma,
    polynomial_partition_bic,
    radio_tail_screen,
)
from prepare_ds23_genuine_causal_prior import earlier_epoch  # noqa: E402


def test_roundtrip_epoch_difference_is_not_an_independent_orbit_update():
    latest = 1792300000000000000
    assert not earlier_epoch(latest - 864000, latest)
    assert not earlier_epoch(latest, latest)
    assert not earlier_epoch(latest + 1000000000, latest)
    assert earlier_epoch(latest - 1000000000, latest)
    assert earlier_epoch(latest - 3600000000000, latest)


def test_causal_phase_proxy_depends_on_catalogue_disagreement_and_forecast_age():
    assert causal_phase_sigma(0., 90000., 30000.) == 1.
    young = causal_phase_sigma(2., 1000., 10000.)
    older = causal_phase_sigma(2., 10000., 10000.)
    assert 1 < young < older < 15
    assert causal_phase_sigma(-2., 10000., 10000.) == older
    assert causal_phase_sigma(100., 100000., 10000.) == 15
    with pytest.raises(ValueError, match="ordered epochs"):
        causal_phase_sigma(2., 10000., 0.)


def test_two_boundary_outliers_cannot_inflate_the_external_radio_noise_scale():
    # Overall RMS passes 450 Hz while the first point is a 12-sigma error.
    residual = np.r_[-1800., -700., np.full(36, 50.)]
    sigma = np.full(len(residual), 150.)
    assert np.sqrt(np.mean(residual**2)) < 450
    assert not radio_tail_screen(residual, sigma)["passes"]
    assert radio_tail_screen(residual[2:], sigma[2:])["passes"]
    with pytest.raises(ValueError, match="independent noise"):
        radio_tail_screen(residual, np.zeros(len(residual)))


def test_piecewise_polynomial_test_accounts_for_the_breakpoint_and_keeps_all_points():
    t = np.linspace(0, 100, 80)
    rng = np.random.default_rng(991)
    y = 20*t + np.maximum(0, t-50)**2*20 + rng.normal(0, 30, len(t))
    result = polynomial_partition_bic(t, y, np.full(len(t), 30.))
    best = result["splits"][0]
    assert best["bic"] < result["full"]["bic"] - 10
    assert 40 < best["after_s"] < 60
    assert best["bic"] == pytest.approx(
        best["left"]["bic"] + best["right"]["bic"] + np.log(len(t)))
