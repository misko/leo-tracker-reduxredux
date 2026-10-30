from audit_predictive_family_inclusion import owner_changes


def test_recovery_must_detect_relabels_and_losses_even_when_point_count_grows():
    before = {'retained': 10, 'relabeled': 20, 'lost': 30}
    after = {'retained': 10, 'relabeled': 21, 'new1': 40, 'new2': 40}
    assert owner_changes(before, after) == [
        {'observation_id': 'relabeled', 'before': 20, 'after': 21},
        {'observation_id': 'lost', 'before': 30, 'after': None}]
    assert owner_changes({'retained': 10}, after) == []
