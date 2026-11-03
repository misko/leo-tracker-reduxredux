"""Checks for the diagnostic derivative used in the two-outlier review."""

import numpy as np

from review_ds23_worst_outliers import central_design


def test_position_design_differentiates_mean_with_coefficients_fixed():
    coefficients=np.array([2.,-3.])
    def prediction(x):
        return np.array([[x[0]**2,x[1]],[x[0]*x[1],x[1]**2]])@coefficients
    x=np.array([.4,-.7])
    expected=np.array([[4*x[0],-3],[2*x[1],2*x[0]-6*x[1]]])
    np.testing.assert_allclose(central_design(prediction,x,.02),expected,rtol=1e-10,atol=1e-10)
