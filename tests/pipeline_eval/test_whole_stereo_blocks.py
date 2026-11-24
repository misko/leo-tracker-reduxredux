from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def replay(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("whole_stereo_blocks")


def test_per_stream_schedule_counts_invalid_gaps_and_anchors_independently(replay):
    class Metadata(dict):
        def __getitem__(self, key):
            if key == "candidates":
                raise AssertionError("Schedule read a waveform result")
            return super().__getitem__(key)

    schedule = replay.StereoBlocks()
    streams = [Metadata(edge="lower", channel=1, actual_rf_hz=rf) for rf in (10.7e9, 10.71e9)]
    observed = []
    for index in range(17):
        a, b = (Metadata(row, valid_start_counter=(index+1)**2*441_016) for row in streams)
        observed.append(schedule.next(a))
        if index % 2 == 0:
            other = schedule.next(b)
            if index in (0, 16):
                assert other == ("full", True)
    assert [i for i, (mode, _keep) in enumerate(observed) if mode == "full"] == [0, 8, 16]
    assert [i for i, (_mode, kept) in enumerate(observed) if not kept] == [3, 6, 10, 13]
    with pytest.raises(ValueError, match="hardware counters"):
        schedule.next(a)


def test_an_empty_skip_advances_real_history_without_supplying_a_vote(replay):
    candidate = dict(fractional_tracking_cfo_hz=-193_250., fractional_margin=.25, candidate_rank=0)
    original = [dict(receiver_id=0, channel=1, actual_rf_hz=10.7e9, valid_start_counter=index*2_000_000,
                     visit_index=index, candidates=[candidate]) for index in range(5)]
    masked = [dict(row, candidates=[]) if row["visit_index"] == 2 else row for row in original]
    before, after = replay.history(original), replay.history(masked)
    assert list(map(bool, before)) == [False, False, False, True, True]
    assert list(map(bool, after)) == [False, False, False, False, True]


def test_gross_pricing_credits_only_original_measured_short_cpu(replay):
    full = dict(native=dict(native_calls={"full": 12, "short_primary": 30},
                            native_cpu_ns={"full": 20_000_000_000, "short_primary": 12_000_000_000}),
                acquire=dict(cpu_ns=39_000_000_000))
    paid = dict(kept_native_lanes={"full": 12, "short_primary": 20}, skipped_native_lanes={"short_primary": 10})
    result = replay.price(full, paid)
    assert result["gross_credit_cpu_s"] == 4.
    assert result["modeled_acquisition_cpu_s"] == 35.
    assert result["non_native_cpu_s"] == 7.
    assert result["eligible"]


@pytest.mark.parametrize(("clearance", "decision", "expected"), [
    (.1, "complete", "valid_fix"), (.1, "withheld", "false_withhold"),
    (-.1, "complete", "false_fix"), (-.1, "withheld", "valid_withhold"),
])
def test_south_geographic_score_keeps_false_fixes_as_failures(replay, clearance, decision, expected):
    south = import_module("whole_stereo_blocks_south")
    assert south.geographic_result(clearance, decision) == expected
