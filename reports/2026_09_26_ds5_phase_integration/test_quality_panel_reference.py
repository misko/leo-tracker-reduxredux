import numpy as np
from causal_quality_accuracy import exact_evidence
from quality_panel_reference import panel_evidence


def test_panel_matches_exact_histories():
    r=np.array([0.,3.,1.,60.,40.,15.]); scales=[5.,50.]; t=np.arange(6.); flags=[False,False,True,False,False,False]
    for kind in ['stationary','generic','timing_informed']:
        expected=exact_evidence(r,scales,t,flags,kind)
        actual,_=panel_evidence(r,scales,t,flags,kind,order=12)
        assert abs(actual[-1]-expected)<1e-6


def test_future_panel_placement_preserves_prefix_integrals():
    r=np.array([-800000.,-799997.,-799999.,-799940.,-799960.,-799985.]);scales=[5.,50.];t=np.arange(6.);flags=np.zeros(6,bool)
    a,_=panel_evidence(r,scales,t,flags,'generic',order=12)
    changed=r.copy();changed[-2:]+=5000
    b,_=panel_evidence(changed,scales,t,flags,'generic',order=12)
    assert np.max(abs(a[:4]-b[:4]))<1e-6


def test_all_ten_scales_and_large_receiver_offset():
    r=np.array([-800000.,-799999.,-799950.,-799900.]);scales=3.125*2.**np.arange(10);t=np.arange(4.);flags=[False,True,False,False]
    for kind in ['generic','timing_informed']:
        expected=exact_evidence(r,scales,t,flags,kind)
        actual,_=panel_evidence(r,scales,t,flags,kind,order=12)
        assert abs(actual[-1]-expected)<1e-6
