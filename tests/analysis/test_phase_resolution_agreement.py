import numpy as np
import pytest
from scipy.special import logsumexp
from scipy.stats import norm
from leo.analysis.research.predictive_track import phase_resolution_agreement


def density(x,step):
    phi=np.arange(-8,8+step/2,step);prior=norm.logpdf(phi)
    return -2*(logsumexp(prior+norm.logpdf(x+phi,scale=.02))-logsumexp(prior))


def test_coarse_phase_integration_is_detected_against_continuous_gaussian_oracle():
    x=np.array([.04,.065,.015,.04,.04])
    coarse=np.array([[density(z,h) for h in [.1,.05,.025]] for z in x])
    assert not phase_resolution_agreement(coarse)['local_agreement']
    fine=np.array([[density(z,h) for h in [.01,.005,.0025]] for z in x])
    np.testing.assert_allclose(fine[:,-1],-2*norm.logpdf(x,scale=np.sqrt(1+.02**2)),atol=1e-10)
    assert phase_resolution_agreement(fine)['local_agreement']
    with pytest.raises(ValueError):phase_resolution_agreement(np.ones((2,3)))
    with pytest.raises(ValueError):phase_resolution_agreement(fine,spacing_km=np.nan)
