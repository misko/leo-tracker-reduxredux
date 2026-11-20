import numpy as np

from leo.analysis.starlink import acquisition
from tools.pipeline_eval.variants import anchor_grid, capture_batched_fft, capture_fft


def test_batched_inverses_preserve_support_and_normalization_against_double_grid(tmp_path):
    batch, _ = capture_batched_fft.build(tmp_path)
    double = capture_fft.build(tmp_path / "double.so")
    baseline, candidate = (capture_fft.FullGrid(lib) for lib in (double, batch))
    rng = np.random.default_rng(123)
    n, rate, epochs = 13_709, 2_500_000.0, 3333
    ref = (rng.integers(-20, 20, epochs) + 1j * rng.integers(-20, 20, epochs)) / 20
    samples = rng.integers(-300, 300, n) + 1j * rng.integers(-300, 300, n)
    frequencies, symbols = (-500_000, -120_000, 0, 200_000, 620_000), (2, 28, 80, 180, 288)

    def fail(*unused):
        raise AssertionError("the held fixture must exercise the compiled grid")

    for s in (samples, np.zeros_like(samples)):
        a, b = [
            np.asarray(x.score_grid(acquisition, fail, s, ref, rate, frequencies, symbols, epochs))
            for x in (baseline, candidate)
        ]
        assert a.shape == b.shape == (5, 3333)
        assert baseline.calls[-1]["inverse_ffts"] == candidate.calls[-1]["inverse_ffts"]
        assert np.max(np.abs(a - b)) < 1e-6
        if not np.any(s):
            assert np.count_nonzero(b) == 0


def test_vector_selection_keeps_installed_ties_and_circular_suppression():
    rng = np.random.default_rng(47628)
    frequencies = (-300.0, -50.0, 50.0, 300.0)
    for width in (1, 3, 19, 135):
        for _ in range(12):
            scores = tuple(rng.integers(0, 4, (4, width)).astype(float))
            params = (frequencies, scores, 8, 4, 110.0, width)
            assert anchor_grid.retained_peaks(*params) == acquisition._retain_score_map_peaks(
                *params
            )
