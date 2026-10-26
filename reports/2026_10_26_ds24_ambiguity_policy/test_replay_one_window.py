import copy
from replay_one_window import compare_candidates


def row():
    return dict(candidate_rank=0, integer_epoch_sample=10,
                passed_fractional_margin_gate=True,
                fractional_epoch_offset_samples=.1,
                fractional_tracking_cfo_hz=42., fractional_exact_score=.2,
                fractional_control_score=.01, fractional_margin=.19)


def test_identity_and_gate_changes_fail_even_with_equal_cfo():
    old = row()
    for field, value in [('candidate_rank', 1), ('integer_epoch_sample', 11),
                         ('passed_fractional_margin_gate', False)]:
        new = copy.deepcopy(old)
        new[field] = value
        assert not compare_candidates([old], [new])['all_passed']


def test_missing_candidates_and_nonfinite_frequency_fail():
    old = row()
    assert not compare_candidates([old], [])['all_passed']
    new = {**old, 'fractional_tracking_cfo_hz': float('nan')}
    assert not compare_candidates([old], [new])['all_passed']


def test_declared_numeric_tolerance_is_enforced():
    old = row()
    assert compare_candidates([old], [dict(old)])['all_passed']
    assert compare_candidates([old], [{**old, 'fractional_tracking_cfo_hz': 42.+5e-7}])['all_passed']
    assert not compare_candidates([old], [{**old, 'fractional_tracking_cfo_hz': 42.+2e-6}])['all_passed']
