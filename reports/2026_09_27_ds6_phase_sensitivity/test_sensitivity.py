import importlib.util
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('sensitivity',Path(__file__).with_name('run.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_profiled_intercepts_match_schur_complement():
    rng=np.random.default_rng(42);g=rng.normal(size=(8,2));x=np.column_stack([g,np.ones(8)])
    fisher=x.T@x;profiled=fisher[:2,:2]-np.outer(fisher[:2,2],fisher[2,:2])/fisher[2,2]
    centered=m.remove_offsets(g)
    np.testing.assert_allclose(centered.T@centered,profiled,atol=1e-12)
    np.testing.assert_allclose(m.remove_offsets(g+[100,-50]),centered,atol=1e-12)


def test_geometric_gradient_matches_independent_one_sided_limit():
    lat,lon=37.8,-122.4;origin=m.geodetic_to_ecef_km(lat,lon,0)
    p=origin+np.array([[[700.,200.,900.],[690.,210.,900.]],[[800.,-300.,700.],[790.,-310.,700.]]])
    analytic=m.gradient(p,lat,lon,11.2e9,.1)
    h=.001;dl=np.degrees(h/6371.0088);de=dl/np.cos(np.radians(lat));base=m.phase(p,lat,lon,11.2e9)
    one=np.column_stack([(m.phase(p,lat,lon+de,11.2e9)-base)/h,(m.phase(p,lat+dl,lon,11.2e9)-base)/h])
    np.testing.assert_allclose(analytic,one,rtol=2e-5,atol=1e-8)


def test_information_scaling():
    g=np.array([[1.,0.],[0.,2.]])
    a=m.information([g]);b=m.information([g,g])
    np.testing.assert_allclose(b['weak_axis_sigma_km_at_1deg'],a['weak_axis_sigma_km_at_1deg']/np.sqrt(2))
