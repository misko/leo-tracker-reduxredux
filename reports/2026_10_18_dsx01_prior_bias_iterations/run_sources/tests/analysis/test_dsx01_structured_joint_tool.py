"""Dense covariance and secular-transport controls for structured alternatives."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("dsx01_structured_joint")
    finally:
        sys.path.pop(0)


def test_colored_whitening_and_volume_match_dense_covariance(tool):
    t, sigma = np.array([0.0, 0.3, 2.0, 8.0, 19.0]), 110.0
    w, volume = tool.covariance_whitener(t, sigma)
    cov = sigma**2 * np.eye(len(t)) + 150**2 * np.exp(-abs(t[:, None] - t) / 10)
    np.testing.assert_allclose(w @ cov @ w.T, np.eye(len(t)), atol=1e-13)
    np.testing.assert_allclose(volume, np.linalg.slogdet(cov)[1] - len(t) * np.log(sigma**2))


def test_block_whitening_preserves_full_dense_marginal_likelihood(tool):
    joint = importlib.import_module("dsx01_joint_marginal")
    rng = np.random.default_rng(14)
    y, u = rng.normal(size=8) * 100, rng.normal(size=(8, 3)) * 30
    times = [np.array([0.0, 1.0, 4.0]), np.array([0.0, 0.5, 1.0, 7.0, 8.0])]
    matrices, volumes = zip(*(tool.covariance_whitener(t, 100) for t in times), strict=True)
    z, a = tool.whiten_blocks(y, u, [slice(0, 3), slice(3, 8)], matrices)
    result = joint.integrated_gaussian(z, a, 1.0)
    w = np.zeros((8, 8))
    w[:3, :3], w[3:, 3:] = matrices
    covariance = np.linalg.inv(w.T @ w) + u @ u.T
    expected = (
        y @ np.linalg.solve(covariance, y) + np.linalg.slogdet(covariance)[1] - 8 * np.log(100**2)
    )
    np.testing.assert_allclose(
        result["residual"] @ result["residual"] + sum(volumes), expected, atol=1e-12
    )


def test_eccentricity_prior_uses_propagated_common_epoch_not_original_perigee(tool):
    current = SimpleNamespace(ecco=0.001, argpo=0.0, jdsatepoch=2461000.0, jdsatepochF=0.2)

    class Previous:
        ecco, argpo = 0.001, np.pi / 2

        def sgp4(self, jd, fraction):
            assert (jd, fraction) == (2461000.0, 0.2)
            self.em, self.om = 0.001, 0.0
            return 0, None, None

    sigma, difference = tool.eccentricity_sigma(current, Previous())
    np.testing.assert_allclose(sigma, [1e-5, 1e-5])
    np.testing.assert_array_equal(difference, [0.0, 0.0])


def test_whitening_rejects_missing_or_overlapping_observation_blocks(tool):
    with pytest.raises(ValueError, match="cover"):
        tool.whiten_blocks(np.ones(4), np.ones((4, 2)), [slice(0, 2), slice(1, 3)], [np.eye(2)] * 2)


def test_exact_combined_orbit_mean_matches_direct_sgp4_initialization(tool):
    exact = importlib.import_module("dsx01_joint_exact_mean")
    from sgp4.api import WGS72, Satrec

    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
    from leo.sky.propagation import ElementSetCatalogue

    nominal = Satrec()
    nominal.sgp4init(WGS72, "i", 12345, 26438.0, 0.0, 0.0, 0.0, 0.001, 0.3, 0.7, 0.1, 0.065, 0.2)
    # A self-contained satellite and bank: no private corpus or hardware needed.
    origin = 1640995200000000000
    knots, times = np.arange(-20.0, 101.0), np.array([3.0, 40.0, 78.0])
    bank_p, bank_v, good = exact.ecef_states(
        ElementSetCatalogue(("x",), (12345,), (nominal,)), origin, knots
    )
    assert good.all()
    coefficients = np.zeros(17)
    coefficients[11:16] = [0.4, -0.2, 0.3, 0.5, -0.4]
    sigma = np.array([1e-4, 2e-4])

    # The helper normally reads a causal TLE. Substitute only construction,
    # keeping the real propagation and parameter composition under test.
    original_satrec = exact.Satrec
    exact.Satrec = SimpleNamespace(twoline2rv=lambda *args: nominal)
    problem = SimpleNamespace(
        labels=[0],
        supported=[0],
        hardware=np.zeros((3, 8)),
        smooth=np.zeros((3, 2)),
        scan=SimpleNamespace(
            norads=np.array([12345]),
            elements={"12345": {"lines": ["a", "b"]}},
            receipt={"origin_utc_ns": origin},
        ),
        mode_metadata={
            0: dict(mean_motion_sigma_rev_day=0.001, inclination_sigma_deg=0.1, raan_sigma_deg=0.1)
        },
        ecc_bank=True,
        ecc_metadata={0: {"sigma": sigma}},
        sky=dict(time_s=knots, position_km=bank_p, velocity_km_s=bank_v),
        flat_times=times,
        flat_labels=np.zeros(3, dtype=int),
        calculate=lambda x: dict(coefficient=coefficients, scales=np.ones(3)),
        state=lambda x: dict(phases=np.array([2.0])),
    )
    try:
        actual, _, _ = exact.exact_conditional_frequency(problem, np.zeros(2))
    finally:
        exact.Satrec = original_satrec
    ex, ey = 0.001 * np.cos(0.3) + 0.5e-4, 0.001 * np.sin(0.3) - 0.4 * 2e-4
    omega = np.arctan2(ey, ex) % (2 * np.pi)
    elapsed_days = (
        (origin / 1e9 + 150) / 86400 + 2440587.5 - nominal.jdsatepoch - nominal.jdsatepochF
    )
    expected_sat = Satrec()
    expected_sat.sgp4init(
        WGS72,
        "i",
        12345,
        26438.0,
        0.0,
        0.0,
        0.0,
        np.hypot(ex, ey),
        omega,
        0.7 - np.deg2rad(0.02),
        (0.4 - omega - 2 * np.pi * 0.0004 * elapsed_days) % (2 * np.pi),
        0.065 + 0.0004 * 2 * np.pi / 1440,
        0.2 + np.deg2rad(0.03),
    )
    p, v, good = exact.ecef_states(
        ElementSetCatalogue(("x",), (12345,), (expected_sat,)), origin, knots
    )
    assert good.all()
    frequency, _ = paired_phase_frequency(
        dict(time_s=knots, position_km=p, velocity_km_s=v),
        times,
        np.zeros(3, dtype=int),
        np.array([2.0]),
        *exact.latlon(np.zeros(2)),
    )
    np.testing.assert_allclose(actual, frequency, atol=2e-7, rtol=1e-12)
