import numpy as np
from solver import fit,scores


def test_multimodal_solution_beats_dense_grid_and_has_stationarity():
    for y in [np.r_[np.zeros(20),np.ones(17)*1000],np.r_[np.zeros(8),np.ones(8)*2000,np.ones(9)*4000],np.ones(10)*1e6]:
        offset,audit=fit(y)
        grid=np.linspace(min(0,y.min()),max(0,y.max()),20001)
        loss=lambda x:2.5*np.log1p(((y-x)/100)**2/4).sum()+.5*(x/1e6)**2
        assert loss(offset)<=min(loss(x) for x in grid)+1e-7
        assert audit['converged'] and audit['curvature']>0


def test_held_data_cannot_change_fitted_offset_or_training_score():
    r=np.array([[0,0,400,0,150,200],[2000,2100,1900,2000,4000,1000]],dtype=float)
    mask=np.array([True]*4+[False]*2)
    a,b,audits=scores(r,mask);r[:,~mask]+=1e7;c,d,other=scores(r,mask)
    np.testing.assert_array_equal(a,c);assert audits==other
    assert np.all(d-c<b-a)


def test_selected_real_tracks_all_reach_positive_curvature_stationarity():
    import json,hashlib
    from pathlib import Path
    here=Path(__file__).resolve().parent;reports=here.parent
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    protocol=json.loads((here/'protocol.json').read_text())
    assert protocol['source_sha256']==digest(here/'audit_stationary.py')
    assert protocol['solver_sha256']==digest(here/'solver.py')
    assert len(protocol['selected'])==43
    for name,value in protocol['input_sha256'].items():assert digest(reports/name)==value
    for session,ids in protocol['selected'].items():
        result=json.loads((here/f'{session}.json').read_text())
        assert result['complete'] and result['protocol_sha256']==digest(here/'protocol.json')
        assert sorted(t['track_id'] for t in result['tracks'])==ids
        for t in result['tracks']:
            assert t['all_converged'] and t['max_abs_gradient']<1e-7
            assert t['min_curvature']>0
            assert t['train_gain']>=-1e-5
