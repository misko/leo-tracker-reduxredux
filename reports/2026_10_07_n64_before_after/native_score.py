"""Offline acceleration, numerically audited against the original implementation."""
import ctypes
from pathlib import Path
import numpy as np
from leo.analysis.regional_position_score import observer
from fast_score import FastObjective
import fast_score

_lib=ctypes.CDLL(str(Path(__file__).with_name('orbits.so')))
_double=np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS')
_bool=np.ctypeslib.ndpointer(dtype=np.bool_,flags='C_CONTIGUOUS')
_lib.predict.argtypes=[ctypes.c_int]*3+[ctypes.c_double]*2+[_double]*8+[ctypes.c_int,_double,_bool,_double,_double]
_lib.predict.restype=ctypes.c_int

def predict_orbits(bank,observations,prior,point,shifts_s,*,derivatives=True):
    shifts=np.ascontiguousarray(shifts_s,dtype=float)
    if shifts.shape!=(len(bank.numbers),) or not np.isfinite(shifts).all():
        raise ValueError('one finite orbit shift per satellite required')
    site,up=observer(prior,point)
    jac=np.zeros((2,3))
    if derivatives:
        eye=np.eye(2)*.001
        jac=np.stack([(observer(prior,np.asarray(point)+d)[0]-observer(prior,np.asarray(point)-d)[0])/.002 for d in eye])
    shape=(len(observations.times_s),len(bank.numbers))
    prediction=np.empty(shape);visible=np.empty(shape,dtype=bool)
    spatial=np.empty((*shape,2)) if derivatives else np.empty(0)
    timing=np.empty(shape) if derivatives else np.empty(0)
    result=_lib.predict(*shape,len(bank.nodes_s),bank.nodes_s[0],bank.nodes_s[1]-bank.nodes_s[0],
        np.ascontiguousarray(observations.times_s),np.ascontiguousarray(observations.rf_hz),shifts,
        np.ascontiguousarray(bank.position_km),np.ascontiguousarray(bank.velocity_km_s),
        site,up,jac,int(derivatives),prediction,visible,spatial,timing)
    if result:raise ValueError('orbit query outside ephemeris support' if result==1 else 'satellite coincides with observer')
    return prediction,visible,spatial if derivatives else None,timing if derivatives else None

class NativeObjective(FastObjective):
    pass

# This module is used exclusively in offline replay processes. FastObjective's
# mathematics is unchanged; only its orbit evaluator is exchanged.
fast_score.predict_orbits=predict_orbits
