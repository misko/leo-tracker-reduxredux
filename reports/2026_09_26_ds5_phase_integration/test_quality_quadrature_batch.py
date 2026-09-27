import numpy as np
from quality_quadrature_batch import batch_evidence
from quality_offset_quadrature import offset_evidence

def test_scaled_batch_matches_independent_log_recursion():
    r=np.array([[0.,3.,1.,60.,40.,15.],[100.,103.,101.,160.,140.,115.]])
    scales=[5,50];t=np.arange(6.);f=np.array([0,0,1,0,0,0],bool)
    actual=batch_evidence(r,scales,t,f,nodes=64,warmup=3)
    for m,name in enumerate(('generic','timing_informed')):
        for h in range(2):np.testing.assert_allclose(actual[m,h],offset_evidence(r[h],scales,t,f,name,nodes=64,warmup=3),atol=1e-11)

def test_future_values_do_not_change_past_batch_scores():
    r=np.array([[0.,3.,1.,60.,40.,15.]])
    t=np.arange(6.);f=np.zeros(6,bool)
    a=batch_evidence(r,[5,50],t,f,nodes=16,warmup=3);r[:,4:]+=1000;f[4:]=True
    b=batch_evidence(r,[5,50],t,f,nodes=16,warmup=3)
    np.testing.assert_array_equal(a[...,:4],b[...,:4])

def test_physical_rf_delay_sign_and_lo_cancellation():
    from physical_phase_audit import case
    for baseline,start in ((0.,0),(.3,63),(.6,0)):
        r=case(baseline,start)
        assert r['both_qualified']
        assert abs(r['error_rad'])<.01
        assert max(abs(f-75) for f in r['residual_frequency_hz'])<1
