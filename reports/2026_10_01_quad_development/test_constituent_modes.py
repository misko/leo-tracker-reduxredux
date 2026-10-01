from copy import deepcopy
import pytest
from diagnose_constituent_modes import compare_fits


def test_assignment_comparison_requires_identical_candidate_and_observation_binding():
    fit=dict(mean=[1,2],associations=[0,1],objectives=[10],seed_index=0,
             converged=True,reason='converged',iterations=2)
    original=dict(binding={'unit':'pair'},columns=[[0,1]],inputs={'orbits':'hash'},
                  observations=[['a'],['b']],precision=[0,0],best=fit,fits=[fit])
    variant=deepcopy(original);variant['best']['mean']=[1,3]
    variant['best']['associations']=[0,2];variant['best']['objectives']=[9]
    result=compare_fits(original,variant)
    assert result['changed_assignments']==1 and result['objective_change']==-1
    assert result['position_separation_m']==1000
    variant['inputs']['orbits']='other catalogue'
    with pytest.raises(AssertionError,match='inputs'):compare_fits(original,variant)
