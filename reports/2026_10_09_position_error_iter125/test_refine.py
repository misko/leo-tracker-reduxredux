import numpy as np
import pytest
from refine import DELTA_HZ, evaluate, polynomial, refine


@pytest.mark.parametrize("phase", [-0.4, 0.2, 255.8, -255.8])
def test_pure_correlation_peak_and_seam(phase):
    z = np.exp(2j * np.pi * phase * np.arange(64) / 512)[None, :]
    result = refine(z)

    def difference(x):
        return ((x / DELTA_HZ - phase + 256) % 512) - 256

    assert abs(difference(result["newton_hz"])) < 1e-7
    assert abs(difference(result["logparabola_hz"])) < 0.002
    assert result["newton_score"] >= result["coarse_score"]


def test_flat_noop_and_no_extra_peak_search():
    result = refine(np.zeros((2, 64), complex))
    assert result["coarse_hz"] == result["newton_hz"] == result["logparabola_hz"] == 0
    assert result["newton_steps"] == 0
    with pytest.raises(ValueError, match="winner mismatch"):
        refine(np.zeros((2, 64), complex), native_bin=1)


def test_exact_derivatives_and_amplitude_invariance():
    rng = np.random.default_rng(125)
    z = rng.normal(size=(3, 64)) + 1j * rng.normal(size=(3, 64))
    coefficients, spectrum, _ = polynomial(z)
    h = 0.001
    v, g, hess = evaluate(coefficients, 13.2)
    left, right = evaluate(coefficients, 13.2 - h), evaluate(coefficients, 13.2 + h)
    assert (right[0] - left[0]) / (2 * h) == pytest.approx(g, abs=1e-9, rel=0)
    assert (right[1] - left[1]) / (2 * h) == pytest.approx(hess, abs=1e-9, rel=0)
    np.testing.assert_allclose(polynomial(z * 0.01)[1], spectrum, atol=1e-14, rtol=0)
    assert np.isfinite(v)
