import importlib.util
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
import pytest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('continuous',HERE/'run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


@pytest.fixture(scope='module')
def model():return m.Model()


def test_matches_grid_at_fixed_clocks(model):
    grid=json.loads((HERE.parent/'2026_09_27_ds6_joint_phase/quarter/results.json').read_text())
    row=grid['points'][2];x=model.protocol['starts'][0];indices=[round((v+5)*4) for v in x[2:]]
    for arm in ['cfo_only','phase']:
        if arm=='cfo_only':
            train=sum(s['cfo_train'][i] for s,i in zip(row['scans'],indices));joint=sum(s['cfo_joint'][i] for s,i in zip(row['scans'],indices))
        else:
            train=logsumexp(sum(np.array(s['train'])[:,i] for s,i in zip(row['scans'],indices)))-np.log(42)
            joint=logsumexp(sum(np.array(s['joint'])[:,i] for s,i in zip(row['scans'],indices)))-np.log(42)
        actual=model.evaluate(x,arm)
        np.testing.assert_allclose(actual['train'],train,atol=1e-8,rtol=0)
        np.testing.assert_allclose(actual['held'],joint-train,atol=1e-8,rtol=0)


def test_held_values_cannot_choose_fit(model):
    x=model.protocol['starts'][0];before=model.evaluate(x,'phase');saved=[]
    try:
        for bank in model.banks:
            for b in bank['tracks'].values():
                saved.append((b,b['t']['measured_hz']))
                y=np.array(b['t']['measured_hz']);y[~b['mask']]+=3000;b['t']['measured_hz']=y.tolist()
        after=model.evaluate(x,'phase')
        assert before['train']==after['train']
        assert abs(before['held']-after['held'])>1
    finally:
        for b,y in saved:b['t']['measured_hz']=y


def test_completed_fits():
    for arm in ['cfo_only','phase']:
        r=json.loads((HERE/f'{arm}.json').read_text())
        assert r['complete'] and r['protocol_sha256']==m.joint.sha(HERE/'protocol.json')
        assert r['best']==max(r['runs'],key=lambda x:x['train'])
        assert np.isfinite(r['exact']['train']) and np.isfinite(r['exact']['held'])
        assert r['maximum_interpolation_error_hz']<.1


def test_full_catalogue_coverage_accounts_for_every_track():
    for arm in ['cfo_only','phase']:
        audit=json.loads((HERE/f'{arm}-coverage.json').read_text())
        assert audit['complete'] and audit['fit_sha256']==m.joint.sha(HERE/f'{arm}.json')
        assert len(audit['rows'])==174
        assert len({(r['session_id'],r['track_id']) for r in audit['rows']})==174
        for r in audit['rows']:
            assert -.00000001<=r['log_evidence_loss']
            np.testing.assert_allclose(r['retained_training_mass'],np.exp(-r['log_evidence_loss']))
        np.testing.assert_allclose(audit['cfo_log_evidence_loss'],sum(r['log_evidence_loss'] for r in audit['rows']))
