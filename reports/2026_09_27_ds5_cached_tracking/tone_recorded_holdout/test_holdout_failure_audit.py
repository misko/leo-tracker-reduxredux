from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_holdout import classify


def test_active_identity_failure_cannot_be_repaired_by_inactive_only_rescue():
    row = {'native_decisions': {'native_tracked': [{'active': True}]},
           'tone_rescue_result': {'rescue_receiver': 1, 'rescue_events': []}}
    assert classify(row, 0) == 'active_primary_identity_disagreement'


def test_selection_and_confirmation_failures_are_not_mislabeled_as_margin_failures():
    row = {'native_decisions': {'native_tracked': [{'active': False}]},
           'tone_rescue_result': {'rescue_receiver': 1, 'rescue_events': []}}
    assert classify(row, 0) == 'inactive_receiver_not_selected'
    row['tone_rescue_result']['rescue_receiver'] = 0
    assert classify(row, 0) == 'other_rescue_failure'
    row['tone_rescue_result']['rescue_events'] = [{'reason': 'python_margin_failed'}]
    assert classify(row, 0) == 'all_probe_zero_proposals_below_margin'
    row['tone_rescue_result']['rescue_events'].append({'reason': 'confirmation_failed'})
    assert classify(row, 0) == 'other_rescue_failure'
