"""Recovery preserves scientific outputs and does not silently reset budgets."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from resume_ds23_combined_recovery_full import interrupted_cases,terminal_from_checkpoint


def test_conservative_fifo_prefix_keeps_completed_out_of_new_work():
    interrupted,fresh=interrupted_cases(list('abcdefgh'),{'a','c'},3)
    assert interrupted==['b','d','e']
    assert fresh==['f','g','h']


def test_dispatch_inconsistency_is_not_silently_reclassified():
    with pytest.raises(ValueError,match='FIFO'):
        interrupted_cases(list('abcdefgh'),{'h'},2)


def test_checkpoint_retains_policy_and_original_elapsed_evidence():
    old=dict(policy_arms={'c0':{'score':12},'fitted_c':{'score':11}},
             policy_model={'mask':[True,False]},status='running',seconds=127.)
    result=terminal_from_checkpoint(old,'digest',900)
    assert result['policy_arms']==old['policy_arms']
    assert result['policy_model']==old['policy_model']
    assert result['status']=='interrupted'
    assert result['seconds']==127.
    assert result['charged_inference_budget_seconds']==900
    assert old['status']=='running'
