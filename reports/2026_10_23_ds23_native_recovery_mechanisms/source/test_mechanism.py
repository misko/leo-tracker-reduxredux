import numpy as np
import pytest
from types import SimpleNamespace
from mechanism import selected_fragments,tempered_objective,tempered_residual,id_audit

def test_family_ablation_retains_whole_paths():
    paths=[dict(norad=1,key='a'),dict(norad=2,key='b'),dict(norad=1,key='c')]
    assert selected_fragments(paths,'only',1)==[paths[0],paths[2]]
    assert selected_fragments(paths,'without',1)==[paths[1]]
    assert selected_fragments(paths,'all')==paths

def test_tempering_is_incremental_not_entire_parent():
    assert tempered_objective(100,140,0)==100
    assert tempered_objective(100,140,1)==140
    assert tempered_objective(100,140,.25)==110
    with pytest.raises(ValueError):tempered_objective(100,140,-1)

def test_audit_rejects_physical_reuse_across_roles():
    p=SimpleNamespace(members=[0],slices=[slice(0,2)],keep=np.array([True,False]),scan=SimpleNamespace(tracks=[dict(observation_ids=['a','b']),dict(observation_ids=['a'])]))
    with pytest.raises(AssertionError,match='overlap'):id_audit(p,[dict(track_index=1)])
    p.scan.tracks[1]['observation_ids']=['b']
    assert id_audit(p,[dict(track_index=1)])['intersection']==0

def test_actual_solver_residual_has_weighted_objective_and_gradient():
    def parent(x):return np.array([x-1,2.])
    def full(x):return np.array([x-4,3.,1.])
    alpha=.25;x=2.;h=1e-5
    def objective(z):
        r=tempered_residual(parent(z),full(z),alpha)
        return r@r
    expected=(1-alpha)*(parent(x)@parent(x))+alpha*(full(x)@full(x))
    assert objective(x)==pytest.approx(expected)
    assert (objective(x+h)-objective(x-h))/(2*h)==pytest.approx(2*((1-alpha)*(x-1)+alpha*(x-4)),abs=1e-8)
