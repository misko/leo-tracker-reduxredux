import importlib.util
import json
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('audit',HERE/'run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_scalar_multimodal_stationarity_and_score():
    train=np.r_[np.zeros(20),np.ones(17)*1000];offset,a=m.solver.fit(train)
    assert a['converged'] and a['curvature']>0
    row=np.r_[train,3000.];mask=np.arange(len(row))<len(train)
    score=m.score(row,mask,offset)[0]
    grid=np.linspace(-10,1010,4001)
    assert score>=max(m.score(row,mask,x)[0] for x in grid)-1e-7
    row[-1]+=1e6;assert m.score(row,mask,offset)[0]==score


def test_complete_pooled_stationarity_audit():
    p=json.loads((HERE/'protocol.json').read_text());r=json.loads((HERE/'results.json').read_text())
    assert r['complete'] and r['protocol_sha256']==m.fresh.digest(HERE/'protocol.json')
    assert p['fit_sha256']==m.fresh.digest(HERE.parent/'2026_09_27_ds6_cohort_phase/all.json')
    assert p['solver_sha256']==m.fresh.digest(HERE.parent/'2026_09_27_ds6_stationary_offsets/solver.py')
    assert [s['session_id'] for s in r['scans']]==p['sessions'] and len(r['scans'])==43
    for s in r['scans']:
        for t in s['tracks']:
            assert 1<=len(t['candidates'])<=2
            assert t['candidates'][0]['old_train']>=t['candidates'][-1]['old_train']
            for c in t['candidates']:
                assert c['converged'] and abs(c['gradient'])<1e-7 and c['curvature']>0
                assert c['new_train']>=c['old_train']-1e-6
