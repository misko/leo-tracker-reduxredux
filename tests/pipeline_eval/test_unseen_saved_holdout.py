from reports.ALGO08.v3.unseen_saved_holdout import enrollment, estimated_child_ceiling


def test_original_release_assignment_and_unchanged_order():
    result = enrollment()
    assert result["selected"] == "DS30-0255"
    assert result["eligible_ids"] == 87
    assert result["order"] == ("routed", "installed")


def test_budget_uses_post_detection_time_and_preserves_unknown():
    assert estimated_child_ceiling(49.) == 103.
    assert estimated_child_ceiling(58.) > 120.
    assert estimated_child_ceiling(None) is None
