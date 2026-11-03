from reference_profile_balance import merge_positions, reference_starts


def test_reference_gets_nearest_ray_and_displaced_starts_not_extra_radius_weight():
    positions = [{"label": "truth", "radius_m": 0}, {"label": "N-50m", "radius_m": 50},
                 {"label": "N-100m", "radius_m": 100},
                 {"label": "displaced_optimum", "radius_m": None}]
    assert [point["label"] for point in reference_starts(positions)] == [
        "N-50m", "displaced_optimum"]


def test_merging_preserves_original_and_replaces_reference_best():
    original = {"positions": [{"label": "truth", "best": {"objective": 10.},
                               "attempts": [], "ranking_resolved": True}]}
    balanced = {"best": {"objective": 9., "success": False}, "attempts": [1, 2],
                "best_attempt_index": 1}
    result = merge_positions(original, balanced, {})
    assert original["positions"][0]["best"]["objective"] == 10.
    assert result["positions"][0]["best"]["objective"] == 9.
    assert result["unresolved_position_labels"] == ["truth"]
