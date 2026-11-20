import numpy as np

from leo.analysis.starlink import acquisition
from tools.pipeline_eval.qualification.original_kernel_trial import rank_gap
from tools.pipeline_eval.variants import capture_batched_fft, capture_fft, original_kernel


def test_prepared_cache_key_reuse_and_mixed_waveforms(tmp_path):
    before = tmp_path / "before"
    before.mkdir()
    old, _ = capture_batched_fft.build(before)
    new, _ = original_kernel.build(tmp_path)
    baseline, trial = capture_fft.FullGrid(old), original_kernel.PersistentGrid(new)
    rng = np.random.default_rng(75830)

    def values(n):
        return rng.integers(-300, 300, n) + 1j * rng.integers(-300, 300, n)

    x, y, ref = values(13_197), values(13_197), values(3333) / 300
    alternate = ref.copy()
    alternate[22] += 1j
    frequencies = (-600_000, 0, 80_000, 700_000)
    symbols = (2, 14, 28, 76)

    def unsupported(*_args):
        raise AssertionError("test must use the compiled prepared body")

    def grid(kernel, signal, template, bins):
        return np.asarray(
            kernel.score_grid(
                acquisition, unsupported, signal, template, 2_500_000.0, bins, symbols, 3333
            )
        )

    try:
        first = grid(trial, x, ref, frequencies)
        assert trial.calls[-1]["filter_ffts"] == len(frequencies) * len(symbols)
        second = grid(trial, y, ref.copy(), frequencies)
        assert trial.calls[-1]["filter_ffts"] == 0
        assert not np.array_equal(first, second)
        np.testing.assert_allclose(second, grid(baseline, y, ref, frequencies), atol=3e-15, rtol=0)
        grid(trial, y, alternate, frequencies)
        assert trial.calls[-1]["filter_ffts"] > 0
        grid(trial, y, alternate, frequencies[::-1])
        assert trial.calls[-1]["filter_ffts"] > 0
        zero = grid(trial, np.zeros_like(x), ref, frequencies)
        assert not np.any(zero)
        assert trial.calls[-1]["filter_ffts"] == 0
        trial.clear_cache()
        grid(trial, x, ref, frequencies)
        assert trial.calls[-1]["filter_ffts"] > 0
    finally:
        trial.clear_cache()


def test_rank_gap_retains_an_actual_tied_cfo_and_wrap():
    rows = np.array([[0.5, 0.1, 0.2, 0.5], [0.5, 0.1, 0.1, 0.25]])
    assert rank_gap(rows, np.array([-80_000, 80_000]), 2, 2, 180_000)[0] == 0
    assert rank_gap(np.zeros_like(rows), np.array([-80_000, 80_000]), 2, 2, 180_000) == []
