"""Native nonlinear oscillator drift must not acquire a channel RF multiplier."""

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
        yield importlib.import_module("dsx01_native_drift")
    finally:
        sys.path.pop(0)


def test_native_basis_is_identical_at_different_RF_in_the_same_hardware_group(tool):
    t, rx, band, q = (
        np.array([80.0, 80.0]),
        np.ones(2, int),
        np.zeros(2, int),
        np.array([0.93, 1.07]),
    )
    native = tool.smooth_columns(t, rx, band, q, "native_rx")
    np.testing.assert_array_equal(native[0], native[1])
    mixed = tool.smooth_columns(t, rx, band, q, "mixed_rx")
    np.testing.assert_allclose(mixed[0, :11], mixed[1, :11])
    np.testing.assert_allclose(mixed[0, 11:22] / q[0], mixed[1, 11:22] / q[1])


def test_independent_band_columns_are_disjoint_and_have_no_affine_component(tool):
    t = np.linspace(0, 300, 301)
    rx = np.ones(len(t), int)
    low = tool.smooth_columns(t, rx, np.zeros(len(t), int), np.ones(len(t)), "native_band")
    high = tool.smooth_columns(t, rx, np.ones(len(t), int), np.ones(len(t)), "native_band")
    assert not np.any(low[:, 11:]) and not np.any(high[:, :11])
    np.testing.assert_allclose(
        np.column_stack([np.ones(len(t)), (t - 150) / 150]).T @ low, 0, atol=1e-12
    )


def test_compatibility_prediction_adds_native_radio_exactly_once(tool):
    p = SimpleNamespace(
        conditional_frequency=lambda x: (np.array([100.0, 200.0]), np.ones(2)),
        nonlinear_radio_mean=lambda x: np.array([30.0, 40.0]),
        q=np.array([0.9, 1.1]),
    )
    adapter = tool.NativeDriftEvaluation(p)
    predicted, _ = adapter.predicted(np.zeros(2))
    np.testing.assert_allclose(predicted * p.q, [120, 260])


def test_gate_adapter_does_not_change_the_persisted_native_radio_coordinates(tool):
    actual = np.arange(44).reshape(2, 22)
    p = SimpleNamespace(
        state=lambda x: dict(smooth=actual),
        supported=[3],
        scan=SimpleNamespace(rx_basis=[np.zeros((3, 11))]),
    )
    result = tool.NativeDriftEvaluation(p).association_state(np.zeros(2))
    np.testing.assert_array_equal(actual, np.arange(44).reshape(2, 22))
    assert result["smooth"].shape == (2, 11) and not result["smooth"].any()
