import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('geographic', HERE/'run.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_shared_baseline_independent_clocks_by_enumeration():
    rng = np.random.default_rng(14)
    scans = []
    for _ in range(3):
        tr = rng.normal(size=(2, 3))
        scans.append(dict(train=tr, joint=tr-rng.uniform(size=(2, 3)),
                          cfo_train=rng.normal(size=3), cfo_joint=rng.normal(size=3)))
    result = m.combine(scans)
    def evidence(key):
        return np.mean([np.exp(sum(scans[s][key][b,t] for s,t in enumerate(ts)))
                        for b in range(2) for ts in itertools.product(range(3), repeat=3)])
    np.testing.assert_allclose(result['phase']['train'], np.log(evidence('train')))
    np.testing.assert_allclose(result['phase']['held'], np.log(evidence('joint')/evidence('train')))
    np.testing.assert_allclose(result['cfo_only']['train'], sum(np.log(np.mean(np.exp(s['cfo_train']))) for s in scans))


def test_center_reproduces_previous_group_factors():
    center = json.loads((HERE/'point-4.json').read_text())
    prior = json.loads((HERE.parent/'2026_09_27_ds6_expanded_association/results.json').read_text())
    rows = [s for s in prior['scans'] if s['evaluable']]
    for new, old in zip(center['scans'], rows):
        assert new['session_id'] == old['session_id']
        assert len(new['groups']) == len(old['groups'])
        for a,b in zip(new['groups'],old['groups']):
            assert a['pair_counts'] == b['pair_counts']
            for key in ['train','joint','cfo_train','cfo_joint']:
                np.testing.assert_allclose(a[key],b[key],atol=1e-9,rtol=0)


def test_complete_frozen_screen():
    protocol = json.loads((HERE/'protocol.json').read_text())
    inputs = HERE.parent/'2026_09_27_ds6_expanded_association/inputs.json'
    assert hashlib.sha256(inputs.read_bytes()).hexdigest() == protocol['inputs_sha256']
    source = HERE.parent/'2026_09_27_ds6_expanded_association/protocol.json'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == protocol['source_protocol_sha256']
    members = json.loads(inputs.read_text())['scans']
    for p in protocol['points']:
        r = json.loads((HERE/f"point-{p['index']}.json").read_text())
        assert r['complete'] and r['point'] == p
        assert r['protocol_sha256'] == hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
        assert [s['session_id'] for s in r['scans']] == [s['session_id'] for s in members if s['groups']]
        assert [s['session_id'] for s in r['unavailable']] == [s['session_id'] for s in members if not s['groups']]
        np.testing.assert_allclose(sum(r['scores']['baseline_posterior']),1)
