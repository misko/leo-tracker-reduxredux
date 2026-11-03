"""Grid-local nuisance fitting and fine c arms share the same data and anchor."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
from test_dsx01_rf_clock_tool import problem_inputs


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("profile_dsx01_geographic_calibration")
    finally:
        sys.path.remove(path)


def test_profile_holds_requested_grid_point_instead_of_town_center(tool):
    scan, seed = problem_inputs()
    record = tool.fixed_profile(scan, seed, "shared_phase", [6.25, -6.25], iterations=2)
    assert record["east_north_km"] == [6.25, -6.25]
    assert len(record["seed"]["rows"]) == 4
    p = tool.geometry_problem(
        scan, record["seed"], "shared_phase", False, [6.25, -6.25], mean_sigma=10, height_sigma=0
    )
    p.problem.alias = record["aliases"]
    z = p.residual(p.initial)
    assert z @ z == pytest.approx(record["frequency_prior_score"])


def test_fine_pair_keeps_both_c_arms_at_same_grid_initialization_and_labels(tool):
    scan, seed = problem_inputs()
    record = tool.fixed_profile(scan, seed, "shared_phase", [-6.25, 0], iterations=2)
    fit = tool.fine_pair(scan, record, "shared_phase", iterations=2)
    assert fit["c0"]["rows"] == fit["fitted_c"]["rows"]
    assert fit["c0"]["aliases"] == fit["fitted_c"]["aliases"]
    assert fit["c0"]["starts"] == fit["fitted_c"]["starts"] == [[-6.25, 0]]
    assert (
        len(fit["fitted_c"]["fits"][0]["parameters"]) == len(fit["c0"]["fits"][0]["parameters"]) + 1
    )
    np.testing.assert_allclose(fit["c0"]["fits"][0]["history"][0]["parameters"][:2], [-6.25, 0])


def test_wide_radio_warm_start_survives_legacy_inner_clipping(tool):
    scan, seed = problem_inputs()
    rates = np.array([-12.0, -11.6, -9.0, -8.9])
    seed["state"]["beta"][4:8] = 150 * rates
    legacy = tool.legacy_geometry_problem(
        scan, seed, "shared_phase", False, (0, 0), mean_sigma=10, height_sigma=0
    )
    np.testing.assert_allclose(legacy.decode(legacy.initial)["beta"][4:8] / 150, -1)
    warm = tool.geometry_problem(
        scan, seed, "shared_phase", False, (0, 0), mean_sigma=10, height_sigma=0
    )
    np.testing.assert_allclose(warm.decode(warm.initial)["beta"][4:8] / 150, rates)
    np.testing.assert_array_equal(warm.lower, legacy.lower)
    np.testing.assert_array_equal(warm.upper, legacy.upper)
    for k, (key, _) in enumerate(warm.coordinates):
        if key[0] not in ("RX_drift_mean_hz_s", "RX_drift_band_contrast_hz_s"):
            assert warm.initial[k] == legacy.initial[k]
