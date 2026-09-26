"""Regression checks for physically disjoint spectral validation support."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

DIRECTORY = (
    Path(__file__).resolve().parents[2]
    / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/sync-spectral"
)
sys.path.insert(0, str(DIRECTORY))
SPEC = importlib.util.spec_from_file_location(
    "guarded_spectral_replay", DIRECTORY / "run_guarded_spectral.py"
)
assert SPEC and SPEC.loader
G = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G)


def test_shared_schedule_excludes_fir_support_overlap():
    starts, splits = G.schedule(177)
    assert np.array_equal((starts // 4) * 4, starts)
    assert starts[0] >= G.GUARD
    assert starts[-1] + G.WINDOW + G.GUARD <= 1_200_000
    for train, held in splits.values():
        G.assert_disjoint(starts, train, held)
    # Abutting estimator windows still overlap after the anti-alias FIR.
    with pytest.raises(ValueError, match="overlap"):
        G.assert_disjoint(np.array([0, G.WINDOW]), np.array([0]), np.array([1]))


def test_held_data_cannot_change_training_spectral_mask():
    rng = np.random.default_rng(143)
    values = rng.normal(size=(3 * G.WINDOW, 2)) + 1j * rng.normal(size=(3 * G.WINDOW, 2))
    starts = np.array([0, G.WINDOW, 2 * G.WINDOW])
    before, bandwidth = G.spectral(values, G.RATE, starts, np.array([0, 1]), 0.0, 0.0, (0.0, 0.0))
    values[2 * G.WINDOW :, 1] *= 1000 * np.exp(1.3j)
    after, changed_bandwidth = G.spectral(
        values, G.RATE, starts, np.array([0, 1]), 0.0, 0.0, (0.0, 0.0)
    )
    assert bandwidth == changed_bandwidth
    np.testing.assert_allclose(before["common"][:2], after["common"][:2])
    taper = np.hanning(G.WINDOW)
    direct = np.sum(np.conj(values[: G.WINDOW, 0]) * values[: G.WINDOW, 1] * taper**2)
    np.testing.assert_allclose(after["full"][0] / G.WINDOW, direct, rtol=1e-12)


def test_alias_selection_uses_training_samples_only():
    rng = np.random.default_rng(309)
    n = 3 * G.WINDOW
    left = rng.normal(size=n) + 1j * rng.normal(size=n)
    relative = 650_000.0
    right = left * np.exp(2j * np.pi * relative * np.arange(n) / G.RATE)
    raw = np.column_stack((left, right))
    starts = np.array([0, G.WINDOW, 2 * G.WINDOW])
    centers = (0.0, relative - 1 / 4.4e-6)
    before = G.choose_alias(raw, starts, np.array([0, 1]), centers)
    raw[2 * G.WINDOW :, 1] = rng.normal(size=G.WINDOW) * 1e6
    after = G.choose_alias(raw, starts, np.array([0, 1]), centers)
    assert before == after
    assert before[1]["selected_symbol_alias"] == 1
    assert before[0][1] == pytest.approx(relative)
