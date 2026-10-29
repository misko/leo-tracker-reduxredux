import json
import pytest
from run_annotation_inventory import pending_jobs


def test_queued_running_and_incomplete_attempts_are_not_restarted(tmp_path):
    rows=[dict(track_id=str(k),state='queued') for k in range(5)]
    attempt=tmp_path/'attempt-1';attempt.mkdir()
    (attempt/'selected.json').write_text(json.dumps(rows[:2]))
    # Neither claimed task has a terminal receipt; one has not even started.
    (tmp_path/'1').mkdir();(tmp_path/'2').mkdir()
    (attempt/'3-terminal.json').write_text('{}')
    assert [r['track_id'] for r in pending_jobs({'rows':rows},tmp_path,5)]==['4']
    with pytest.raises(ValueError,match='positive'):pending_jobs({'rows':rows},tmp_path,0)


def test_predictive_queue_selects_its_own_scope(tmp_path):
    rows=[dict(track_id='a',state='queued'),dict(track_id='b',state='needs_predictive_only_model')]
    assert pending_jobs({'rows':rows},tmp_path,1,True)==[rows[1]]
    assert pending_jobs({'rows':rows},tmp_path,1)==[rows[0]]


def test_dataset_priority_keeps_global_claims_and_other_rows(tmp_path):
    rows=[dict(track_id=str(k),state='queued',scopes=['DS24'] if k<2 else ['other']) for k in range(3)]
    attempt=tmp_path/'attempt-1';attempt.mkdir();(attempt/'selected.json').write_text(json.dumps(rows[:1]))
    assert pending_jobs({'rows':rows},tmp_path,3,scope='DS24')==[rows[1]]
    assert pending_jobs({'rows':rows},tmp_path,3)==rows[1:]
