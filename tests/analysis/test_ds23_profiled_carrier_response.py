import copy
import numpy as np
import pytest

from ds23_joint_component_refinement import JointComponentWorkspace
from ds23_differential_rf_epoch import inject_component_rates
from ds23_profiled_carrier_response import tight_fit,observed_rate_response


def workspace():
    rng=np.random.default_rng(20261022);n=50000;fs=2.5e6
    fits=[dict(CFO_hz=12000.,offset_samples=.12,modulation_ppm=2.),
          dict(CFO_hz=-28000.,offset_samples=-.17,modulation_ppm=-3.)]
    p=JointComponentWorkspace(rng.normal(size=n)+1j*rng.normal(size=n),fs,'upper',[100.,800.],fits)
    (a,_),(b,_)=[p.columns_and_derivatives(v,k) for k,v in enumerate(p.start.reshape(2,3))]
    for segment in p.segments:
        c=10*(rng.normal(size=17)+1j*rng.normal(size=17))
        p.y[segment]+=np.column_stack((a[segment],b[segment],np.ones(len(segment))))@c
    return p


def test_tight_profile_improves_score_and_retains_native_bounds():
    p=workspace();start=p.start.copy();start[[0,3]]+=[4.,-5.]
    before=p.statistics(start);fit=tight_fit(p,start)
    assert fit['score']>before['score'] and not fit['boundary']
    assert fit['maximum_standardized_score']<.01
    assert np.max(abs(np.asarray(fit['parameters'])[[0,3]]-p.start[[0,3]]))<3


def test_observed_curvature_predicts_refitted_frequency_ramp():
    p=workspace();fit=tight_fit(p,p.start);parameters=np.asarray(fit['parameters'])
    response=observed_rate_response(p,parameters)
    assert response['minimum_eigenvalue']>0 and response['hessian_asymmetry']<.01
    fits=[]
    for sign in [-1,1]:
        view=copy.copy(p);view.y=inject_component_rates(p,parameters,[sign*1000.,0.])
        fits.append(tight_fit(view,parameters))
    actual=(fits[1]['difference_hz']-fits[0]['difference_hz'])/2
    assert abs(actual-response['response_s'][0]*1000.)<.1


def test_invalid_profile_coordinates_rejected():
    p=workspace()
    with pytest.raises(ValueError):tight_fit(p,[1.,2.])
