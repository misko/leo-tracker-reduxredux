import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental.receiver_cfo_peak_bound import (
    SPECTRUM,
    SUPPORT,
    Epoch,
    audit_scout,
    peak_upper,
    ranked,
    timing_order,
)


@pytest.mark.parametrize("step", [2, 4])
def test_subsampled_fft_bounds_both_modes_with_off_grid_peaks(step):
    rng = np.random.default_rng(806)
    coordinates = np.arange(SUPPORT)
    noise = rng.normal(size=(2, SUPPORT)) + 1j * rng.normal(size=(2, SUPPORT))
    tone = np.exp(2j * np.pi * 4094.5 * coordinates / SPECTRUM)
    for data in (noise, noise * 0.001 + tone, np.vstack([noise[0], 0 * noise[1]])):
        exact = np.sum(abs(np.fft.fft(data, n=SPECTRUM, axis=1)) ** 2, axis=0)
        pilot_fft = np.fft.fft(data, n=SPECTRUM // step, axis=1)
        np.testing.assert_allclose(exact[::step], np.sum(abs(pilot_fft) ** 2, axis=0))
        assert peak_upper(max(exact[::step]), step) >= max(exact)


def test_pruning_keeps_tied_and_hidden_seeds_with_strict_order():
    def epoch(i, first, second, anchor):
        return Epoch(i, (anchor, anchor), first, ((20 + i, first), (800 + i, second)))

    rows = [epoch(4, 6, 4, 6), epoch(1, 5, 3, 5), epoch(9, 7, 4, 6), epoch(3, 1, 0, 1)]
    assert [row[:2] for row in ranked(rows, [2, 1, 0])] == [(2, 0), (0, 0), (1, 0), (0, 1)]
    stats = audit_scout(rows, 2, [2, 1, 3, 0], initial=0)
    assert stats["full"] == 3
    rows[0] = epoch(4, 6, 4, 0)
    stats = audit_scout(rows, 2, [2, 1, 3, 0], initial=0)
    assert stats["bounds_failed"] == 1
    assert stats["full"] == 3


def test_raw_hints_wrap_and_only_reorder_residual_epochs():
    def epoch(i, power):
        return Epoch(i, (power, power), power, ((1, power),))

    raw = [epoch(0, 10), epoch(40, 4)]
    residual = [epoch(20, 3), epoch(39, 4), epoch(3331, 10), epoch(5, 8)]
    assert timing_order(residual, raw) == [2, 1, 0, 3]
    assert timing_order(residual, None) == [0, 1, 2, 3]
    assert audit_scout(residual, 2, timing_order(residual, raw), initial=2)["full"] == 4


def test_exact_cutline_tie_requires_the_full_epoch():
    rows = [Epoch(i, (0, 0), 0, ((0, 0), (17, 0))) for i in range(12)]
    assert audit_scout(rows, 4, list(range(len(rows))), initial=2)["full"] == len(rows)
