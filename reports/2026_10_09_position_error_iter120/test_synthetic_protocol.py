import pytest
from run_synthetic import wilson


def test_wilson_extremes_and_symmetry():
    lower, upper = wilson(0, 16)
    assert lower == pytest.approx(0, abs=1e-15)
    assert upper == pytest.approx(0.1936076805344365)
    opposite = wilson(16, 16)
    assert opposite == pytest.approx([1 - upper, 1 - lower])
    assert sum(wilson(8, 16)) == pytest.approx(1)
