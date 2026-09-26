"""Tests for independent-reference geometric phase recovery prototype."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/single-track/recovery/reference/run.py"
spec = importlib.util.spec_from_file_location("reference_recovery", SCRIPT)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def test_complex_division_sign_and_common_phase_cancellation():
    d = M.simulate(seed=8, reference_noise=0)
    train = np.arange(len(d["t"])) < 500
    r = M.recover(d["satellite"], d["reference"], d["injection"],
                  d["delay_samples"], train)
    held = (~train) & r["valid"]
    error = M.wrap(r["phase_rad"][held] - d["geometry"][held])
    assert np.degrees(np.sqrt(np.mean(error**2))) < 2
    # Equal phase applied to the two cross-products cancels algebraically.
    common = np.exp(1j * .81)
    shifted = M.recover(d["satellite"]*common, d["reference"]*common,
                        d["injection"], d["delay_samples"], train)
    np.testing.assert_allclose(M.wrap(shifted["phase_rad"][held] - r["phase_rad"][held]), 0, atol=1e-12)


def test_known_injection_path_is_required_to_avoid_constant_bias():
    d = M.simulate(seed=3, reference_noise=0)
    train = np.arange(len(d["t"])) < 500
    good = M.recover(d["satellite"], d["reference"], d["injection"], d["delay_samples"], train)
    bad = M.recover(d["satellite"], d["reference"], np.ones_like(d["injection"]), d["delay_samples"], train)
    valid = good["valid"] & bad["valid"]
    # Wrong injection metadata leaves a material, stable calibration gauge bias.
    bias = np.angle(np.mean(np.exp(1j*(bad["phase_rad"][valid]-good["phase_rad"][valid]))))
    assert abs(np.degrees(bias)) > 10


def test_held_recovery_and_unsafe_subtraction_erases_slow_geometry():
    _, _, _, _, metrics = M.experiment(seed=32)
    assert metrics["independent_reference_rmse_deg"] < 3
    assert metrics["uncalibrated_rmse_deg"] > 50
    assert metrics["unsafe_same_satellite_rmse_deg"] > 25
    assert metrics["unsafe_held_excursion_deg"] < .35 * metrics["true_held_excursion_deg"]


def test_held_satellite_changes_do_not_change_reference_calibration_inputs():
    d = M.simulate(seed=4)
    train = np.arange(len(d["t"])) < 600
    base = M.recover(d["satellite"], d["reference"], d["injection"], d["delay_samples"], train)
    changed = d["satellite"].copy()
    changed[~train] *= np.exp(1j*.4)
    moved = M.recover(changed, d["reference"], d["injection"], d["delay_samples"], train)
    held = (~train) & base["valid"]
    np.testing.assert_allclose(M.wrap(moved["phase_rad"][held]-base["phase_rad"][held]), .4, atol=1e-12)


def test_missing_and_unsupported_reference_cases_are_explicit():
    d = M.simulate(seed=2)
    train = np.arange(len(d["t"])) < 200
    missing = np.full_like(d["reference"], np.nan+1j*np.nan)
    with pytest.raises(ValueError, match="no supported training"):
        M.recover(d["satellite"], missing, d["injection"], d["delay_samples"], train)
    with pytest.raises(ValueError, match="delay is unsupported"):
        M.recover(d["satellite"], d["reference"], d["injection"], len(d["t"]), train)
    with pytest.raises(ValueError, match="one phasor per tone"):
        M.recover(d["satellite"], d["reference"], d["injection"][:-1], d["delay_samples"], train)
    zero = d["reference"].copy(); zero[d["delay_samples"]] = 0
    r = M.recover(d["satellite"], zero, d["injection"], d["delay_samples"], train)
    assert not r["valid"][0]
    with pytest.raises(ValueError, match="finite and nonzero"):
        M.recover(d["satellite"], d["reference"], np.zeros_like(d["injection"]), d["delay_samples"], train)
    with pytest.raises(ValueError, match="one value per frame"):
        M.recover(d["satellite"], d["reference"], d["injection"], d["delay_samples"], train[:-1])


def test_zero_delay_reference_is_supported():
    d = M.simulate(seed=7, delay_samples=0, reference_noise=0)
    train = np.arange(len(d["t"])) < 400
    r = M.recover(d["satellite"], d["reference"], d["injection"], 0, train)
    assert r["valid"].all()
    assert np.degrees(M.circular_rmse(r["phase_rad"], d["geometry"])) < 2


def test_noncommon_drift_is_not_removed_by_reference():
    d = M.simulate(seed=6, reference_noise=0)
    train = np.arange(len(d["t"])) < 500
    extra = .3*d["t"]**2  # e.g. differential multipath or an unreferenced branch
    satellite = d["satellite"] * np.exp(1j*extra[:, None])
    r = M.recover(satellite, d["reference"], d["injection"], d["delay_samples"], train)
    valid = r["valid"]
    residual = M.wrap(r["phase_rad"][valid]-d["geometry"][valid])
    expected = M.wrap(extra[valid])
    assert np.degrees(M.circular_rmse(residual, expected)) < 2
    assert np.degrees(np.ptp(np.unwrap(residual))) > 100
