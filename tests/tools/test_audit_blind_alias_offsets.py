import importlib.util
from pathlib import Path

import numpy as np
import pytest

PATH = Path(__file__).parents[2] / "tools/research/audit_blind_alias_offsets.py"
SPEC = importlib.util.spec_from_file_location("audit_blind_alias_offsets", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_rf_denormalization_inverts_canonical_scaling():
    actual = 10_709_687_498.0
    native = -38_000.0
    normalized = native * MODULE.CANONICAL_RF_HZ / actual
    assert MODULE.native_offset_hz(normalized, actual) == pytest.approx(native)


def test_alias_wrap_is_signed_and_periodic():
    period = MODULE.ALIAS_SPACING_HZ
    values = np.array([-0.6 * period, -10.0, 0.0, 10.0, 0.6 * period])
    expected = np.array([0.4 * period, -10.0, 0.0, 10.0, -0.4 * period])
    np.testing.assert_allclose(MODULE.wrap_alias_hz(values), expected)
    np.testing.assert_allclose(
        MODULE.wrap_alias_hz(values + 3 * period), expected, atol=1e-9
    )


def test_circular_mean_crosses_alias_seam():
    period = MODULE.ALIAS_SPACING_HZ
    mean = MODULE.circular_mean_hz([period / 2 - 100, -period / 2 + 100])
    assert abs(abs(mean) - period / 2) < 1e-9
