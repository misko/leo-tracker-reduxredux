import json
import pytest
from audit_numerical_results import audit,execution_evidence,status_transition,same_scientific_inputs


def test_numerical_transition_uses_final_round_and_never_physical_gate_as_optimizer_success():
    old=dict(history=[dict(success=True,message='early'),dict(success=False,message='ABNORMAL: ')])
    new=dict(history=[dict(success=False,message='early'),dict(success=True,message='CONVERGENCE')],paired_valid=False)
    row=status_transition(old,new)
    assert row['ABNORMAL_to_success'] and not row['original_success_to_failure']
    assert row['treatment_success']
    # Paired validity is deliberately distinct from optimizer completion.
    assert not new['paired_valid']


def test_changed_target_or_prior_is_not_a_matched_optimizer_comparison():
    old=dict(targets=[dict(norad=10,alias=1)],family_prior=dict(phase_prior_sigma_s=3),start=[0,0])
    assert not same_scientific_inputs(old,dict(old))
    assert same_scientific_inputs(old,dict(old,targets=[dict(norad=11,alias=1)]))==['targets']
    assert same_scientific_inputs(old,dict(old,family_prior=dict(phase_prior_sigma_s=4)))==['family_prior']


def test_final_audit_rejects_incomplete_terminal_receipt(tmp_path):
    (tmp_path/'dataset-protocol.json').write_text(json.dumps(dict(fast_cases=['DS26-X'])))
    (tmp_path/'source-freeze.json').write_text(json.dumps(dict(files_sha256={})))
    folder=tmp_path/'cases/DS26-X';folder.mkdir(parents=True)
    (folder/'receipt.json').write_text('{')
    with pytest.raises(ValueError,match='every frozen fast-case terminal receipt'):
        audit(tmp_path,final=True)


def test_worker_timeout_survives_missing_bootstrap_receipt(tmp_path):
    stage=dict(name='joint-c0',status='failed',command=['python','-B','fit_two_predictive_families.py'],
        error='TimeoutExpired: numerical_stage.py child timed out',budget_seconds=5)
    (tmp_path/'decision.json').write_text(json.dumps(dict(stages=[stage,dict(name='joint-fitted_c',status='budget_exhausted')])))
    result=execution_evidence(tmp_path)
    assert len(result['failed'])==1 and result['failed'][0]['timeout']
    assert len(result['missing_helper_receipts'])==1
    assert result['missing_helper_receipts'][0]['stage']=='joint-c0'
    assert result['unstarted_budget_exhausted']==['joint-fitted_c']
    # A child receipt can exist without a case decision yet. It remains an
    # authoritative timeout and must not be counted twice when both exist.
    (tmp_path/'joint-c0-receipt.json').write_text(json.dumps(stage))
    assert len(execution_evidence(tmp_path)['failed'])==1
