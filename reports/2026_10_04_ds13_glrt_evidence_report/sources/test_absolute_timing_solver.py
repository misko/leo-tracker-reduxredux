import sys
from types import SimpleNamespace
import numpy as np
import pytest
from absolute_timing_solver import absolute_parameters,AbsoluteCalibration

def test_single_absolute_shift_does_not_mutate_input():
    p=np.arange(9,dtype=float);q=absolute_parameters(p,[0,2],.116)
    assert q[6]==q[8]==.116 and q[7]==p[7]
    assert np.array_equal(p,np.arange(9,dtype=float))

def test_different_fold_references_cannot_change_satellite_time(monkeypatch):
    seen=[]
    def paired(d,p,rows,sats):
        seen.append(p[6]);return np.full(len(rows),p[6]),np.ones(len(rows),bool),SimpleNamespace(tau=np.ones(len(rows)))
    monkeypatch.setitem(sys.modules,'prediction_jacobian',SimpleNamespace(paired_prediction_jacobian=paired))
    cal=AbsoluteCalibration.__new__(AbsoluteCalibration)
    cal.parts=[(SimpleNamespace(times=np.arange(2)),{'fitted-c':(np.zeros(7),common,np.zeros(2))}) for common in [-.3365,-.695]]
    p,v,r=cal.predict('fitted-c',np.array([0]),.116)
    assert seen==[.116,.116] and np.all(p==.116)

def test_search_bounds():
    for value in [-20.,20.]:assert absolute_parameters(np.zeros(7),[0],value)[6]==value
    for value in [-20.1,20.1,np.nan]:
        with pytest.raises(ValueError):absolute_parameters(np.zeros(7),[0],value)
