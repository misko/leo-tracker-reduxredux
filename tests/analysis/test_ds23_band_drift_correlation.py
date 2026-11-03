from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_band_drift_correlation import drift_coordinate_scales,ORIGINAL_CORRELATION


@pytest.mark.parametrize('rho',[ORIGINAL_CORRELATION,0.,.5,-.4])
def test_cross_band_covariance_changes_without_changing_either_marginal(rho):
    scale=drift_coordinate_scales(rho)
    design=np.array([[10.,-.5],[10.,.5]])*scale
    covariance=design@design.T
    np.testing.assert_allclose(covariance,100.25*np.array([[1.,rho],[rho,1.]]),rtol=1e-13,atol=1e-12)


def test_original_prior_coordinates_are_exact_null():
    np.testing.assert_array_equal(drift_coordinate_scales(ORIGINAL_CORRELATION),np.ones(2))


@pytest.mark.parametrize('rho',[1.,-1.,np.nan,np.inf])
def test_singular_or_nonfinite_prior_is_rejected(rho):
    with pytest.raises(ValueError):drift_coordinate_scales(rho)
