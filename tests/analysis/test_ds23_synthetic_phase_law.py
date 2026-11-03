from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_synthetic_phase_law import unit_variance_law,bounded_phase_draw
from learn_ds23_causal_phase_forecast import distribution_cost


@pytest.mark.parametrize('nu',[None,3.,4.,8.,16.])
def test_density_matches_frozen_normalized_prior_and_variance(nu):
    z=np.array([-4.,-1.,0.,1.,4.]);law=unit_variance_law(nu)
    np.testing.assert_allclose(-2*law.logpdf(z),distribution_cost(z,np.ones(len(z)),1.,nu),rtol=1e-13,atol=1e-13)
    assert abs(law.var()-1.)<1e-14


def test_truncated_draw_matches_conditional_original_density_quantiles():
    law=unit_variance_law(3.);means=np.array([0.,14.]);sigma=np.array([2.,4.]);u=np.array([.1,.8])
    phi=bounded_phase_draw(means,sigma,3.,u)
    low=law.cdf((-15-means)/sigma);high=law.cdf((15-means)/sigma)
    np.testing.assert_allclose((law.cdf((phi-means)/sigma)-low)/(high-low),u,atol=1e-12)
    assert np.all((phi>-15)&(phi<15))


def test_nonexistent_variance_is_rejected():
    with pytest.raises(ValueError):unit_variance_law(2.)
