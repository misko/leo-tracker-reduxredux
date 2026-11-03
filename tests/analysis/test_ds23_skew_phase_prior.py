import numpy as np
import pytest
from scipy.integrate import quad

from ds23_skew_phase_prior import side_scales,density_cost
from learn_ds23_causal_phase_forecast import distribution_cost


@pytest.mark.parametrize('nu',[None,3.,8.])
def test_zero_asymmetry_is_the_existing_normalized_law(nu):
    values=np.linspace(-5,5,31)
    np.testing.assert_allclose(density_cost(values,np.ones(31),1.,nu,0.),
                               distribution_cost(values,np.ones(31),1.,nu),atol=1e-12)


@pytest.mark.parametrize('nu,kappa',[(3.,.5),(8.,-.4),(None,.6)])
def test_asymmetry_preserves_mass_and_variance_and_has_expected_mean(nu,kappa):
    pdf=lambda x:float(np.exp(-.5*density_cost(x,1.,1.,nu,kappa)))
    mass=quad(pdf,-np.inf,0,epsabs=1e-9)[0]+quad(pdf,0,np.inf,epsabs=1e-9)[0]
    mean=quad(lambda x:x*pdf(x),-np.inf,0,epsabs=1e-9)[0]+quad(lambda x:x*pdf(x),0,np.inf,epsabs=1e-9)[0]
    second=quad(lambda x:x*x*pdf(x),-np.inf,0,epsabs=1e-9)[0]+quad(lambda x:x*x*pdf(x),0,np.inf,epsabs=1e-9)[0]
    assert abs(mass-1)<1e-8
    assert abs(mean-side_scales(kappa,nu)[2])<1e-8
    assert abs(second-mean*mean-1)<1e-8
