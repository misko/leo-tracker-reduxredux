from datetime import UTC, datetime
from types import SimpleNamespace

from tools.research.inventory_historical_continuous_dual_rx import (
    CUTOFF_UTC_NS,
    timeline_is_contiguous,
)


def block(counter, sequence, *, count=10, missing=0, overflow=False):
    return SimpleNamespace(
        device_sample_counter=counter,
        source_sequence=sequence,
        sample_count=count,
        missing_samples_before=missing,
        overflow_observed=overflow,
    )


def test_cutoff_is_2026_08_24_utc():
    assert int(datetime(2026, 8, 24, tzinfo=UTC).timestamp() * 1_000_000_000) == CUTOFF_UTC_NS


def test_timeline_requires_nonempty_adjacent_clean_blocks():
    assert timeline_is_contiguous([block(100, 1), block(110, 2)])
    assert not timeline_is_contiguous([])
    assert not timeline_is_contiguous([block(100, 1, missing=1)])
    assert not timeline_is_contiguous([block(100, 1, overflow=True)])
    assert not timeline_is_contiguous([block(100, 1), block(111, 2)])
    assert not timeline_is_contiguous([block(100, 1), block(110, 3)])
