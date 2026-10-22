import numpy as np

from diagnose_ds23_dbg01_orbit_support import curvature_information


def test_affine_physical_modes_do_not_count_as_active_curvature_support():
    t=np.linspace(0,40,25);x=(t-t.mean())/20
    modes=np.column_stack((np.ones(len(t)),x,x*x))
    eigen=curvature_information(t,modes,np.eye(len(t)))
    np.testing.assert_allclose(eigen[:2],0,atol=1e-12)
    assert eigen[-1]>2
    shifted=modes+np.outer(np.ones(len(t)),[100.,200.,300.])+np.outer(x,[11.,12.,13.])
    np.testing.assert_allclose(curvature_information(t,shifted,np.eye(len(t))),eigen,atol=1e-8)
