import numpy as np
import pytest

from leo.analysis.research.regional_mode_stability import regional_deletion_stability


def test_deleting_a_dominant_scan_exposes_a_distant_mode():
    result = regional_deletion_stability(
        [[10, 0], [0, 4], [0, 4]], [0, 0], [0, 10], ["a", "b", "c"]
    )
    assert result["best_grid_index"] == 0
    assert result["separated_mode_score_gap"] == 2
    assert result["deletions"][0]["grid_index"] == 1
    assert result["maximum_deletion_displacement_km"] > 1100
    assert not result["calibrated_uncertainty"]


def test_group_constant_offsets_and_permutation_do_not_change_selected_locations():
    scores = np.array([[10, 0, 1], [0, 4, 1], [0, 4, 1]])
    original = regional_deletion_stability(scores, [0, 0, 0], [0, 10, 20], ["a", "b", "c"])
    changed = regional_deletion_stability(
        (scores + np.array([100, -50, 7])[:, None])[[2, 0, 1]],
        [0, 0, 0],
        [0, 10, 20],
        ["c", "a", "b"],
    )
    assert original["best_grid_index"] == changed["best_grid_index"]
    assert original["separated_mode_score_gap"] == changed["separated_mode_score_gap"]
    assert sorted(original["deletions"], key=lambda r: r["omitted_group"]) == sorted(
        changed["deletions"], key=lambda r: r["omitted_group"]
    )


def test_one_scan_is_not_reported_as_validated_stability():
    result = regional_deletion_stability([[2, 2]], [0, 0], [179.9, -179.9], ["one"])
    assert result["state"] == "insufficient-groups"
    assert result["deletions"] == []
    assert result["exact_tie_count"] == 2
    assert result["separated_mode_score_gap"] is None


@pytest.mark.parametrize("scores, groups", [([[0, 0], [0, 0]], ["x", "x"]), ([[np.nan, 0]], ["x"])])
def test_rejects_duplicate_groups_and_nonfinite_scores(scores, groups):
    with pytest.raises(ValueError):
        regional_deletion_stability(scores, [0, 0], [0, 1], groups)


def test_antimeridian_distance_is_short():
    result = regional_deletion_stability(
        [[5, 0], [0, 4]], [0, 0], [179.9, -179.9], ["a", "b"], separated_mode_km=10
    )
    assert 22 < result["maximum_deletion_displacement_km"] < 23
