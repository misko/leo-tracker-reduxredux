"""Shared-anchor cache parity across ties and physical probe boundaries."""

from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import original_kernel, retry_reuse


def test_retry_matches_prepared_on_a_carrier_tie_and_rejects_a_crossed_lane(tmp_path):
    sample = np.zeros(retry_reuse.SAMPLES, dtype=np.complex128)
    sample[127::635] = 120 - 23j
    template = np.zeros(13_333, dtype=np.complex128)
    anchors = set(retry_reuse.PRIMARY) | set(retry_reuse.RETRY)
    template[np.array(sorted(anchors)) * 44] = 1
    frequencies = tuple(80_000.0 * k for k in range(-10, 11))
    acquisition = SimpleNamespace(
        OFDM_SYMBOL_DURATION_S=4.4e-6,
        FRAME_RATE_HZ=750.0,
        _power_prefix=lambda x: np.r_[0, np.cumsum(x.real**2 + x.imag**2)],
    )

    def unexpected(*args):
        raise AssertionError("the native grid unexpectedly declined this support")

    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    control = original_kernel.PersistentGrid(original_kernel.build(baseline_dir)[0])
    result = retry_reuse.Grid(retry_reuse.build(tmp_path / "candidate")[0])

    def score(grid, symbols, received=sample):
        return np.asarray(
            grid.score_grid(
                acquisition,
                unexpected,
                received,
                template,
                10_000_000,
                frequencies,
                symbols,
                13_333,
            )
        )

    try:
        key = (0, 3, "upper")
        result._active = "capture", key
        primary = score(result, retry_reuse.PRIMARY)
        np.testing.assert_array_equal(primary, score(control, retry_reuse.PRIMARY))
        result._prepared = result._last_capture
        assert result._prepared is not None
        result._active = "retry", key
        wider = score(result, retry_reuse.RETRY, sample.copy())
        expected = score(control, retry_reuse.RETRY)
        np.testing.assert_array_equal(wider, expected)
        np.testing.assert_array_equal(wider, np.broadcast_to(wider[0], wider.shape))
        assert result.calls[-1]["cache_mode"] == 2
        assert result.calls[-1]["inverse_ffts"] < control.calls[-1]["inverse_ffts"]

        result._active = "retry", (1, 3, "upper")
        np.testing.assert_array_equal(score(result, retry_reuse.RETRY), expected)
        assert result.calls[-1]["cache_mode"] == 0
        assert result.calls[-1]["inverse_ffts"] == control.calls[-1]["inverse_ffts"]
        assert result.storage_bytes == 33_600_000
    finally:
        for grid in (control, result):
            grid.clear_cache()


def test_retry_identity_uses_exact_bytes():
    sample = np.array([0.0 + 0.0j, 1.0 - 2.0j])
    assert retry_reuse.equal_arrays(sample, sample.copy())
    copy = sample.copy()
    copy.real[0] = -0.0
    assert np.array_equal(sample, copy)
    assert not retry_reuse.equal_arrays(sample, copy)
