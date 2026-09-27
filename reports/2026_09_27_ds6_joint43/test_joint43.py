import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from run_joint43 import SparseJoint

HERE=Path(__file__).resolve().parent


class QuadraticScan:
    def __init__(self,tau):self.target=np.array([1.2,-.7,tau]);self.held_bias=0.
    def evaluate(self,x,drift):
        return dict(train=-float(np.sum((x-self.target)**2)),held=self.held_bias)


def test_sparse_gradient_matches_independent_global_difference():
    models=[QuadraticScan(t) for t in [-1.,.5,2.]]
    objective=SparseJoint(models);x=np.array([2.,3.,-.2,.3,1.])
    value,gradient=objective.value_gradient(x)
    def function(v):return -sum(m.evaluate(np.array([v[0],v[1],v[i+2]]),False)['train'] for i,m in enumerate(models))
    expected=[]
    for i in range(len(x)):
        changed=x.copy();changed[i]+=1e-4
        expected.append((function(changed)-function(x))/1e-4)
    np.testing.assert_allclose(value,function(x))
    np.testing.assert_allclose(gradient,expected,atol=1e-8)
    for model in models:model.held_bias=1e9
    v2,g2=objective.value_gradient(x)
    assert v2==value
    np.testing.assert_array_equal(g2,gradient)


def test_shared_geometry_and_independent_timing_recover_without_reference():
    objective=SparseJoint([QuadraticScan(t) for t in [-1.,.5,2.]])
    fit=minimize(objective.value_gradient,np.zeros(5),jac=True,method='L-BFGS-B',bounds=[(-12,12)]*2+[(-5,5)]*3)
    assert fit.success
    np.testing.assert_allclose(fit.x,[1.2,-.7,-1.,.5,2.],atol=.001)


def test_frozen_random_scan_partition_covers_all_ds6():
    protocol=json.loads((HERE/'protocol.json').read_text())
    groups=protocol['splits']
    assert len(groups['all'])==43
    assert set(groups['A']).isdisjoint(groups['B'])
    assert set(groups['A'])|set(groups['B'])==set(groups['all'])
    ordered=sorted(groups['all'],key=lambda s:hashlib.sha256(f"{protocol['seed']}:{s}".encode()).hexdigest())
    assert groups['A']==ordered[::2] and groups['B']==ordered[1::2]
    assert hashlib.sha256((HERE/'run_joint43.py').read_bytes()).hexdigest()==protocol['source_sha256']
    for name,value in protocol['files'].items():assert hashlib.sha256((HERE.parent/name).read_bytes()).hexdigest()==value


def test_finished_real_fits_and_exact_propagation_audits():
    protocol=json.loads((HERE/'protocol.json').read_text())
    for name,sessions in protocol['splits'].items():
        result=json.loads((HERE/f'{name}.json').read_text())
        assert result['complete']
        assert result['sessions']==sessions
        assert result['protocol_sha256']==hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
        assert result['best']==max(result['runs'],key=lambda r:r['train'])
        assert len(result['best']['x'])==2+len(sessions)
        assert {a['session_id'] for a in result['audits']}==set(sessions)
        assert all(np.isfinite(a['exact_train']) and np.isfinite(a['exact_held']) for a in result['audits'])
        assert max(a['maximum_interpolation_error_hz'] for a in result['audits'])<1.
