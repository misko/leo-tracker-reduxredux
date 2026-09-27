import numpy as np

from audit_clock import basis,fit_clock,score,fit_offset


def test_complete_frozen_dataset_and_numerical_convergence():
    import json
    from audit_clock import HERE,REPORTS,digest
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(HERE/'audit_clock.py')==protocol['source_sha256']
    for name,value in protocol['files'].items():
        assert digest(REPORTS/name)==value
    assert len(protocol['sessions'])==len(set(protocol['sessions']))==43
    for session in protocol['sessions']:
        result=json.loads((HERE/f'{session}.json').read_text())
        earlier=json.loads((REPORTS/'2026_09_27_ds6_clock_curvature'/f'{session}.json').read_text())
        assert result['complete']
        assert result['protocol_sha256']==digest(HERE/'protocol.json')
        assert result['assignments']==earlier['assignments']
        assert all(v['converged'] for v in result['arms'].values())
        assert result['iteration_audit']['converged']
        assert abs(result['iteration_audit']['held_change'])<1e-6
        assert abs(result['iteration_audit']['train_change'])<1e-6


def test_constant_time_still_converges_track_offset():
    y=np.array([0.,0.,0.,400.,0.,0.,0.,400.]);mask=np.ones(8,dtype=bool)
    row=dict(receiver_id=0,time=np.ones(8)*100,rf_hz=11.2e9,mask=mask,residual=y)
    _,offsets,converged=fit_clock([row],2)
    assert converged
    np.testing.assert_allclose(offsets,[fit_offset(y)],atol=1e-5)


def test_clock_recovers_injected_curve_without_held_leakage():
    rows=[]
    for rx in [0,1]:
        for start in [0.,60.,120.,180.,240.]:
            # Enough training information for the stated 5 Hz recovery gate
            # despite the fixed 750 Hz coefficient prior.
            times=np.linspace(start,start+55,100);mask=np.arange(100)%2==0;rf=10.71e9
            x=basis(times,mask,rf,2);beta=np.array([300.,-400.])*(rx+1)
            rows.append(dict(receiver_id=rx,time=times,rf_hz=rf,mask=mask,residual=12345.+x@beta))
    coefficients,offsets,converged=fit_clock(rows,2)
    assert converged
    for rx in [0,1]:np.testing.assert_allclose(coefficients[rx],np.array([300.,-400.])*(rx+1),atol=5.)
    # Check the penalized objective is stationary, including track offsets.
    for rx in [0,1]:
        for j in range(2):
            plus={k:v.copy() for k,v in coefficients.items()}
            minus={k:v.copy() for k,v in coefficients.items()}
            plus[rx][j]+=.01;minus[rx][j]-=.01
            gradient=(score(rows,2,plus,offsets)['penalized_train']-score(rows,2,minus,offsets)['penalized_train'])/.02
            assert abs(gradient)<1e-6
    changed=[dict(r,residual=r['residual']+np.where(r['mask'],0.,1e6)) for r in rows]
    other,other_offsets,_=fit_clock(changed,2)
    for rx in [0,1]:np.testing.assert_array_equal(coefficients[rx],other[rx])
    np.testing.assert_array_equal(offsets,other_offsets)
    assert score(changed,2,other,other_offsets)['held']<score(rows,2,coefficients,offsets)['held']
