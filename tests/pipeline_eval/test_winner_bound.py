import numpy as np
import pytest

from tools.pipeline_eval.qualification.winner_bound_spectrum import SIZE, component
from tools.pipeline_eval.variants import winner_bound as bound


def test_nonnegative_mean_and_fixed_bin_control_bounds_cover_full_fft():
    rng = np.random.default_rng(17)
    grid = np.fft.fftfreq(SIZE)
    exact = rng.normal(size=(4, 64)) + 1j * rng.normal(size=(4, 64))
    control = rng.normal(size=(4, 64)) + 1j * rng.normal(size=(4, 64))
    score = component(exact, grid)[0]
    true_margin = score - component(control, grid)[0]
    ceiling, mean, subset = bound.margin_bounds(score, control)
    assert true_margin <= subset <= mean <= ceiling
    assert ceiling == score
    assert bound.margin_bounds(score, np.zeros_like(control)) == (score, score, score)


@pytest.mark.parametrize("offset", (-1.4, -0.3, 0.0, 0.35, 1.4))
def test_integer_energy_bound_encloses_lanczos_shifted_complex_correlation(offset):
    rng = np.random.default_rng(712)
    template = rng.normal(size=(64, 44)) + 1j * rng.normal(size=(64, 44))
    values = rng.normal(size=(3, 64, 78)) + 1j * rng.normal(size=(3, 64, 78))
    shift = round(offset)
    operator_freq = -305_600.0
    grid = np.fft.fftfreq(SIZE)
    axes = np.arange(44)
    nearest_start = 15 + shift
    base = int(np.floor(offset))
    disp = base + bound.LANCZOS
    delta = offset - disp
    factors = np.sinc(delta) * np.sinc(delta / 8)
    factors /= factors.sum()
    rotated = values * np.exp(
        -2j * np.pi * operator_freq * np.arange(values.shape[-1]) / bound.RATE
    )
    integer = np.sum(rotated[..., nearest_start + axes] * template.conj(), axis=-1)
    interp = values[..., 15 + axes[:, None] + disp] @ factors
    carrier = np.exp(-2j * np.pi * operator_freq * (15 + axes + offset) / bound.RATE)
    fractional = np.sum(interp * carrier * template.conj(), axis=-1)
    first, stop, coefficient = bound.perturbation(template, offset, operator_freq)
    energy = np.linalg.norm(values[..., nearest_start + first : nearest_start + stop], axis=-1)
    envelope = bound.integer_envelope(integer, component(integer, grid)[0], coefficient, energy)
    assert np.all(np.abs(fractional - integer) <= energy * coefficient + 1e-10)
    assert component(fractional, grid)[0] <= envelope + 1e-10


def test_certificates_keep_gate_existence_and_ties():
    assert not bound.can_skip(0.0, None)
    assert not bound.can_skip(0.0, 0.024)
    assert not bound.can_skip(0.08, 0.08)
    assert not bound.can_skip(0.08 - bound.ROUNDING_ALLOWANCE / 2, 0.08)
    assert bound.can_skip(0.021, 0.025)
