import numpy as np
import pytest

from reports.ALGO08.v3.fractional_reject_ceiling import ledger, prefix_bounds, summarize


def test_frame_prefix_bounds_hold_for_all_original_frequency_bins():
    rng = np.random.default_rng(33)
    for _ in range(8):
        exact, rolled = rng.normal(size=(2, 8, 64)) + 1j*rng.normal(size=(2, 8, 64))

        def summaries(rows):
            scores = (abs(np.fft.fft(rows, 512, axis=1)) ** 2).cumsum(axis=0).max(axis=1)
            norm = (abs(rows).sum(axis=1) ** 2).cumsum()
            return scores, norm

        e, ed = summaries(exact)
        r, rd = summaries(rolled)
        for n in range(8):
            upper, lower = prefix_bounds(e[n], ed[n], ed[-1]-ed[n], r[n], rd[n], rd[-1]-rd[n])
            assert upper >= e[-1]/ed[-1]-1e-15
            assert lower <= r[-1]/rd[-1]+1e-15


def test_zero_rolled_witness_and_authentic_zero_rejection():
    assert prefix_bounds(0, 0, 0, 0, 0, 100) == (0, 0)
    with pytest.raises(ValueError):
        prefix_bounds(2, 1, 0, 0, 0, 0)
    groups = ledger("scout-readout.json.gz")["groups"]
    weak, dense = (summarize(groups[name]["rows"]) for name in ("weak", "dense"))
    assert (weak["fractional"], dense["fractional"]) == (58, 80)
    assert weak["generous_oracle_cpu_ns"] == dense["generous_oracle_cpu_ns"] == 0
