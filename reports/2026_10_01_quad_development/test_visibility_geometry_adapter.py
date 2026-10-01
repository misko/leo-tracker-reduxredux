from types import SimpleNamespace
import numpy as np
import pytest
from visibility_geometry_adapter import hermite_position_rate


def test_hermite_derivative_reproduces_cubic_and_knot_values():
    t=np.arange(7,dtype=float)
    p=np.stack([t**3,2*t*t,t],axis=-1)[None,:,:]
    v=np.stack([3*t*t,4*t,np.ones_like(t)],axis=-1)[None,:,:]
    bank=SimpleNamespace(times_s=t,positions_ecef_km=p,velocities_ecef_km_s=v)
    query=np.array([1.2,2.,3.7,5.])
    actual=hermite_position_rate(bank,query,np.array([0.]))[0]
    np.testing.assert_allclose(actual,np.stack([3*query**2,4*query,np.ones_like(query)],axis=-1),atol=1e-12)
    with pytest.raises(ValueError):hermite_position_rate(bank,[.5],[0.])
