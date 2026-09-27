"""Training scale calibration, model equivalence, and recorded evidence checks."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import t as student

from run_scale import Objective, ScaledObjective, site, training_scale

HERE=Path(__file__).resolve().parent


def test_scale_calibration_recovers_t4_scale_and_ignores_held_values():
    train=student.ppf((np.arange(10000)+.5)/10000,df=4)*75.+1234.
    values=np.empty(20000);values[::2]=train;values[1::2]=0
    mask=np.arange(20000)%2==0
    before=training_scale(values,mask)
    assert before==pytest.approx(75.,rel=.001)
    values[~mask]=1e9
    assert training_scale(values,mask)==before
    assert training_scale(np.zeros(6),np.ones(6,dtype=bool))==20.
    assert training_scale(train*1000,np.ones(10000,dtype=bool))==1000.


def test_scaled_objective_matches_baseline_and_isolates_training():
    center=[37.85,-122.48];receiver,up=site(*center)
    pos=np.broadcast_to(receiver+550*up,(2,41,8,3)).copy();pos[1]+=20
    vel=np.broadcast_to(np.array([1.,2.,3.]),pos.shape).copy()
    mask=np.array([True,False]*4)
    tracks=[dict(track_id='a',receiver_id=0,y=np.arange(8.)*7,mask=mask,
                 centered_t=np.arange(8.)-3.,sigma=100.)]
    banks={'a':(pos,vel,None)}
    baseline=Objective(tracks,banks,center,2,[0])
    scaled=ScaledObjective(tracks,banks,center,2,[])
    x=np.array([.2,-.2,.125])
    a=baseline.evaluate(x,False);b=scaled.evaluate(x)
    for key in ['train','held']:assert a[key]==b[key]
    tracks[0]['sigma']=75.
    before=scaled.evaluate(x)
    tracks[0]['y'][~mask]+=10000
    after=scaled.evaluate(x)
    assert before['train']==after['train']
    assert before['held']!=after['held']


def test_recorded_results_are_complete_and_baseline_reproduces():
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert hashlib.sha256((HERE/'run_scale.py').read_bytes()).hexdigest()==protocol['source_sha256']
    for name,value in protocol['dependencies'].items():
        assert hashlib.sha256((HERE.parent/name).read_bytes()).hexdigest()==value
    for name in protocol['inputs']:
        source=HERE.parent/'2026_09_27_ds6_common_rate_validation'/name
        assert hashlib.sha256(source.read_bytes()).hexdigest()==protocol['inputs'][name]
        result=json.loads((HERE/name.replace('-plan','')).read_text())
        old_path=HERE.parent/'2026_09_27_ds6_joint_drift'/name.replace('-plan','')
        assert hashlib.sha256(old_path.read_bytes()).hexdigest()==protocol['baseline_sha256'][old_path.name]
        old=json.loads(old_path.read_text())
        parent_protocol=HERE.parent/'2026_09_27_ds6_joint_drift/protocol.json'
        assert hashlib.sha256(parent_protocol.read_bytes()).hexdigest()==old['protocol_sha256']
        parent=json.loads(parent_protocol.read_text())
        transfer=HERE.parent/'2026_09_27_ds6_cfo_transfer'/old_path.name
        assert hashlib.sha256(transfer.read_bytes()).hexdigest()==parent['transfer_sha256'][transfer.name]
        assert result['complete']
        assert result['protocol_sha256']==hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
        assert abs(result['arms']['fixed_100']['best']['train']-old['arms']['no_drift']['best']['train'])<.01
        assert all(20<=row['sigma']<=1000 for row in result['calibration'])
        for arm in result['arms'].values():
            assert arm['best']==max(arm['runs'],key=lambda r:r['train'])
            assert arm['maximum_interpolation_error_hz']<1.
            assert np.isfinite(arm['exact_held'])
