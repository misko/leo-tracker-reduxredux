import numpy as np
import pytest

from ds23_orbital_phase_forecast import argument_latitude, fit_model, prediction


def test_argument_latitude_tracks_known_orbit_and_ignores_node_longitude():
    inclination=.9
    for u in (-2.,-.5,0.,1.,2.9):
        r=np.array([np.cos(u),np.sin(u)*np.cos(inclination),np.sin(u)*np.sin(inclination)])
        v=np.array([-np.sin(u),np.cos(u)*np.cos(inclination),np.cos(u)*np.sin(inclination)])
        for node in (0.,.7,2.):
            rotate=np.array([[np.cos(node),-np.sin(node),0.],[np.sin(node),np.cos(node),0.],[0.,0.,1.]])
            assert argument_latitude(rotate@r,rotate@v)==pytest.approx(u)
    with pytest.raises(ValueError,match='non-equatorial'):
        argument_latitude([1,0,0],[0,1,0])


def test_mean_harmonic_recovers_signal_without_changing_baseline_density():
    rng=np.random.default_rng(871)
    angle=np.linspace(-np.pi,np.pi,1000)
    rows=[dict(argument_latitude_rad=a,predicted_sigma_s=1.,unit_forecast_s=0.,
               next_innovation_s=.7*np.sin(a)-.3*np.cos(a)+noise)
          for a,noise in zip(angle,rng.normal(0,.2,len(angle)),strict=True)]
    model=dict(shrinkage=0.,multiplier=1.,nu=None)
    fitted=fit_model(rows,model)
    assert fitted['width']==2
    assert fitted['beta']==pytest.approx([.7,-.3],abs=.03)
    assert model==dict(shrinkage=0.,multiplier=1.,nu=None)
    for row in rows:
        row['unit_forecast_s']=100
    assert np.max(abs(prediction(rows,dict(model,shrinkage=1.),[3.,3.])))<=3
