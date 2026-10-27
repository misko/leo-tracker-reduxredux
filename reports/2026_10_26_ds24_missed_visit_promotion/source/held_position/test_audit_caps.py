from audit_caps import checkpoint_state
from position import write

def test_discovery_branch_checkpoint_never_becomes_a_qualified_endpoint(tmp_path):
    case='DS24-test';write(tmp_path/case/'progress_radio_noise.json',dict(choices=[{}]))
    row=checkpoint_state(tmp_path,case)
    assert row['active_stage_at_cap']=='discovery'
    assert row['completed_paired_discovery_branches']==1
    assert not row['partial_endpoints_qualified']

def test_completed_discovery_marks_association_as_pending(tmp_path):
    case='DS24-test';write(tmp_path/case/'fit_radio_noise.json',dict(status='complete'))
    row=checkpoint_state(tmp_path,case)
    assert row['last_completed_stage']=='discovery' and row['active_stage_at_cap']=='initial_association'
