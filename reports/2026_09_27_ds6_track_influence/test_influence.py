import numpy as np
from run_influence import derivatives,deletion_shift,choose


def test_quadratic_influence_matches_exact_deletion_solution():
    matrices=np.array([np.diag([2.,3.,4.]),np.diag([4.,5.,3.]),[[3.,.3,0],[.3,2.,.1],[0,.1,6.]]])
    targets=np.array([[1.,2.,.2],[-1.,.4,-.3],[.2,-.4,1.]])
    info=matrices.sum(axis=0);rhs=np.einsum('nij,nj->i',matrices,targets);x=np.linalg.solve(info,rhs)
    def loss(z):
        d=z-targets
        return .5*np.einsum('ni,nij,nj->n',d,matrices,d)
    _,g,h=derivatives(loss,x,np.array([.05,.05,.01]))
    np.testing.assert_allclose(h,matrices,atol=1e-9)
    np.testing.assert_allclose(g.sum(axis=0),0,atol=1e-10)
    for i in range(3):
        predicted=deletion_shift(g[i]-g.sum(axis=0),h.sum(axis=0)-h[i])
        exact=np.linalg.solve(info-matrices[i],rhs-matrices[i]@targets[i])-x
        np.testing.assert_allclose(predicted,exact,atol=1e-8)


def test_singular_information_is_explicit_and_selection_is_stable():
    assert deletion_shift(np.ones(3),np.diag([1.,1.,0.])) is None
    rows=[dict(track_id=str(i),predicted_shift=[0,0,0],predicted_horizontal_km=float(i)) for i in range(9)]
    a,b=choose(rows,'scan',2026092737)
    assert a==['8','7','6']
    assert not set(a)&set(b) and len(b)==3
    assert (a,b)==choose(list(reversed(rows)),'scan',2026092737)


def test_complete_frozen_deletions_and_propagation():
    import json
    from run_influence import HERE,REPORTS,digest
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(HERE/'run_influence.py')==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    assert len(protocol['sessions'])==4
    for session in protocol['sessions']:
        result=json.loads((HERE/f'{session}.json').read_text())
        assert result['complete'] and result['protocol_sha256']==digest(HERE/'protocol.json')
        top,random=choose(result['tracks'],session,protocol['seed'])
        assert result['selected']==dict(influence=top,random_control=random)
        assert [r['track_id'] for r in result['fits']]==top+random
        for fit in result['fits']:
            assert len(fit['runs'])==2
            assert fit['best']==max(fit['runs'],key=lambda r:r['train'])
            np.testing.assert_allclose(fit['actual_shift'],np.array(fit['best']['x'])-result['baseline_x'])
            assert fit['maximum_interpolation_error_hz']<.05
            assert np.isfinite(fit['exact_omitted_held_gain']) and np.isfinite(fit['exact_retained_held_gain'])
