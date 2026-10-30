import pytest
from reconcile_predictive_annotation_sources import matching_evidence
from run_predictive_queue_inclusions import inclusion_options


def test_role_and_physical_scope_are_required_not_filename_or_old_support():
    job=dict(track_id='t',job_id='scan')
    p=dict(job=job,target=dict(track_id='t',observation_ids=['a','b']),target_used_for_calibration=False)
    r=dict(track_id='t',inclusion_mode='predictive_only',identity_score_name='conditional_target',folds=[])
    assert matching_evidence(p,r,job,['a','b'])['coverage']=='exact_target'
    assert matching_evidence(p,r,job,['a','b','c'])['coverage']=='different_or_partial_target'
    assert matching_evidence(dict(p,target_used_for_calibration=True),r,job,['a','b']) is None
    assert matching_evidence(p,dict(r,inclusion_mode='calibration'),job,['a','b']) is None
    with pytest.raises(ValueError,match='different scan'):
        matching_evidence(dict(p,job=dict(job_id='wrong')),r,job,['a','b'])


def test_existing_annotations_can_use_exact_phase_grid_without_changing_shared_route():
    assert inclusion_options(False,.025)==['--uncalibrated-label','--phase-step','0.025']
    assert inclusion_options(True,.025)==['--predictive-member']
    with pytest.raises(ValueError):inclusion_options(False,0)
