from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.lnb_band_objective import LnbBandObjective
from leo.analysis.shared_track_objective import SharedTrackObjective
from leo.application.hard60_runner import HARD60_SCORE
from tests.analysis.test_regional_position_bootstrap import bootstrap_fixture


def fixture(*, high=True, enabled=True, shared_prior=0.0):
    obs, bank, prior, tracks = bootstrap_fixture()
    if high:
        # Both receivers have both modes. The actual RF values remain explicit
        # independent inputs; the new nuisance is a receiver/mode intercept.
        obs = replace(obs, channel=np.where(np.arange(len(obs.times_s)) % 8 < 4, 1, 5))
    base = Hard60Objective(obs, bank, prior, HARD60_SCORE)
    nodes, knots = np.linspace(0, 80, 7), np.zeros((2, 7))
    centers = np.full(len(bank.numbers), obs.time_center_s)
    parent = SharedTrackObjective(base, nodes, knots, centers, tracks, shared_prior=shared_prior)
    model = LnbBandObjective(
        base, nodes, knots, centers, tracks, enabled=enabled, shared_prior=shared_prior
    )
    vector = np.array([3.1, -5.2, 600.0, 0.5, -600.0, 0.5, 0.0, 0.3, 0.03, -0.04])
    original_clock = np.random.default_rng(16).normal(0, 1, len(parent.initial_clock))
    return parent, model, vector, original_clock


@pytest.mark.parametrize("high,enabled", [(True, False), (False, True)])
def test_disabled_or_unobserved_high_band_is_exactly_the_original_model(high, enabled):
    parent, model, vector, clock = fixture(high=high, enabled=enabled)
    assert model.active_band_receivers == ()
    expanded = model.expand_parent_clock(clock)
    np.testing.assert_array_equal(expanded, clock)
    actual, expected = model.evaluate_joint(vector, expanded), parent.evaluate_joint(vector, clock)
    assert actual[0] == expected[0]
    np.testing.assert_array_equal(actual[1], expected[1])
    np.testing.assert_array_equal(actual[2], expected[2])


def test_band_columns_preserve_rf_tail_and_satellite_corrections():
    parent, model, _, clock = fixture()
    expanded = model.expand_parent_clock(clock, (-20320.0, 39315.0))
    np.testing.assert_array_equal(expanded[-2:], clock[-2:])
    np.testing.assert_allclose(model.band_offsets_hz(expanded), [-20320.0, 39315.0])
    assert model.offset_slice == parent.offset_slice and model.slope_slice == parent.slope_slice
    for actual, expected in zip(
        model.physical_corrections(expanded), parent.physical_corrections(clock), strict=True
    ):
        np.testing.assert_array_equal(actual, expected)
    # Gamma remains an available nuisance after c=0 locks only the RF tail.
    locked = expanded.copy()
    locked[-2:] = 0
    np.testing.assert_allclose(model.band_offsets_hz(locked), [-20320.0, 39315.0])


@pytest.mark.parametrize("shared_prior", [0.0, 0.5])
def test_full_derivatives_include_receiver_band_offsets(shared_prior):
    _, model, vector, parent_clock = fixture(shared_prior=shared_prior)
    clock = model.expand_parent_clock(parent_clock, (80.0, -100.0))
    _, gradient, nuisance, _ = model.evaluate_joint(vector, clock)
    for index in range(len(vector)):
        delta = np.zeros_like(vector)
        delta[index] = 0.001
        difference = (
            model.evaluate_joint(vector + delta, clock)[0]
            - model.evaluate_joint(vector - delta, clock)[0]
        ) / 0.002
        assert gradient[index] == pytest.approx(difference, rel=3e-5, abs=3e-6)
    for index in range(len(clock)):
        delta = np.zeros_like(clock)
        delta[index] = 0.001
        difference = (
            model.evaluate_joint(vector, clock + delta)[0]
            - model.evaluate_joint(vector, clock - delta)[0]
        ) / 0.002
        assert nuisance[index] == pytest.approx(difference, rel=3e-5, abs=3e-6)


def test_invalid_scales_or_clock_shapes_are_rejected():
    _, model, _, clock = fixture()
    with pytest.raises(ValueError):
        model.expand_parent_clock(clock[:-1])
    with pytest.raises(ValueError):
        model.band_offsets_hz(clock)
    for options in ({"band_sigma_hz": 0}, {"band_scale": np.nan}, {"band_scale": -1}):
        with pytest.raises(ValueError, match="finite and positive"):
            LnbBandObjective(None, None, None, None, (), **options)
