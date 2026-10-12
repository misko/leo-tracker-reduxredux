import numpy as np
import pytest

from leo.analysis.continuous_merge_bootstrap import (
    ContinuousBootstrapPolicy,
    bootstrap_with_continuity,
    choose_proposals,
)
from leo.analysis.regional_position_bootstrap import BootstrapMatch, bootstrap_position
from tests.analysis.test_regional_position_bootstrap import bootstrap_fixture


def match(rows, satellite=0, rms=40):
    return BootstrapMatch(tuple(rows), satellite, 0.0, rms, rms**2)


def test_consistent_union_preserves_unrelated_originals_and_bank():
    original = ((0, 1, 2), (3, 4, 5), (6, 7, 8))
    joined = (0, 1, 2, 3, 4, 5)
    matches = (match(original[0]), match(original[1]), match(original[2], 1), match(joined))
    selected, receipt = choose_proposals(original, (joined,), matches, np.arange(9))
    assert selected == (joined, original[2])
    assert receipt["decisions"][0]["accepted"]


def test_polynomial_smoothness_cannot_override_a_different_orbital_match():
    original = ((0, 1, 2), (6, 7, 8))
    joined = (0, 1, 2, 3, 4, 5)
    matches = (match(original[0]), match(original[1], 1), match(joined, 2, 20))
    selected, receipt = choose_proposals(original, (joined,), matches, np.arange(9))
    assert selected == original
    assert receipt["decisions"][0]["reason"] == "different-orbital-candidate"
    ablated, _ = choose_proposals(
        original, (joined,), matches, np.arange(9), ContinuousBootstrapPolicy(mode="shape")
    )
    assert ablated == (joined, original[1])


@pytest.mark.parametrize(
    "joined,rms,reason",
    [
        ((9, 10, 11), 40, "no-selected-parent"),
        ((1, 2, 3, 4), 40, "partial-parent"),
        ((0, 1, 2, 3, 4, 5), 500, "joined-shape-residual"),
    ],
)
def test_no_quota_eviction_partial_replacement_or_noisy_union(joined, rms, reason):
    original = ((0, 1, 2), (6, 7, 8))
    matches = (match(original[0]), match(original[1], 1), match(joined, rms=rms))
    selected, receipt = choose_proposals(original, (joined,), matches, np.arange(12))
    assert selected == original
    assert receipt["decisions"][0]["reason"] == reason


def test_control_reproduces_original_bootstrap_on_the_same_observations():
    obs, bank, prior, tracks = bootstrap_fixture()
    joined = tracks[0]
    tracks = (joined[:3], joined[3:], *tracks[1:])
    original = bootstrap_position(obs, bank, prior, [3, -5], tracks, maximum_seconds=10)
    receipts = []
    result = bootstrap_with_continuity(
        obs,
        bank,
        prior,
        [3, -5],
        tracks,
        merged_tracks=(joined,),
        policy=ContinuousBootstrapPolicy(mode="baseline"),
        audit=receipts.append,
        maximum_seconds=10,
    )
    assert result.satellite_indices == original.satellite_indices
    assert result.matches == original.matches
    np.testing.assert_array_equal(result.vector, original.vector)
    assert receipts[0]["selected_joins"] == 0
    assert len(set(obs.window_ids)) == len(obs.window_ids)


def test_policy_and_budget_reject_invalid_values():
    for options in ({"mode": "unknown"}, {"rms_ratio": 0.5}, {"rms_floor_hz": np.nan}):
        with pytest.raises(ValueError):
            ContinuousBootstrapPolicy(**options)
    obs, bank, prior, tracks = bootstrap_fixture()
    with pytest.raises(TimeoutError):
        bootstrap_with_continuity(
            obs, bank, prior, [3, -5], tracks, merged_tracks=(), maximum_seconds=1e-12
        )
