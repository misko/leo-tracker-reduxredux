"""Receiver additive-Hz and fractional-RF laws must leave orbital RF intact."""

from types import SimpleNamespace
import numpy as np
import pytest
from ds23_receiver_frequency_law import receiver_frequency_law


def test_additive_oscillator_has_identical_hz_at_distinct_rf_with_equal_time_support():
    basis = np.array([[.1, .2], [-.3, .4]])
    scan = SimpleNamespace(tracks=[dict(rf_hz=10.e9), dict(rf_hz=12.e9)], rx_basis=[basis, basis])
    changed = receiver_frequency_law(scan, "additive_Hz")
    for track, b in zip(changed.tracks, changed.rx_basis, strict=True):
        np.testing.assert_allclose(track["rf_hz"]/11.5e9*b, basis, atol=1e-15)
    np.testing.assert_array_equal(scan.rx_basis[0], basis)
    assert changed.tracks is scan.tracks


def test_incumbent_law_is_exact_null_and_design_copies_are_isolated():
    basis = np.arange(4.).reshape(2, 2)
    scan = SimpleNamespace(tracks=[dict(rf_hz=11.5e9)], rx_basis=[basis])
    for law in ("fractional_RF", "additive_Hz"):
        changed = receiver_frequency_law(scan, law)
        np.testing.assert_array_equal(changed.rx_basis[0], basis)
        changed.rx_basis[0][0, 0] = 9.
        assert scan.rx_basis[0][0, 0] == 0.


def test_invalid_radio_authority_or_unknown_law_is_rejected():
    scan = SimpleNamespace(tracks=[dict(rf_hz=float("nan"))], rx_basis=[np.ones((2, 1))])
    with pytest.raises(ValueError, match="physical RF"):
        receiver_frequency_law(scan, "additive_Hz")
    with pytest.raises(ValueError, match="unknown"):
        receiver_frequency_law(scan, "free_polynomial")
