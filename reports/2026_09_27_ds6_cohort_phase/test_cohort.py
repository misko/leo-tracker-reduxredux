import json
import numpy as np
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('cohort',HERE/'run.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);fresh=module.fresh;phase=module.phase


def test_phase_correction_uses_identical_frequency_model():
    p=json.loads((ROOT/'2026_09_27_ds6_fresh_joint43/protocol.json').read_text());r=json.loads((ROOT/'2026_09_27_ds6_fresh_joint43/all.json').read_text());pm=phase.Model();x=r['best']['x'];indices=[r['sessions'].index(b['scan']['session_id'])+2 for b in pm.banks];scale=(6371.0088*np.pi/180)/111.195
    value=held=0.
    for b,i in zip(pm.banks,indices):
        m=fresh.load_model(b['scan']['session_id'],p['center'])[0];s=m.evaluate(np.array([x[0],x[1],x[i]]),False);value+=s['train'];held+=s['held']
    result=pm.evaluate(np.r_[np.array(x[:2])*scale,np.array(x)[indices]],'cfo_only')
    np.testing.assert_allclose(result['train'],value,atol=1e-6,rtol=0)
    np.testing.assert_allclose(result['held'],held,atol=1e-6,rtol=0)


def test_completed_partitions_and_phase_membership():
    parent=json.loads((ROOT/'2026_09_27_ds6_fresh_joint43/protocol.json').read_text())
    for name in ['all','A','B']:
        pp=HERE/f'{name}-protocol.json';p=json.loads(pp.read_text());r=json.loads((HERE/f'{name}.json').read_text())
        assert p['sessions']==parent['splits'][name]
        assert set(p['phase_sessions'])<=set(p['sessions'])
        assert r['complete'] and r['protocol_sha256']==fresh.digest(pp)
        for arm in ['cfo_only','phase']:
            assert np.isfinite(r['results'][arm]['train'])
            assert len(r['results'][arm]['x'])==len(p['sessions'])+2
