import numpy as np
from audit import refine


def test_constant_and_symmetric_residuals_and_held_isolation():
    residual=np.array([[1000.,1100.,900.,1000.,1200.,800.],[2000.,2000.,2000.,2000.,2000.,2000.]])
    mask=np.array([True,True,True,True,False,False]);a,b,c,n=refine(residual,mask)
    assert c.all()
    changed=residual.copy();changed[:,~mask]+=1e6
    d,e,f,m=refine(changed,mask)
    np.testing.assert_array_equal(a,d);np.testing.assert_array_equal(n,m)
    assert np.all(e-d<b-a)


def test_iteration_limit_and_translation_are_explicit():
    residual=np.array([[0.,0.,0.,400.,0.,400.]])+1e6
    mask=np.array([True,True,True,True,False,False])
    _,_,converged,steps=refine(residual,mask,limit=1)
    assert not converged[0] and steps[0]==1
    a,b,c,n=refine(residual,mask)
    d,e,f,m=refine(residual-1e6,mask)
    assert c.all() and f.all()
    # Constant translation affects only the preserved offset penalty.
    np.testing.assert_allclose(b-a,e-d,atol=1e-9)
    np.testing.assert_array_equal(n,m)


def test_all43_frozen_inputs_and_finite_results():
    import json
    from audit import HERE,REPORTS,digest
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(HERE/'audit.py')==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    assert len(set(protocol['sessions']))==43
    for session in protocol['sessions']:
        result=json.loads((HERE/f'{session}.json').read_text())
        assert result['complete'] and result['protocol_sha256']==digest(HERE/'protocol.json')
        assert np.isfinite(result['total_train_gain']) and np.isfinite(result['total_held_gain'])
        assert result['unconverged_visible']==0
        assert result['total_train_gain']==sum(t['train_gain'] for t in result['tracks'])
