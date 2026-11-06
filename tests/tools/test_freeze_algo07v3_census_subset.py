"""A research fixture must use the scan's causal cutoff, never the anchor or future TLEs."""

from types import SimpleNamespace

import pytest
from freeze_algo07v3_census_subset import causal_snapshots


def test_only_causal_window_including_boundaries_is_frozen():
    cutoff = 2_000_000_000_000_000_000
    oldest = cutoff - 72 * 3600 * 10**9
    rows = [SimpleNamespace(collected_utc_ns=t) for t in
            (oldest - 1, oldest, cutoff - 1, cutoff, cutoff + 1)]
    actual, chosen = causal_snapshots(rows, dict(causal_cutoff_utc_ns=cutoff,
                                              anchor_utc_ns=cutoff + 10**9))
    assert actual == cutoff and chosen == rows[1:4]


def test_missing_causal_cutoff_does_not_substitute_another_clock():
    with pytest.raises(KeyError, match='causal_cutoff_utc_ns'):
        causal_snapshots([], dict(anchor_utc_ns=123, cutoff_utc_ns=123))


@pytest.mark.parametrize('cutoff', [True, -1, 0, 1.5])
def test_invalid_cutoff_rejected(cutoff):
    with pytest.raises(ValueError, match='Positive integer'):
        causal_snapshots([], dict(causal_cutoff_utc_ns=cutoff))


def test_missing_causal_snapshots_is_an_explicit_failure():
    with pytest.raises(ValueError, match='No causal snapshots'):
        causal_snapshots([SimpleNamespace(collected_utc_ns=101)], dict(causal_cutoff_utc_ns=100))
