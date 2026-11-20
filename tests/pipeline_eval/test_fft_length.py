"""Compare overlap-save support and exact tied lanes over alternate block lengths."""

from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants import fft_length, fft_length_plan, original_kernel


def _geometry():
    rate = 9_875_000
    duration = 4.4e-6
    frames = 259
    acquisition = SimpleNamespace(
        OFDM_SYMBOL_DURATION_S=duration,
        FRAME_RATE_HZ=rate / frames,
        _power_prefix=lambda wave: np.r_[0, np.cumsum(wave.real**2 + wave.imag**2)],
    )
    rng = np.random.default_rng(6162)

    def waveform(n):
        return rng.integers(-113, 113, n) + 1j * rng.integers(-113, 113, n)

    return acquisition, rate, frames, waveform(1345), waveform(400), (2, 3, 5, 8)


def _oracle(wave, template, rate, frames, starts, stops, frequencies, epochs):
    result = np.zeros((len(frequencies), epochs))
    support = np.zeros(epochs, dtype=int)
    for first, stop in zip(starts, stops, strict=True):
        taps = stop - first
        windows = np.lib.stride_tricks.sliding_window_view(wave, taps)
        reference = template[first:stop]
        coefficients = reference.conj() * np.exp(
            -2j * np.pi / rate * np.outer(frequencies, np.arange(taps))
        )
        dots = abs(coefficients @ windows.T)
        norm = np.linalg.norm(windows, axis=1) * np.linalg.norm(reference)
        for offset in range(first, len(wave), frames):
            size = min(epochs, len(windows) - offset)
            if size > 0:
                x = slice(offset, offset + size)
                result[:, :size] += np.divide(
                    dots[:, x], norm[x], out=np.zeros_like(dots[:, x]), where=norm[x] != 0
                )
                support[:size] += 1
    return result / support


def test_all_overlap_save_lengths_preserve_mixed_tap_and_partial_frame_support(tmp_path):
    acq, rate, frames, wave, template, symbols = _geometry()
    frequencies = (13_211.0, -494_000.0, 601_000.0)
    starts = [round(s * rate * acq.OFDM_SYMBOL_DURATION_S) for s in symbols]
    stops = [round((s + 1) * rate * acq.OFDM_SYMBOL_DURATION_S) for s in symbols]
    measured = _oracle(wave, template, rate, frames, starts, stops, frequencies, 259)
    assert set(np.subtract(stops, starts)) == {43, 44}

    def unavailable(*_):
        pytest.fail("complete supported grid fell back to installed scoring")

    for length in fft_length.LENGTHS:
        result = original_kernel.PersistentGrid(fft_length.build(tmp_path / str(length), length)[0])
        try:
            values = result.score_grid(
                acq, unavailable, wave, template, rate, frequencies, symbols, 259
            )
            np.testing.assert_allclose(values, measured, atol=1.8e-7, rtol=0)
            assert result.calls[-1]["fft_length"] == length
            assert result.calls[-1]["filter_ffts"] == len(symbols) * len(frequencies)
            result.score_grid(acq, unavailable, wave, template, rate, frequencies, symbols, 259)
            assert result.calls[-1]["filter_ffts"] == 0
        finally:
            result.clear_cache()


def test_stored_measured_plan_keeps_exactly_tied_cfo_rows(tmp_path):
    acq, rate, _frames, wave, template, symbols = _geometry()
    template[:] = 0
    for symbol in symbols:
        template[round(symbol * rate * acq.OFDM_SYMBOL_DURATION_S)] = 1
    base = tmp_path / "estimate"
    original = fft_length.build(base, 256)[0]
    learned = fft_length_plan.build(tmp_path / "measured", base, fft_length_plan.measure(256))[0]

    def unavailable(*_):
        pytest.fail("stored complete bank failed to use its plan")

    frequencies = tuple(80_000.0 * f for f in range(-10, 11))
    rows = []
    for path in (original, learned):
        grid = original_kernel.PersistentGrid(path)
        try:
            value = np.asarray(
                grid.score_grid(
                    acq,
                    unavailable,
                    wave,
                    template,
                    rate,
                    frequencies,
                    symbols,
                    259,
                )
            )
            np.testing.assert_array_equal(value, np.broadcast_to(value[0], value.shape))
            rows.append(value)
        finally:
            grid.clear_cache()
    np.testing.assert_allclose(rows[0], rows[1], atol=1.8e-7, rtol=0)
