import pytest
from run_predictive_queue_inclusions import require_predictive_result


def test_inclusion_queue_rejects_calibration_role_or_mismatched_identity_score():
    require_predictive_result(dict(inclusion_mode='predictive_only',identity_score_name='conditional_target'))
    for result in ({},dict(inclusion_mode='predictive_only',identity_score_name='joint'),
                   dict(inclusion_mode='calibration',identity_score_name='conditional_target')):
        with pytest.raises(ValueError,match='predictive-only'):require_predictive_result(result)


def test_assessment_ledger_does_not_count_timeout_or_queue_claim_as_evidence():
    from report_predictive_inventory_completion import assessed
    assert not assessed(dict(state='execution_timeout',claim='attempt-6'))
    assert not assessed(dict(annotation_source='',predictive_recheck_source=''))
    for key in ('annotation_source','predictive_recheck_source','inactive_fragment_annotation_source'):
        assert assessed({key:'/immutable/result.json', 'state':'ambiguous_identity'})


def test_fresh_reassessment_requires_complete_matching_receipts(tmp_path):
    import json
    from run_predictive_queue_inclusions import reassessment_rows
    jobs=[dict(track_id='a',label='scan'),dict(track_id='b',label='scan')]
    (tmp_path/'protocol.json').write_text(json.dumps(dict(jobs=jobs)))
    with pytest.raises(FileNotFoundError):reassessment_rows(tmp_path)
    execution=[dict(job=jobs[0],status='complete'),dict(job=jobs[1],status='timeout')]
    (tmp_path/'execution.json').write_text(json.dumps(execution))
    for r in execution:(tmp_path/(r['job']['track_id']+'-terminal.json')).write_text(json.dumps(r))
    rows,excluded,_=reassessment_rows(tmp_path)
    assert rows==[jobs[0]]
    assert excluded[0]['execution']=='timeout'
    (tmp_path/'b-terminal.json').write_text(json.dumps(dict(status='complete')))
    with pytest.raises(ValueError,match='inconsistent'):reassessment_rows(tmp_path)
