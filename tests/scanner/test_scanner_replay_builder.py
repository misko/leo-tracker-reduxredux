from __future__ import annotations

from tools.build_scanner_replay_dataset import _largest_quiet_interval


def test_largest_quiet_interval_uses_the_full_stream_without_activity() -> None:
    assert _largest_quiet_interval([], duration_s=60.0, dwell_s=0.08) == (0.0, 60.0)


def test_largest_quiet_interval_guards_and_merges_activity() -> None:
    assert _largest_quiet_interval(
        [(0.0, 10.0), (9.9, 12.0), (20.0, 60.0)],
        duration_s=60.0,
        dwell_s=0.08,
    ) == (12.2, 19.8)


def test_largest_quiet_interval_rejects_gaps_shorter_than_a_dwell() -> None:
    assert (
        _largest_quiet_interval(
            [(0.0, 29.97), (30.03, 60.0)],
            duration_s=60.0,
            dwell_s=0.08,
        )
        is None
    )
