import json
from pathlib import Path
import numpy as np
from solver import fit,scores,reference
HERE=Path(__file__).resolve().parent


def test_multimodal_offsets_and_held_isolation():
    train=np.array([np.r_[np.zeros(20),np.ones(17)*1000],np.r_[np.zeros(17),np.ones(20)*1000]])+np.array([1e6,-2e6])[:,None]
    result,audit=fit(train)
    expected=np.array([reference.fit(row)[0] for row in train])
    np.testing.assert_allclose(result,expected,atol=1e-5,rtol=0)
    r=np.c_[train,[9000.,-9000.]];mask=np.arange(r.shape[1])<37
    a,b,_=scores(r,mask);r[:,-1]+=1e7;c,d,_=scores(r,mask)
    np.testing.assert_array_equal(a,c);assert not np.array_equal(b,d)


def test_real_scalar_equivalence_and_stationarity():
    import hashlib
    r=json.loads((HERE/'validation.json').read_text())
    assert r['complete'] and len(r['scans'])==43
    assert r['solver_sha256']==hashlib.sha256((HERE/'solver.py').read_bytes()).hexdigest()
    tracks=[t for s in r['scans'] for t in s['tracks']]
    assert len(tracks)==2526 and sum(t['candidates'] for t in tracks)==5052
    for t in tracks:
        assert t['max_gradient']<1e-7
        np.testing.assert_allclose(t['score_differences'],0,atol=1e-6,rtol=0)


def test_matched_refit_preserves_protocol_and_selection():
    import hashlib
    p=json.loads((HERE/'refit/protocol.json').read_text());oldpath=HERE.parent/'2026_09_27_ds6_continuous_phase/protocol.json';old=json.loads(oldpath.read_text())
    assert p['original_protocol_sha256']==hashlib.sha256(oldpath.read_bytes()).hexdigest()
    assert p['stationary_solver_sha256']==hashlib.sha256((HERE/'solver.py').read_bytes()).hexdigest()
    for key in old:assert p[key]==old[key]
    for arm in ['cfo_only','phase']:
        r=json.loads((HERE/'refit'/f'{arm}.json').read_text())
        assert r['complete'] and r['protocol_sha256']==hashlib.sha256((HERE/'refit/protocol.json').read_bytes()).hexdigest()
        assert r['best']==max(r['runs'],key=lambda row:row['train'])
        assert len(r['runs'])==2
        assert np.isfinite(r['exact']['train']) and np.isfinite(r['exact']['held'])


def test_winning_location_offsets_match_scalar_reference():
    import hashlib
    r=json.loads((HERE/'refit/offset-audit.json').read_text());assert r['complete']
    assert {v['arm'] for v in r['rows']}=={'cfo_only','phase'}
    for v in r['rows']:
        assert v['fit_sha256']==hashlib.sha256((HERE/'refit'/f"{v['arm']}.json").read_bytes()).hexdigest()
        assert v['candidates']==2286 and v['mismatches']==0
        assert v['maximum_loss_difference']<1e-6
