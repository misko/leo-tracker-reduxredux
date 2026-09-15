"""Outcome-independent selection and refusal to publish incomplete evidence."""

import pytest

from tools.replay_scanner_pss_bandwidth import aggregate, select


def test_selection_is_independent_of_iteration_order():
    indexes = [12, 40, 108, 125, 550]
    assert select(indexes, "sha256:" + "a" * 64) == select(
        list(reversed(indexes)), "sha256:" + "a" * 64
    )


def test_aggregate_refuses_partial_cohort(tmp_path):
    with pytest.raises(ValueError, match="incomplete"):
        aggregate(tmp_path)
