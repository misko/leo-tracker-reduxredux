import importlib.util
import itertools
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('joint',HERE/'run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_pair_factor_counts_each_frequency_once():
    a=np.array([-1.,-4.]);b=np.array([-2.,-3.,-5.]);zero=np.zeros((2,3,4))
    np.testing.assert_allclose(m.coupled(a,b,zero),logsumexp(a)+logsumexp(b))
    f=np.arange(24).reshape(2,3,4)/30
    brute=np.array([np.log(sum(np.exp(a[i]+b[j]+f[i,j,k]) for i,j in itertools.product(range(2),range(3)))) for k in range(4)])
    np.testing.assert_allclose(m.coupled(a,b,f),brute)
    # Replacing independent pair sums inside a larger evidence leaves all
    # other track contributions unchanged.
    other=-7.
    np.testing.assert_allclose(other+logsumexp(a)+logsumexp(b)+m.coupled(a,b,f)-logsumexp(a)-logsumexp(b),other+brute)


def test_frozen_inputs_disjoint_groups_and_complete_grid():
    p=json.loads((HERE/'protocol.json').read_text());r=json.loads((HERE/'results.json').read_text())
    assert r['complete'] and r['protocol_sha256']==m.sha(HERE/'protocol.json')
    path=HERE.parent/'2026_09_27_ds6_expanded_association/inputs.json'
    assert m.sha(path)==p['inputs_sha256'];inputs=json.loads(path.read_text())
    members=[]
    for scan in inputs['scans']:
        if not scan['groups']:continue
        members.append(scan['session_id']);used=[tid for g in scan['groups'] for tid in g['track_ids']]
        assert len(used)==len(set(used))
        plan=HERE.parent/scan['plan_path'];assert m.sha(plan)==scan['plan_sha256']
        data=json.loads(plan.read_text());tracks={t['track_id']:t for t in data['tracks']}
        for g in scan['groups']:
            for obs in g['observations']:
                for tid in g['track_ids']:
                    t=tracks[tid];assert t['training_mask'][t['visits'].index(obs['visit'])]
    assert len(r['points'])==9
    for result,point in zip(r['points'],p['grid']['points']):
        assert result['point']==point
        assert [s['session_id'] for s in result['scans']]==members
        assert sum(s['tracks'] for s in result['scans'])==174
        assert all(np.isfinite(result['scores'][arm][key]) for arm in ['cfo_only','phase'] for key in ['train','held'])


def test_timing_audit_preserves_all_other_inputs():
    original=json.loads((HERE/'protocol.json').read_text());quarter=json.loads((HERE/'quarter/protocol.json').read_text())
    assert quarter.pop('parent_protocol_sha256')==m.sha(HERE/'protocol.json')
    quarter.pop('timing_audit')
    assert len(quarter['grid']['timing_s'])==41
    quarter['grid']['timing_s']=original['grid']['timing_s'];assert quarter==original
    result=json.loads((HERE/'quarter/results.json').read_text())
    assert result['complete'] and result['protocol_sha256']==m.sha(HERE/'quarter/protocol.json')
    assert len(result['points'])==9
    for p in result['points']:
        for s in p['scans']:
            assert np.shape(s['train'])==(42,41)
            assert np.shape(s['cfo_train'])==(41,)
