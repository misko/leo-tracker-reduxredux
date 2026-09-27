import importlib.util
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('mechanism',HERE/'run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_evidence_matches_direct_sum_and_held_isolation():
    p=np.array([[.1,.2,.3,.4],[.4,.3,.2,.1],[.2,.3,.1,.4]])
    shifts=np.array([[0,0,0],[0,np.pi/2,np.pi]]);train=np.array([True,True,False]);r=m.evidence(p,shifts,train)
    delta=np.linspace(-np.pi,np.pi,4,endpoint=False);z=zj=0.
    for shift in shifts:
        for theta in delta:
            d=[np.interp(theta+v,delta,.9*row*4+.1,period=2*np.pi) for row,v in zip(p,shift)]
            z+=d[0]*d[1]/8;zj+=np.prod(d)/8
    np.testing.assert_allclose(r['train'],np.log(z));np.testing.assert_allclose(r['held'],np.log(zj/z))
    p[-1]=[.9,.04,.03,.03];other=m.evidence(p,shifts,train)
    np.testing.assert_array_equal(r['joint_training_posterior'],other['joint_training_posterior'])
    assert r['held']!=other['held']


def test_completed_inputs_and_original_partitions():
    r=json.loads((HERE/'results.json').read_text());p=json.loads((HERE/'protocol.json').read_text());assert r['complete'] and r['protocol_sha256']==m.envelope.fresh.digest(HERE/'protocol.json')
    source=HERE.parent/'2026_09_27_ds6_phase_opportunity';plan=json.loads((source/f'{m.SID}-plan.json').read_text());expected={v['visit']:v['partition'] for v in plan['selected']}
    assert {o['visit']:o['partition'] for o in r['observations']}==expected
    assert sum(o['partition']=='train' for o in r['observations'])==2
    for c in r['selected_candidates']:assert c['training_mass']>.999
    for model in r['models'].values():np.testing.assert_allclose(sum(model['hypothesis_posterior']),1,atol=1e-10)
