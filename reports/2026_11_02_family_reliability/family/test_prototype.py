"""Covariance and Gaussian normalization checks for report-local prototype."""
import numpy as np
import pytest
from prototype import scaled_mode_bank
from dsx01_joint_marginal import integrated_gaussian


def test_scaled_covariance_changes_only_selected_physical_modes():
    bank = dict(time_s=np.arange(4), position_km=np.arange(72.).reshape(6,4,3),
                velocity_km_s=np.arange(72.,144.).reshape(6,4,3))
    original = bank['position_km'].copy()
    result = scaled_mode_bank(bank, 1, 4.)
    np.testing.assert_array_equal(bank['position_km'], original)
    np.testing.assert_array_equal(result['position_km'][:3], original[:3])
    np.testing.assert_allclose(result['position_km'][3:], 4*original[3:])
    a = original[3:].reshape(3,-1).T
    b = result['position_km'][3:].reshape(3,-1).T
    np.testing.assert_allclose(b@b.T, 16*a@a.T)


@pytest.mark.parametrize('scale', [1.,2.,4.])
def test_low_rank_cost_matches_dense_normalized_gaussian(scale):
    rng = np.random.default_rng(70211)
    y = rng.normal(size=17); u = rng.normal(size=(17,5)); s = np.linspace(.7,1.4,17)
    u[:,2:] *= scale
    fit = integrated_gaussian(y,u,s)
    covariance = np.diag(s*s)+u@u.T
    dense = y@np.linalg.solve(covariance,y)+np.linalg.slogdet(covariance)[1]+len(y)*np.log(2*np.pi)
    lowrank = fit['quadratic']+fit['logvolume']+2*np.log(s).sum()+len(y)*np.log(2*np.pi)
    assert lowrank == pytest.approx(dense, abs=1e-10)


def test_zero_residual_larger_covariance_has_volume_penalty():
    u = np.eye(5)[:,:3]
    small = integrated_gaussian(np.zeros(5), u, 1.)
    large = integrated_gaussian(np.zeros(5), 4*u, 1.)
    assert large['quadratic'] == small['quadratic'] == 0
    assert large['logvolume'] > small['logvolume']
