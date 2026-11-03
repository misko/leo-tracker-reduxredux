"""Clock covariance, family information and phase/orbit coordinate contracts."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("dsx01_satellite_prior_controls")
    finally:
        sys.path.pop(0)


def test_shared_fractional_clock_preserves_the_original_marginal_variance(tool):
    labels, rf = np.array([0, 0, 1, 2]), np.array([10.7, 12.4, 11.2, 11.7]) * 1e9
    clock, independent = tool.clock_design(
        labels,
        rf,
        [0, 1],
        shared_sigma=np.sqrt(0.9) * 1000,
        reference_hz=12.5e9,
        preserve_variance=True,
    )
    covariance = clock @ clock.T + np.diag(independent**2)
    np.testing.assert_allclose(np.diag(covariance), 1e6)
    np.testing.assert_allclose(covariance[0, 1], 0.9e6 * rf[0] * rf[1] / 12.5e9**2)
    assert covariance[0, 2] == 0 and covariance[0, 3] == 0
    assert independent[3] == 1000


def test_effective_family_count_is_capped_without_discarding_observations(tool):
    labels = np.repeat([0, 1, 2], [150, 50, 10])
    groups = np.repeat(np.arange(21), 10)
    powers = tool.family_powers(labels, groups, 100)
    effective = np.bincount(labels, weights=powers[groups])
    np.testing.assert_allclose(effective, [100, 50, 10])
    assert np.all(powers > 0)


def test_global_rf_coefficient_does_not_shift_the_semantic_prior_groups(tool):
    for hardware in (8, 9):
        phase_start = hardware + 22
        size = phase_start + 3 + 6 + 8
        groups = tool.orbital_prior_groups(size, phase_start, [2, 8, 11], [0, 2])
        np.testing.assert_array_equal(groups[phase_start : phase_start + 3], [0, 1, 2])
        np.testing.assert_array_equal(groups[phase_start + 3 : phase_start + 9], [0, 0, 0, 2, 2, 2])
        assert np.all(groups[:phase_start] == -1) and np.all(groups[-8:] == -1)
