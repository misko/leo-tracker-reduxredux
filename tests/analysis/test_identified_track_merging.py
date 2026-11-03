"""Full residual and ownership checks when satellite proposals guide merging."""

import numpy as np
import pytest

from leo.analysis.research.identified_track_merging import consolidate
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


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


def test_joined_screen_blocks_structure_hidden_across_short_fragments():
    rng = np.random.default_rng(629)
    rows = []
    for i, delta in enumerate((-45, -27, -9, 9, 27, 45)):
        row = segment(str(i), start=i * 25.0)
        row["native_residual_hz"] = 350 + delta + rng.normal(0, 15, 21)
        rows.append(row)

    def no_structure(residual, times):
        return bool(batch_noise_screen(residual[None, :], times)["noise_screen_pass"][0])

    unchecked = consolidate(rows, accept)
    checked = consolidate(rows, accept, accept_joined_residual=no_structure)
    assert unchecked["output_tracks"] == 1
    assert checked["output_tracks"] > 1
    assert checked["points"] == unchecked["points"] == 126
    assert checked["points_dropped"] == 0
    assert checked["identities_changed"] is False
    for group in checked["groups"]:
        own = [row for row in rows if row["key"] in group["members"]]
        times = np.concatenate([row["time_s"] for row in own])
        residual = np.concatenate([row["native_residual_hz"] for row in own]) - group["bias_hz"]
        order = np.argsort(times)
        assert no_structure(residual[order], times[order])


def test_joined_screen_receives_time_sorted_original_samples_and_keeps_rejections():
    rows = [segment("late", start=25), segment("early")]
    seen = []

    def reject(residual, times):
        assert len(times) == len(residual)
        assert np.all(np.diff(times) >= 0)
        seen.append(len(times))
        return False

    result = consolidate(rows, accept, accept_joined_residual=reject)
    assert max(seen) == 42
    assert result["output_tracks"] == 2 and result["points"] == 42
    assert all(not g["residual_check"] for g in result["groups"])
