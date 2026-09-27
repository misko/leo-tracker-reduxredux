import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('expanded',HERE/'run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_predict_matches_direct_weighted_sum():
    train=np.array([[-1.,-2.],[-3.,-4.]]);joint=train-np.array([[.4,.8],[.1,.6]]);p=np.array([.7,.3]);r=m.predict(train,joint,p)
    expected=np.log(np.sum(np.exp(joint)*p[:,None])/np.sum(np.exp(train)*p[:,None]));assert abs(r['held_cfo_log_predictive']-expected)<1e-12
    np.testing.assert_allclose(m.predict(train,joint,[1.,0.])['held_cfo_log_predictive'],logsumexp(joint[0])-logsumexp(train[0]))


def test_completed_membership_frozen_prior_and_training_phase_only():
    inputs=json.loads((HERE/'inputs.json').read_text());protocol=json.loads((HERE/'protocol.json').read_text());result=json.loads((HERE/'results.json').read_text());donorpath=ROOT/'2026_09_27_ds6_baseline_sensitivity/results.json';donor=json.loads(donorpath.read_text())
    assert result['complete'] and result['protocol_sha256']==hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
    assert protocol['inputs_sha256']==hashlib.sha256((HERE/'inputs.json').read_bytes()).hexdigest()
    assert protocol['donor_sha256']==hashlib.sha256(donorpath.read_bytes()).hexdigest()
    assert protocol['priors']['transferred_baseline']==donor['scores']['baseline_mixture']['baseline_posterior']
    assert [s['session_id'] for s in result['scans']]==[s['session_id'] for s in inputs['scans']]
    assert sum(s['evaluable'] for s in result['scans'])==3
    for scan,out in zip(inputs['scans'],result['scans']):
        planpath=ROOT/scan['plan_path'];assert hashlib.sha256(planpath.read_bytes()).hexdigest()==scan['plan_sha256'];plan=json.loads(planpath.read_text())
        for g in scan['groups']:
            expected={v['visit'] for v in plan['selected'] if v['group']==g['group'] and v['partition']=='train'}
            assert {o['visit'] for o in g['observations']}==expected and len(expected)==2
            assert abs(np.mean(g['correlation'])-1)<1e-10
        if out['evaluable']:
            assert len(out['groups'])==len(scan['groups'])
            for g in out['groups']:
                assert len(g['pair_counts'])==11 and all(n>0 for n in g['pair_counts'])
                assert g['paired_visits']==g['training_visits']+g['held_visits']
            for name in ['nominal','uniform_baseline','transferred_baseline']:assert abs(sum(out['scores'][name]['baseline_posterior'])-1)<1e-10
