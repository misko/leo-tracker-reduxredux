import numpy as np
import pytest
from inventory_ds23_calibration_curvature import active_evidence


def test_unused_isolated_point_cannot_supply_curvature_to_the_active_mask():
    t=np.r_[0.,np.linspace(10,40,30)];y=300*t;y[0]=40000
    assert not active_evidence(dict(times=t,values=y),np.r_[False,np.ones(30,bool)])['qualified']


def test_distributed_curvature_and_alias_invariance_on_actual_points():
    t=np.linspace(0,60,40);y=10*t*t
    a=active_evidence(dict(times=t,values=y),np.ones(len(t),bool));b=active_evidence(dict(times=t,values=y+1/4.4e-6),np.ones(len(t),bool))
    assert a['qualified'] and b['qualified']
    assert abs(a['minimum_linear_RMS_hz']-b['minimum_linear_RMS_hz'])<1e-8
    with pytest.raises(ValueError,match='nonempty'):active_evidence(dict(times=t,values=y),np.zeros(len(t),bool))
