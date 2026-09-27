import hashlib
import json
from pathlib import Path

import numpy as np

from run_drift import profile

HERE=Path(__file__).resolve().parent


def test_profile_recovers_offsets_and_slopes_without_held_leakage():
    times=np.linspace(-50,50,100);mask=np.arange(100)%2==0
    times-=times[mask].mean()
    slopes=np.array([2.,-3.]);offsets=np.array([800.,-1200.])
    residual=offsets[:,None]+slopes[:,None]*times
    train,joint,offset,slope=profile(residual,times,mask,30.)
    np.testing.assert_allclose(offset,offsets,atol=.001)
    np.testing.assert_allclose(slope,slopes,atol=.001)
    changed=residual.copy();changed[:,~mask]+=1e6
    train2,joint2,offset2,slope2=profile(changed,times,mask,30.)
    np.testing.assert_array_equal(train,train2)
    np.testing.assert_array_equal(offset,offset2)
    np.testing.assert_array_equal(slope,slope2)
    assert np.all(joint2<joint)


def test_profile_handles_an_outlier_and_zero_span_without_nan():
    times=np.linspace(-50,50,100);mask=np.ones(100,dtype=bool)
    residual=(500.+2.*times)[None,:];residual[0,40]+=10000
    _,_,offset,slope=profile(residual,times,mask,30.)
    np.testing.assert_allclose(offset,[500.],atol=.1)
    np.testing.assert_allclose(slope,[2.],atol=.01)
    a,b,offset,slope=profile(np.ones((1,6))*500,np.zeros(6),np.array([True,False]*3),30.)
    assert np.all(np.isfinite([*a,*b,*offset,*slope]))
    np.testing.assert_array_equal(slope,[0.])


def test_frozen_results_and_numerical_audits():
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert hashlib.sha256((HERE/'run_drift.py').read_bytes()).hexdigest()==protocol['source_sha256']
    for name,value in protocol['files'].items():assert hashlib.sha256((HERE.parent/name).read_bytes()).hexdigest()==value
    for session in protocol['sessions']:
        result=json.loads((HERE/f'{session}.json').read_text())
        assert result['complete']
        assert result['protocol_sha256']==hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
        assert result['best']==max(result['runs'],key=lambda r:r['train'])
        assert result['maximum_interpolation_error_hz']<1.
        assert np.isfinite(result['held_gain'])
        # An explicit acceptance gate, not a reason to overwrite failed evidence.
        assert abs(result['iteration_audit']['train_change'])<.1
        assert abs(result['iteration_audit']['held_change'])<.1
