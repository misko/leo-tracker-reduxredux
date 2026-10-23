import numpy as np
from native_shape import polynomial


def test_polynomial_invariant_to_constant_alias_shift():
    t=np.linspace(0,40,50);y=1000+30*t+3*t*t+np.sin(t)*10
    left=polynomial(t,y,np.full(50,30.));right=polynomial(t,y+234375,np.full(50,30.))
    assert left['degree']==right['degree']
    np.testing.assert_allclose(left['residual_hz'],right['residual_hz'],atol=1e-7)
