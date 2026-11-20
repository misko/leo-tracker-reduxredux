"""Check analytic complex interpolation and the sufficient selection condition."""

from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import coarse_cfo, original_kernel, prepared_hotpath_peaks


def test_normalized_filter_defect_dominates_complex_projection_error():
    rng = np.random.default_rng(711320)
    refs = rng.normal(size=(7, 44)) + 1j * rng.normal(size=(7, 44))
    signal = rng.normal(size=(200, 44)) + 1j * rng.normal(size=(200, 44))
    signal /= np.linalg.norm(signal, axis=1, keepdims=True)
    centered = np.arange(44) - 21.5
    phases = np.exp(-2j * np.pi * 0.008 * np.arange(21)[:, None] * centered)
    refs /= np.linalg.norm(refs, axis=1, keepdims=True)
    for terms in coarse_cfo.ORDERS:
        model, defects = coarse_cfo.weights(refs, terms)
        for row, neighbors in enumerate(coarse_cfo.neighbors(terms)):
            available = phases[coarse_cfo.KEEP[neighbors]]
            full = phases[coarse_cfo.ODD[row]]
            residual = (model[:, row] @ available - full) * refs.conj()
            actual = abs(signal @ residual.T)
            assert np.all(actual <= defects[:, row] + 1e-14)


def test_unknown_tied_candidate_cannot_certify_across_row_suppression():
    values = np.zeros((3, 9))
    values[0, 2], values[1, 2], values[2, 6] = 0.9, 0.85, 0.8
    rank = prepared_hotpath_peaks.retained_peaks
    residuals = (-80_000.0, 0.0, 80_000.0)
    chosen = rank(residuals, values, 2, 3, 90_000, 9)
    assert [entry[1:] for entry in chosen] == [(2, -80_000.0), (6, 80_000.0)]
    seen = np.ones_like(values, dtype=bool)
    seen[0, -1] = False
    exact = np.where(seen, values, np.nan)
    bounds = np.zeros_like(values)
    bounds[0, -1] = chosen[-1][0]
    assert not coarse_cfo.exact_selection(values, exact, seen, bounds, chosen)
    bounds[0, -1] = np.nextafter(bounds[0, -1], 0)
    assert coarse_cfo.exact_selection(values, exact, seen, bounds, chosen)
    assert coarse_cfo.exact_selection(values, values, np.ones_like(seen), bounds, chosen)


def test_native_reconstruction_applies_bounds_and_rescores_with_all_44_taps(tmp_path):
    rate, epochs = coarse_cfo.RATE, 13_333
    acquisition = SimpleNamespace(
        OFDM_SYMBOL_DURATION_S=4.4e-6,
        FRAME_RATE_HZ=750,
        _power_prefix=lambda x: np.r_[0, np.cumsum(x.real**2 + x.imag**2)],
    )
    rng = np.random.default_rng(521)
    waveform = rng.integers(-100, 100, size=(2, 200_000))
    received = waveform[0] + 1j * waveform[1]
    taps = rng.normal(size=(2, epochs))
    template = taps[0] + 1j * taps[1]
    frequencies = tuple(1337 + 80_000 * i for i in range(-10, 11))
    layout = tuple(range(2, 302, 26))
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    exact = original_kernel.PersistentGrid(original_kernel.build(baseline)[0])
    model = coarse_cfo.Interpolated(
        coarse_cfo.build(tmp_path / "projected", 6)[0], 6, exact, repair="shortlist"
    )

    def unsupported(*_):
        raise AssertionError("the native geometry was not scored")

    try:
        args = (acquisition, unsupported, received, template, rate, frequencies, layout, epochs)
        left = np.asarray(exact.score_grid(*args))
        rows = model.score_grid(*args)
        approximation = np.asarray(rows)
        bound = model._inputs()[-1]
        assert np.all(abs(approximation - left) <= bound + coarse_cfo.NUMERICAL_SLACK)
        rank = (frequencies, rows, 8, 5, 10_000, epochs)
        model.restore(rank, approximation, prepared_hotpath_peaks.retained_peaks)
        repaired = np.asarray(rows)
        visited = np.isfinite(repaired)
        assert 0 < visited.sum() < left.size
        np.testing.assert_allclose(repaired[visited], left[visited], atol=1e-7, rtol=0)
    finally:
        for grid in (exact, model):
            grid.clear_cache()
