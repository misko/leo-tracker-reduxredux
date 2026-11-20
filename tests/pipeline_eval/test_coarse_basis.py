"""Verify the shared correlation arithmetic independently of archived IQ."""

from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification.coarse_basis_results import BANKS, figure_rows
from tools.pipeline_eval.variants import (
    coarse_basis,
    coarse_basis_integer,
    coarse_basis_shift,
    original_kernel,
)


def test_stage_table_exports_both_panels_and_excludes_synthetic_detector_rows():
    grids = [
        dict(mode=bank, anchors=anchors, cpu_ms=ms)
        for bank, _ in BANKS
        for anchors in (12, 22)
        for ms in (2, 4)
    ]
    detector = dict(mode="prepared", case="recorded", label="43", cpu_ms=12, coarse_cpu_ms=4)
    rows = figure_rows(grids, [dict(detector, kind=k) for k in ("radio", "synthetic")])
    assert len(rows) == 14
    assert {r["median_ms"] for r in rows if r["panel"] == "development"} == {3}
    assert [(r["metric"], r["median_ms"]) for r in rows if r["panel"] == "held"] == [
        ("full_detector_cpu", 12),
        ("coarse_cpu", 4),
    ]


def _waveform_fixture():
    rng = np.random.default_rng(733)

    def noise(n):
        return rng.integers(-128, 128, n) + 1j * rng.integers(-128, 128, n)

    wave = noise(2531)
    template = noise(256)
    starts, epochs = (44, 132, 176), 911
    frames = np.array([0, 1000, 2000])
    rate = 10_000_000
    bins = 31_255.0 + 80_000 * np.arange(-10, 11)
    prefix = np.r_[0, np.cumsum(wave.real**2 + wave.imag**2)]
    bank = coarse_basis.filters(template, starts, 44, bins, rate)
    expected = np.zeros((len(bins), epochs))
    support = np.zeros(epochs)
    windows = np.lib.stride_tricks.sliding_window_view(wave, 44)
    norm = np.linalg.norm(windows, axis=1)
    for symbols, coefficients in zip(starts, bank, strict=True):
        dots = coefficients @ windows.T
        for frame in frames:
            first = frame + symbols
            count = max(0, min(epochs, windows.shape[0] - first))
            expected[:, :count] += abs(dots[:, first : first + count]) / norm[first : first + count]
            support[:count] += 1
    expected /= support
    return wave, template, starts, epochs, frames, rate, bins, prefix, bank, expected


def test_projection_preserves_full_rank_and_partial_frame(tmp_path):
    wave, _, starts, epochs, frames, _, _, prefix, bank, expected = _waveform_fixture()
    library = tmp_path / "projection.so"
    coarse_basis.compile_projection(library)
    scorer = coarse_basis.Projection(library, bank, 44, starts, frames, epochs)
    values, cost = scorer.score(wave, prefix)
    np.testing.assert_allclose(values, expected, atol=2e-7, rtol=0)
    assert cost["inverse_ffts"] == 44 * cost["forward_ffts"]


@pytest.mark.hardware
def test_quantized_complex_reconstruction_with_clipped_frame(tmp_path):
    wave, _, starts, epochs, frames, _, _, prefix, bank, _ = _waveform_fixture()
    floating = tmp_path / "projection.so"
    integer = tmp_path / "integer.so"
    coarse_basis.compile_projection(floating)
    coarse_basis_integer.build(integer)
    source = coarse_basis.Projection(floating, bank, 20, starts, frames, epochs)
    approximate = coarse_basis_integer.QuantizedReconstruction(integer, source)
    expected, _ = source.score(wave, prefix)
    actual, receipt = approximate.score(wave, prefix)
    assert receipt["response_reconstruction_clipped_tiles"] == 0
    np.testing.assert_allclose(actual, expected, atol=0.004, rtol=0)


def test_shifted_spectra_keep_signed_lanes_with_asymmetric_filters(tmp_path):
    wave, template, _, _, _, rate, bins, _, _, expected = _waveform_fixture()
    libraries = [coarse_basis_shift.build(tmp_path / str(n), n)[0] for n in (250, 500, 1000)]
    acquisition = SimpleNamespace(
        OFDM_SYMBOL_DURATION_S=44 / rate,
        FRAME_RATE_HZ=rate / 1000,
        _power_prefix=lambda wave: np.r_[0, np.cumsum(wave.real**2 + wave.imag**2)],
    )
    scorers = [original_kernel.PersistentGrid(path) for path in libraries]

    def unsupported(*args):
        return np.full_like(expected, float("nan"))

    def score(grid, absolute):
        return grid.score_grid(
            acquisition, unsupported, wave, template, rate, absolute, (1, 3, 4), 911
        )

    try:
        for grid in scorers:
            np.testing.assert_allclose(score(grid, bins), expected, atol=2e-7, rtol=0)
            assert grid.calls[-1]["filter_ffts"] == 3
            np.testing.assert_allclose(score(grid, bins), expected, atol=2e-7, rtol=0)
            assert grid.calls[-1]["filter_ffts"] == 0
            irregular = bins.copy()
            irregular[-1] -= 1
            assert np.isnan(score(grid, irregular)).all()
            assert not grid.calls[-1]["applied"]
    finally:
        for grid in scorers:
            grid.clear_cache()
