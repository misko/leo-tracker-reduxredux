from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def track(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(path))
    return import_module("track_before_detect")


def test_sampling_keeps_signed_band_and_preserves_equal_null(track):
    surface = (-track.BIN_HZ, track.BIN_HZ, np.array([9., 6., 0.]), 0.)
    np.testing.assert_allclose(track.frequency_scores(surface, [-track.BIN_HZ / 2, track.BIN_HZ / 2]), [7.5, 3.])
    with pytest.raises(ValueError, match="signed interval"):
        track.frequency_scores(surface, [2 * track.BIN_HZ])
    np.testing.assert_array_equal(track.standardized(np.zeros(8)), np.zeros(8))
    huge = np.array([0., 1e25, 2e25], dtype=np.float32)
    np.testing.assert_allclose(track.standardized(huge), [-np.sqrt(1.5), 0., np.sqrt(1.5)])


def test_multiple_visits_accumulate_without_peak_thresholds(track):
    offsets = np.arange(-5, 6) * 10000
    weak = np.zeros((6, len(offsets)))
    weak[:, offsets == 0] = 2
    for i, shift in enumerate((-50000, -40000, -30000, 30000, 40000, 50000)):
        weak[i, offsets == shift] = 5
    assert all(track.ranks(offsets, row[None, :])["exact_rank"] == 2 for row in weak)
    combined = track.ranks(offsets, weak)
    assert combined["exact_rank"] == 1
    assert combined["top4_in_band"]


def test_gap_and_exact_rf_grouping(track):
    records = [dict(visit_index=i, valid_start_counter=t * 10_000_000, receiver_id=0, channel=4,
                    actual_rf_hz=11000000000, edge="lower")
               for i, t in enumerate((0, 1, 2, 3, 4, 5, 15, 26, 27))]
    ids = {track.obs_id("s", row): dict(norad=77) for row in records}
    counts = [len(chunk) for chunk in track.split_gaps(records)]
    assert counts == [7, 2]
    assert len(track.blocks(records, "s", ids, 256)[0][3]) == 1
    records[0]["receiver_id"] = 1
    records[1]["actual_rf_hz"] += 1
    assert track.blocks(records, "s", ids, 256)[0][3] == []


def test_native_bank_counts_eligible_cells_and_interpolates(track, tmp_path):
    binary = tmp_path / "cyclic.so"
    track.build(binary)
    use = track.native_accumulator(binary)
    values = np.array([1., 3., 5.], dtype=np.float32)
    cfo = np.array([-50., 100.])
    offsets = np.array([-200., 0, 50.])
    sums = np.zeros((2, 3))
    count = use(values.ctypes.data, len(values), -100., 100., cfo.ctypes.data, len(cfo),
                offsets.ctypes.data, len(offsets), sums.ctypes.data)
    assert count == 4
    np.testing.assert_array_equal(sums, [[0., 2., 3.], [1., 5., 0.]])
