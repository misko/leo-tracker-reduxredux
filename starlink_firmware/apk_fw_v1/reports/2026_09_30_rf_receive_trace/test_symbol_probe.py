import pytest
from symbol_probe import equalization, unpack


def test_capture_signed_extremes_and_ignored_bits():
    assert unpack([0x7FFC8000, 0x7FFF8003, 0xFFFFFFFF]) == [
        (-8192, 8191), (-8192, 8191), (-1, -1)]


def test_equalization_phase_error_and_zero_guard():
    assert equalization(1+0j, 1j) == pytest.approx(2)
    assert equalization(1+2j, 3+4j) == pytest.approx(1.6)
    assert equalization(0j, 3+4j) == 1
