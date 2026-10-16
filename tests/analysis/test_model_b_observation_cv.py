"""Original B oracle, normalized expansion nesting, fold isolation and every-coordinate FD."""

from copy import copy
from dataclasses import replace

import numpy as np
import pytest
import test_ds21_joint_bank_augmentation as orbit
import test_model_b_fusion_audit as fixture

from leo.analysis.research import model_b_observation_cv as core


@pytest.fixture
def example(monkeypatch):
    models, fits = fixture.models.__wrapped__(monkeypatch)
    monkeypatch.setattr(core, "predict_orbits", orbit.orbit_stub)
    return models["all"], fits["all"]


def test_legacy_exact_original_and_conditional_event_mass_oracles(example):
    original, fit = example
    v, n = np.asarray(fit["vector"]), np.asarray(fit["nuisance"])
    mask = np.ones(len(original.observations.window_ids), bool)
    legacy, normalized = (core.ObservationModel(original, mask, arm)
                          for arm in ("legacy", "conditional"))
    reference = original.evaluate_joint(v, n)
    old, _ = legacy.evaluate_details(v, n)
    new, details = normalized.evaluate_details(v, n)
    for a, b in zip(old[:3], reference[:3], strict=True):
        np.testing.assert_allclose(a, b, atol=1e-9, rtol=0)
    np.testing.assert_allclose(old[3].responsibilities, reference[3].responsibilities,
                               atol=1e-12, rtol=0)
    assert new[0]-old[0] == pytest.approx(details["log_integrated_event_mass"].sum(), abs=1e-9)
    np.testing.assert_allclose(new[1], old[1], atol=1e-12, rtol=0)
    np.testing.assert_allclose(new[2], old[2], atol=1e-12, rtol=0)
    for arm in ("dispersion", "detectability"):
        model = core.ObservationModel(original, mask, arm)
        out = model.evaluate_joint(v, np.r_[n, np.zeros(model.observation_parameter_count)])
        assert out[0] == pytest.approx(new[0], abs=1e-9)
        np.testing.assert_allclose(out[1], new[1], atol=1e-12, rtol=0)
        np.testing.assert_allclose(out[2][:len(n)], new[2], atol=1e-12, rtol=0)
        np.testing.assert_allclose(out[3].responsibilities, new[3].responsibilities, atol=1e-12)


@pytest.mark.parametrize("arm", core.ARMS)
def test_all_physical_clock_group_and_observation_coordinates_FD(example, arm):
    original, fit = example
    mask = np.arange(len(original.observations.window_ids)) % 2 == 0
    model = core.ObservationModel(original, mask, arm)
    tail = .05*np.cos(np.arange(model.observation_parameter_count))
    x = np.r_[fit["vector"], fit["nuisance"], tail]
    value = model.evaluate_joint(x[:model.size], x[model.size:])
    actual = np.r_[value[1], value[2]]
    finite = []
    for i in range(len(x)):
        delta = np.eye(len(x))[i]*1e-4
        plus, minus = x+delta, x-delta
        finite.append((model.evaluate_joint(plus[:model.size], plus[model.size:])[0]-
                       model.evaluate_joint(minus[:model.size], minus[model.size:])[0])/2e-4)
    np.testing.assert_allclose(actual, finite, atol=2e-6, rtol=3e-4)


def test_fold_excluded_measured_values_cannot_affect_any_arm_fit_objective(example):
    original, fit = example
    mask = np.arange(len(original.observations.window_ids)) % 2 == 0
    base = copy(original.base)
    measured = original.observations.measured_hz.copy()
    measured[~mask] += 100000
    base.observations = replace(original.observations, measured_hz=measured)
    changed = core.GroupCalibrationObjective(base, original.observations.channel >= 5,
        frame=original.frame, sigma_hz=original.sigma_hz)
    for arm in core.ARMS:
        a, b = (core.ObservationModel(o, mask, arm) for o in (original, changed))
        n = np.r_[fit["nuisance"], np.zeros(a.observation_parameter_count)]
        first, second = a.evaluate_joint(fit["vector"], n), b.evaluate_joint(fit["vector"], n)
        for x, y in zip(first[:3], second[:3], strict=True):
            np.testing.assert_array_equal(x, y)
        assert a.observations is original.observations  # Original physical domain remains full.
        assert len(a.scored_observations.window_ids) == mask.sum()


def test_declared_sigma_box_bounds_and_no_empty_fold(example):
    original, _ = example
    mask = np.ones(len(original.observations.window_ids), bool)
    model = core.ObservationModel(original, mask, "dispersion")
    limits = model.group_limits[original.group_count:]
    basis = model.channel_basis
    for row in basis:
        beta = np.sign(row)*limits[2:]
        for sign in [-1, 1]:
            log_sigma = sign*limits[0]+row@(sign*beta)
            assert 62.5-1e-10 <= 125*np.exp(log_sigma) <= 250+1e-10
    with pytest.raises(ValueError, match="Nonempty boolean"):
        core.ObservationModel(original, np.zeros(len(mask), bool), "legacy")


def test_original_bounded_fitter_tail_labels_and_nuisance_shape(example):
    original, seed = example
    model = core.ObservationModel(original,
        np.ones(len(original.observations.window_ids), bool), "dispersion")
    nuisance = np.r_[seed["nuisance"], np.zeros(model.observation_parameter_count)]
    fit = core.fit(model, np.array(seed["vector"]), nuisance, arm="fitted-c", seconds=2,
        iterations=100, fixed_position=True, local_center=seed["vector"][:2], local_radius_km=25)
    assert fit["observation_parameters"].shape == (9,)
    assert not len(fit["group_clock_coefficients"])
    assert fit["source_fitter_tail_metadata"]["generic_group_clock_coefficients"].shape == (9,)
    assert fit["observation_arm"] == "dispersion"
    assert fit["objective"] == pytest.approx(model.evaluate_joint(
        fit["vector"], fit["nuisance"])[0], abs=1e-7)
