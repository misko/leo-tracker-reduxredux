import numpy as np
from visibility_state_gradient import weight_components,selected_weight_gradient


def test_all_state_columns_and_background_mass_conservation():
    margins=np.array([[.05,.2],[-.03,.3],[.12,.4]])
    jac=np.array([[[1.,2.,.5],[2.,1.,.2]],[[.2,-1.,.7],[1.,2.,.3]],[[.4,.5,-.6],[2.,3.,.1]]])
    components=weight_components(margins,jac,.1,.8)
    full=np.stack([selected_weight_gradient(components,i) for i in range(4)])
    np.testing.assert_allclose(np.exp(components[0])@full,np.zeros(8),atol=1e-13)
    for d in range(8):
        dm=np.zeros_like(margins)
        if d<3:dm=jac[:,:,d]
        elif d>=5:dm[d-5]=jac[d-5,:,2]
        h=1e-6
        plus=weight_components(margins+h*dm,jac,.1,.8)[0]
        minus=weight_components(margins-h*dm,jac,.1,.8)[0]
        np.testing.assert_allclose((plus-minus)/(2*h),full[:,d],rtol=1e-7,atol=1e-7)
    np.testing.assert_allclose(full[-1,2],full[-1,5:].sum(),atol=1e-14)
    assert np.all(full[:,3:5]==0)
