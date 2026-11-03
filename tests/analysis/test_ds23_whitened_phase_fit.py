import numpy as np

from ds23_whitened_phase_fit import curvature_whitener,minimize_whitened


def test_curvature_scaling_recovers_correlated_quadratic_and_original_bounds():
    h=np.array([[1e4,99.],[99.,1.]])
    center=np.array([2.,-3.]);scale=np.array([.1,10.])
    def statistics(p):
        residual=p-center
        return dict(NLL=float(.5*residual@h@residual),gradient_scaled=scale*(h@residual))
    whitener,receipt=curvature_whitener(statistics,np.array([0.,0.]),scale)
    np.testing.assert_allclose(whitener.T@(scale[:,None]*h*scale[None,:])@whitener,np.eye(2),atol=1e-10)
    fit=minimize_whitened(statistics,[0.,0.],scale,[-5.,-5.],[5.,5.],whitener)
    assert fit['converged']
    np.testing.assert_allclose(fit['parameters'],center,atol=1e-6)
    constrained=minimize_whitened(statistics,[0.,0.],scale,[-5.,-5.],[1.,5.],whitener)
    assert constrained['converged'] and constrained['boundary']
    assert np.all(constrained['parameters']<=[1.000001,5.000001])
