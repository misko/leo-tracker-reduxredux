import numpy as np
from curvature_position_profile import curvature, excluded_satellites, probes, finite_difference


def test_screen_optional_strict_and_satellite_scope():
    tracks=[dict(catalog_number=1, receiver=0, ratio=1.1),
            dict(catalog_number=2, receiver=0, ratio=1.01),
            dict(catalog_number=2, receiver=1, ratio=1.10001),
            dict(catalog_number=3, receiver=0, ratio=None)]
    assert excluded_satellites(tracks) == []
    assert excluded_satellites(tracks,1.1) == [2]


def test_curvature_identical_points_and_linear_invariance():
    t=np.linspace(0,60,100); noise=np.sin(t*3)
    y=.04*(t-30)**2+noise
    a=curvature(t,y);b=curvature(t,y+200+7*t)
    assert a['ratio']>1.1
    assert np.isclose(a['ratio'],b['ratio'])
    assert curvature([0]*5,range(5))['status']=='unassessed'
    assert curvature(t,2*t+1)['status']=='unassessed'


def test_probes_reproducible_and_derivatives():
    assert probes()==probes()
    assert len(probes())==15
    cells=[]
    for p in probes():
        e,n=p['east_m'],p['north_m']
        assert np.hypot(e,n)<=500
        cells.append(dict(**p,objective=10+2*e-3*n+.2*e*e+.4*n*n))
    for h in (50,100):
        d=finite_difference(cells,h)
        np.testing.assert_allclose(d['gradient_score_per_m'],[2,-3])
        np.testing.assert_allclose(d['diagonal_curvature_score_per_m2'],[.4,.8])
