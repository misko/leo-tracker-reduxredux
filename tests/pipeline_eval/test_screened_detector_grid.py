"""Quantized statistic across native tile widths and partial final frames."""

import numpy as np
import pytest

from tools.pipeline_eval.variants import screened_detector_grid


def scalar(values, template, frequencies, starts, stops, offsets, prefix, rate, epochs):
    sums = np.zeros((len(frequencies), epochs))
    support = np.zeros(epochs)
    xmax = max(np.abs(values.real).max(), np.abs(values.imag).max())
    used = np.concatenate([template[a:b] for a, b in zip(starts, stops, strict=True)])
    rmax = max(np.abs(used.real).max(), np.abs(used.imag).max())
    qmax = min(32767, np.floor((2**31 - 1) / (2 * (stops - starts).max() * xmax))) - 1
    scale = qmax / (2 * rmax)
    for first, last in zip(starts, stops, strict=True):
        taps = last - first
        reference = template[first:last]
        bank = reference * np.exp(2j * np.pi * frequencies[:, None] * np.arange(taps) / rate)
        qr = np.rint(bank.real * scale).astype(np.int64)
        qi = np.rint(bank.imag * scale).astype(np.int64)
        for offset in offsets:
            for epoch in range(epochs):
                sample = first + offset + epoch
                if sample + taps > len(values):
                    continue
                part = values[sample : sample + taps]
                x, y = part.real.astype(np.int64), part.imag.astype(np.int64)
                r = (qr @ x + qi @ y) / scale
                i = (qr @ y - qi @ x) / scale
                energy = prefix[sample + taps] - prefix[sample]
                denom = np.sqrt(energy * np.sum(reference.real**2 + reference.imag**2))
                if denom:
                    sums[:, epoch] += np.sqrt(r * r + i * i) / denom
                support[epoch] += 1
    return np.divide(sums, support, where=support > 0, out=np.zeros_like(sums))


@pytest.mark.hardware
def test_quantized_grid_matches_scalar(tmp_path):
    """Requires an x86-64 host advertising AVX-VNNI and an available compiler."""
    kernel = screened_detector_grid.Grid(screened_detector_grid.build(tmp_path / "screened.so"))
    rng = np.random.default_rng(18032)
    values = rng.integers(-2000, 2000, size=125) + 1j * rng.integers(-2000, 2000, size=125)
    reference = rng.normal(size=30) + 1j * rng.normal(size=30)
    starts, stops, offsets = (np.array(a, dtype=np.intp) for a in ((3, 14), (10, 23), (0, 41, 111)))
    prefix = np.r_[0.0, np.cumsum(values.real**2 + values.imag**2)]
    for count in (1, 8, 9, 16, 17, 21, 24):
        frequencies = np.linspace(-770000.0, 768000.0, count)
        args = (values, reference, frequencies, starts, stops, offsets, prefix, 10_000_000, 19)
        got = kernel._tile(*args)
        np.testing.assert_allclose(got, scalar(*args), atol=2e-16, rtol=2e-16)

    # Signed-IQ overflow geometry belongs to the original installed fallback.
    assert kernel._tile(values * 32768, *args[1:]) is None
