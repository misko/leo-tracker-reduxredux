import pytest
from summarize_cold_seed_limits import arm_row


def result():
    launch = dict(returncode=0, within_budget=True, timed_out=False, elapsed_seconds=10.)
    return dict(launch=dict(launch), audit_launch=dict(launch), evaluation={'rows': [
        dict(unit='a', cpu_s=8., accepted=True, error_m=12., failures=[])]})


def test_failed_audit_launch_cannot_inherit_geographic_score():
    r = result()
    assert arm_row('a', 1, r)['error_m'] == 12.
    r['audit_launch']['timed_out'] = True
    row = arm_row('a', 1, r)
    assert not row['accepted'] and row['error_m'] is None


def test_wrong_unit_and_missing_audit():
    r = result()
    with pytest.raises(ValueError):
        arm_row('wrong', 1, r)
    r['evaluation'] = None
    row = arm_row('a', 1, r)
    assert not row['accepted'] and row['error_m'] is None
