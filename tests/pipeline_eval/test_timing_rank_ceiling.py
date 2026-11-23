from fractions import Fraction

import numpy as np

from reports.ALGO08.v3.timing_rank_ceiling import energy_envelope, exact_powers, mantissa_units


def test_binary32_power_is_exact_even_for_subnormal_and_signed_zero_parts():
    tiny = np.float32(np.ldexp(1.0, -149))
    bank = np.array([[complex(-3., 4.), complex(-0., tiny), complex(-tiny, tiny)]], dtype=np.complex64)
    assert exact_powers(bank) == [[25 * (1 << 298), 1, 2]]
    assert mantissa_units(0x80000000) == 0


def test_full_circulant_flat_spectrum_has_exact_linear_energy_ceiling():
    trace, ceiling, lower_rank = energy_envelope([[4] * 12], 8, [12])
    assert lower_rank == 8
    assert [Fraction(v, trace) for v in ceiling] == [Fraction(r, 8) for r in range(9)]


def test_cropped_multilag_envelope_dominates_optimal_capture_on_small_exact_example():
    bin_count, epochs = 12, 8
    widths = (9, 11)
    rng = np.random.default_rng(822)
    data = rng.integers(-4, 5, size=(2, bin_count, 2)).astype(np.float32)
    stored = (data[..., 0] + 1j * data[..., 1]).astype(np.complex64)
    trace, ceiling, lower_rank = energy_envelope(exact_powers(stored), epochs, widths)
    columns = np.fft.fft(np.eye(bin_count), axis=0)
    parts = [np.fft.ifft(columns * row[:, None], axis=0)[:epochs, :width]
             for row, width in zip(stored, widths, strict=True)]
    finite = np.concatenate(parts, axis=1)
    values = np.maximum(np.linalg.eigvalsh(finite @ finite.conj().T), 0.)[::-1]
    attained = np.r_[0., np.cumsum(values) / values.sum()]
    assert all(float(Fraction(bound, trace)) >= actual - 1e-12
               for bound, actual in zip(ceiling, attained, strict=True))
    assert lower_rank <= np.count_nonzero(values > 1e-12)
