"""Owned tests for the scientific control's provenance and fallback rules."""
from types import SimpleNamespace
import numpy as np
import pytest

from matched_controls import assert_factor_contract,cold_refit,factor_contract,policy_source


def toy_problem(reference):
    p=SimpleNamespace(rows=[dict(component='curve',candidate_index=7)],members=[0],labels=[0],
        alias=[1],keep=np.array([True,True]),values=np.array([12.,13.]),flat_times=np.array([0.,1.]),
        q=np.ones(2),lower=np.array([-12.5,-12.5]),upper=np.array([12.5,12.5]),reference=np.asarray(reference))
    p.state=lambda x:dict(phases=np.array([.5]))
    return p


def test_gate_or_qualification_failure_keeps_exact_baseline_pair():
    assert policy_source(True,True)=='trial'
    assert policy_source(False,True)=='baseline'
    assert policy_source(True,False)=='baseline'


def test_contract_rejects_changed_point_mask_and_identity():
    p=toy_problem([0]);expected=factor_contract(p,[])
    assert_factor_contract(p,[],expected)
    p.keep[0]=False
    with pytest.raises(ValueError):assert_factor_contract(p,[],expected)
    p=toy_problem([0]);p.rows[0]['candidate_index']=8
    with pytest.raises(ValueError):assert_factor_contract(p,[],expected)


def test_cold_fit_budget_phase_refresh_and_saved_reference_are_matched():
    starts=[];references=[];budgets=[]
    def build(arm,ref):
        references.append(ref.copy());return toy_problem(ref)
    def fit(p,x,iterations):
        starts.append(np.asarray(x).copy());budgets.append(iterations)
        return dict(parameters=np.array([1.,2.]),evaluations=1,stopped='converged')
    def summary(p,x,entries):
        return dict(endpoint_east_north_km=x,phase_reference=p.reference,linear_calibration_max_difference=0)
    expected=factor_contract(toy_problem([0]),[])
    result=cold_refit(build,'c0',1,[],expected,fit_function=fit,summary_function=summary)
    np.testing.assert_array_equal(starts[0],[0,0])
    np.testing.assert_array_equal(references[0],[0])
    np.testing.assert_array_equal(references[-1],[.5])
    assert budgets==[48]*5 and len(result['history'])==5
    assert result['final_phase_change_s']==0


def test_predictive_calibration_feedback_is_rejected():
    expected=factor_contract(toy_problem([0]),[])
    with pytest.raises(ValueError,match='fed back'):
        cold_refit(lambda a,r:toy_problem(r),'c0',1,[],expected,
            fit_function=lambda p,x,iterations:dict(parameters=x),
            summary_function=lambda p,x,e:dict(linear_calibration_max_difference=.01))
