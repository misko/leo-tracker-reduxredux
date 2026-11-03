from types import SimpleNamespace
import numpy as np
import pytest

import ds23_windowed_differential_factor as m
from leo.analysis.research.retained_track_likelihood import PERIOD


def test_graph_lifts_and_original_fragment_aliases_are_distinct():
    native=np.array([20.,40.]);lifted=native+np.array([-2,3])*PERIOD
    assert m.lift_measured_contrast(-17.,native,lifted,[5,1])==pytest.approx(-17.-PERIOD)
    with pytest.raises(ValueError,match='exact integer'):m.lift_measured_contrast(-17.,native,lifted+[1.,0.],[5,1])


def test_window_response_retains_shared_receiver_rate_and_fragment_constants(monkeypatch):
    monkeypatch.setattr(m,'difference_query',lambda p,rows,t,rf:SimpleNamespace(time=t,q=np.ones(2)))
    def geometry(v,x,h):
        t=v.time
        return dict(intercept=np.array([10.+3*t,20.+7*t]),
            features=np.array([[100.,t,1000.,0.],[100.,t,0.,1000.]]))
    monkeypatch.setattr(m,'geometry_features',geometry)
    r=dict(curve_rows=[0,1],time_s=8.,rf_hz=12e9,frequency_rate_response_s=[.002,-.001])
    result=m.windowed_geometry(None,r,[0.,0.])
    assert result['intercept_hz']==pytest.approx((10+24)-(20+56)+.002*3-.001*7)
    np.testing.assert_allclose(result['features'],[0.,.001,1000.,-1000.],atol=1e-10)


def test_zero_measurements_delegate_to_unchanged_original_problem(monkeypatch):
    sentinel=object();monkeypatch.setattr(m,'make_event_problem',lambda *args:sentinel)
    assert m.make_differential_problem(None,None,None,None,None,None,None,None,[]) is sentinel
