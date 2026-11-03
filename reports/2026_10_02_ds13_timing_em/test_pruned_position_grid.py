from pruned_position_grid import profile_seeds


def test_reference_and_alternative_use_same_two_initialization_classes():
    selection = {"fit": {"parameters": [1., 2.]}}
    for label in ("truth", "S-50m", "N-500m"):
        point = {"label": label, "best": {"parameters": [3., 4.]}}
        seeds = profile_seeds(point, selection)
        assert [direction for direction, _ in seeds] == [
            "previous_compact_at_position", "pruned_at_displaced_position"]
        assert seeds[0][1] is point["best"]
        assert seeds[1][1] is selection["fit"]
