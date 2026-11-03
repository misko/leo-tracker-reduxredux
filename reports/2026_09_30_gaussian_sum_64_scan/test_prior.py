from __future__ import annotations

import numpy as np
from physics import PhysicsConfig, StateLayout, _noise_covariance, helmert_contrasts
from prior import (
    UniformDiskApproximation,
    _cell_moments,
    build_uniform_disk_prior,
    disk_probability,
)

from leo.analysis.gaussian_sum_location import (
    Candidate,
    FilterConfig,
    ObservationFactor,
    update_filter,
)


def test_cell_moments_agree_with_dense_deterministic_integration() -> None:
    inner, outer, center, half = 70.0, 130.0, 0.7, np.pi / 8
    mean, covariance = _cell_moments(inner, outer, center, half)
    # Midpoint integration is independent of the closed-form moment equations.
    radial = np.sqrt(np.linspace(inner**2, outer**2, 401)[:-1] + (outer**2-inner**2)/800)
    angles = np.linspace(center-half, center+half, 601)[:-1] + half/600
    points = np.stack((radial[:, None] * np.cos(angles), radial[:, None] * np.sin(angles)), axis=-1)
    numeric_mean = points.mean(axis=(0, 1))
    flat = points.reshape(-1, 2)
    numeric_second = flat.T @ flat / flat.shape[0]
    np.testing.assert_allclose(mean, numeric_mean, atol=2e-3)
    np.testing.assert_allclose(
        covariance, numeric_second - np.outer(numeric_mean, numeric_mean), atol=0.2
    )


def test_32_components_preserve_uniform_disk_global_moments_and_nuisances() -> None:
    layout = StateLayout((11, 22))
    specification = UniformDiskApproximation()
    state = build_uniform_disk_prior(layout, specification)
    assert len(state.components) == 32
    assert sum(component.weight for component in state.components) == 1.0
    mean = sum(component.weight * component.mean for component in state.components)
    second = sum(
        component.weight * (component.covariance + np.outer(component.mean, component.mean))
        for component in state.components
    )
    np.testing.assert_allclose(mean, 0.0, atol=1e-12)
    np.testing.assert_allclose(
        second[:2, :2], np.eye(2) * specification.radius_km**2 / 4, atol=1e-10
    )
    np.testing.assert_allclose(np.diag(second)[2:], [0.01, 1.0, 0.25, 0.25, 0.25, 0.25])


def test_disk_leakage_quadrature_is_stable_and_nonzero() -> None:
    state = build_uniform_disk_prior(StateLayout(()), UniformDiskApproximation())
    p1 = disk_probability(state, 250.0, radial_order=48, angular_order=96)
    p2 = disk_probability(state, 250.0, radial_order=72, angular_order=144)
    assert 0.0 < 1.0 - p2 < 0.2
    assert abs(p1-p2) < 2e-6


def test_background_only_low_information_update_preserves_all_32_prior_cells() -> None:
    state = build_uniform_disk_prior(StateLayout(()), UniformDiskApproximation())
    factor = ObservationFactor(
        observation_ids=("low-information",),
        observation=np.array([0.0]),
        candidates=(Candidate("zero-prior-signal", 0.0, lambda _: None),),
        background_prior=1.0,
        background_log_likelihood=-3.0,
    )
    result = update_filter(
        state,
        factor,
        FilterConfig(max_components=32, min_weight=1e-12, max_child_work=65536),
    )
    assert len(result.state.components) == 32
    assert result.retained_pre_normalization_mass == 1.0
    assert result.discarded_pre_normalization_mass == 0.0
    for before, after in zip(state.components, result.state.components, strict=True):
        assert before.weight == after.weight
        np.testing.assert_array_equal(before.mean, after.mean)
        np.testing.assert_array_equal(before.covariance, after.covariance)


def test_failed_replay_track_projected_noise_can_be_exactly_symmetrized() -> None:
    times = np.array(
        [0.0, 5.11643988, 15.43916897, 20.63783344,
         27.27784396, 36.38170975, 43.82583451, 51.36313777]
    )
    contrasts = helmert_contrasts(np.zeros(times.size, dtype=int))
    projected = contrasts @ _noise_covariance(times, PhysicsConfig()) @ contrasts.T
    repaired = (projected + projected.T) * 0.5
    np.testing.assert_array_equal(repaired, repaired.T)
    assert np.max(np.abs(repaired - projected)) < 6e-13
