from pathlib import Path

import numpy as np
import pytest

from tools.pipeline_eval.qualification import differential_pilot_eval, multilag_search_eval
from tools.pipeline_eval.variants import differential_pilot as dp
from tools.pipeline_eval.variants import multilag_search as multi


@pytest.mark.parametrize("signed_hz", (-688_125, 688_125))
def test_a_common_signed_carrier_fits_all_three_pilot_phase_products(signed_hz):
    phase = 2 * np.pi * signed_hz * np.asarray(multi.LAGS) / dp.RATE
    value = np.zeros((2, 3, 2, 2), dtype=np.complex128)
    value[:, :, 0, 0] = np.exp(1j * phase)
    value[:, :, 0, 1] = np.exp(1j * phase) * [1, -1, 1]
    ranked = multi.score(value)
    assert np.allclose(ranked[:, 0], 3)
    assert np.allclose(ranked[:, 1], 2.25)
    value[:, :, 1, :] = value[:, :, 0, :]
    assert np.all(multi.score(value) <= 1e-12)


def test_lag_one_has_the_released_template_energy_and_phase_rows():
    actual, energy = multi.product_filter("upper", 0, 44)
    reference, allowed = dp.filters("upper")[0]
    np.testing.assert_array_equal(actual, reference)
    np.testing.assert_array_equal(energy, allowed)


def direct(sample, edge, lag, epoch, roll):
    x = sample[:, 0, 0].astype(float) + 1j * sample[:, 0, 1].astype(float)
    data = x[lag:] * x[:-lag].conj()
    data -= data.mean()
    code, power = multi.product_filter(edge, roll, lag)
    kernel = np.fft.ifft(code.conj(), axis=-1)[:, : dp.FRAME]
    accum = 0j
    for residue, start in dp.STARTS:
        lo = max(0, -start - epoch)
        hi = min(dp.FRAME, data.size - start - epoch)
        if hi > lo:
            accum += np.vdot(kernel[residue, lo:hi], data[start + epoch + lo : start + epoch + hi])
    return accum / np.sqrt(float(np.vdot(data, data).real) * power[epoch])


@pytest.mark.hardware
def test_actual_fftw_port_matches_direct_complex_matched_code_at_edges(tmp_path):
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL

    built = multilag_search_eval.build(tmp_path)
    with multi.MultilagScout(Path(built["path"]), "upper") as scout:
        sample, plant = differential_pilot_eval.synthetic("upper", "strong")
        scout.surface(sample)
        for li, lag in enumerate(multi.LAGS):
            for ci, roll in enumerate((0, CONTROL_SYMBOL_ROLL)):
                for epoch in (0, plant["epoch"], 13_332):
                    value = direct(sample, "upper", lag, epoch, roll)
                    assert abs(value - scout.response[0, li, ci, epoch]) <= 3e-6
        absent = scout.surface(np.zeros_like(sample))
        assert not np.count_nonzero(absent)
        assert scout(np.zeros_like(sample), "upper") == [([], []), ([], [])]
