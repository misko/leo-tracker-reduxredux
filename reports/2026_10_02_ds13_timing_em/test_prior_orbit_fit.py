import numpy as np
from sgp4.api import Satrec,WGS72
from prior_orbit_fit import modified_satellite,folds


def example():
    sat=Satrec()
    sat.sgp4init(WGS72,'i',12345,28000.,1e-5,0.,0.,.001,.3,.9,1.2,.065,.4)
    return sat


def test_zero_perturbation_replays_state():
    base=example();other=modified_satellite(base,0.,base.jdsatepoch+.5)
    for t in (0.,.2,1.):
        a=base.sgp4(base.jdsatepoch,t);b=other.sgp4(base.jdsatepoch,t)
        assert a[0]==b[0]==0
        np.testing.assert_allclose(a[1:],b[1:],atol=1e-9,rtol=0)


def test_mean_motion_preserves_keplerian_phase_at_anchor():
    base=example();anchor=base.jdsatepoch+base.jdsatepochF+.3
    other=modified_satellite(base,.001,anchor)
    minutes=(anchor-base.jdsatepoch-base.jdsatepochF)*1440
    assert np.isclose(other.no_kozai-base.no_kozai,.001*2*np.pi/1440,rtol=1e-8)
    assert np.isclose(other.mo+other.no_kozai*minutes,base.mo+base.no_kozai*minutes)


def test_blocked_folds_cover_points_and_have_guard():
    t=np.linspace(0,80,161);seen=np.zeros(len(t),int)
    for train,test in folds(t):
        seen+=test
        assert not np.any(train&test)
        assert np.all(np.min(abs(t[train,None]-t[None,test]),axis=1)>1)
    assert np.all(seen==1)
