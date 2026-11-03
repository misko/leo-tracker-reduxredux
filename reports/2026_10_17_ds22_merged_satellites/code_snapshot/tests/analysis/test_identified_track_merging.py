"""Full residual and ownership checks when satellite proposals guide merging."""

import numpy as np
import pytest

from leo.analysis.research.identified_track_merging import consolidate


def segment(key, start=0.0, bias=300.0, norad=123):
    t = np.linspace(start, start + 20, 21)
    return dict(
        key=key,
        candidate_norad=norad,
        time_s=t,
        native_residual_hz=bias + 20 * np.sin(t),
        observation_ids=[f"{key}:{i}" for i in range(len(t))],
    )


def accept(residual, times):
    return np.sqrt(np.mean(residual**2)) < 150


def test_sequential_or_overlapping_tracks_can_join_without_dropping_points():
    for start in (10.0, 25.0):
        result = consolidate([segment("a"), segment("b", start)], accept)
        assert result["output_tracks"] == 1
        assert result["points"] == 42 and result["points_dropped"] == 0
        assert result["identities_changed"] is False


def test_incompatible_biases_keep_both_tracks():
    result = consolidate([segment("a"), segment("b", 25.0, bias=1300.0)], accept)
    assert result["output_tracks"] == 2 and result["points"] == 42


def test_different_identities_or_long_gaps_cannot_be_forced_together():
    for second in (segment("b", 25.0, norad=456), segment("b", 50.0)):
        result = consolidate([segment("a"), second], accept)
        assert result["output_tracks"] == 2 and result["points_dropped"] == 0


def test_duplicate_evidence_is_an_error():
    with pytest.raises(ValueError, match="duplicate observation"):
        consolidate([segment("a"), segment("a")], accept)
