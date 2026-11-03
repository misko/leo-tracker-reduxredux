"""RF-only tests of a fixed acquisition interpolation-response hypothesis.

Use original native CFOs, never a graph's alias-lifted CFO, for the response.
Leave-one-out polynomial predictions do not use the held measurement value.
These tests do not certify which acquisition binary generated a recording.
"""

import numpy as np


def polynomial_press(times,values,degree):
    t,y=np.asarray(times,float),np.asarray(values,float)
    if (t.ndim!=1 or y.shape!=t.shape or len(t)<degree+4 or degree<0 or
            not np.isfinite(t).all() or not np.isfinite(y).all() or np.ptp(t)<=0):
        raise ValueError('finite supported polynomial observations required')
    z=(t-t.mean())/np.ptp(t);a=np.polynomial.legendre.legvander(z,degree)
    q,r=np.linalg.qr(a)
    if np.linalg.matrix_rank(r)!=degree+1:raise ValueError('polynomial coordinates lack rank')
    residual=y-q@(q.T@y);h=np.sum(q*q,axis=1)
    if np.any(h>=1-1e-10):raise ValueError('leave-one-out polynomial has unit leverage')
    press=residual/(1-h)
    variance=np.maximum(0.,(residual@residual-residual**2/(1-h))/(len(y)-degree-2))
    return dict(prediction=y-press,press_residual=press,leverage=h,
        training_sigma_hz=np.sqrt(variance),prediction_sigma_hz=np.sqrt(variance*h/(1-h)))


def interpolation_bias(true_native_cfo,response,phase_shift_hz=0.):
    f=np.asarray(true_native_cfo,float)-phase_shift_hz
    step=response['step_hz'];center=np.floor(f/step+.5)*step;offset=f-center
    reported=np.interp(offset,response['actual_offset_hz'],response['reported_offset_hz'])
    return reported-offset


def native_correction(native_cfo,response):
    f=np.asarray(native_cfo,float);step=response['step_hz'];center=np.floor(f/step+.5)*step
    corrected=center+np.interp(f-center,response['reported_offset_hz'],response['actual_offset_hz'])
    return corrected-f


def active_curvature(times,values):
    t,y=np.asarray(times,float),np.asarray(values,float);x=t-t.mean();centered=y-y.mean()
    r=centered-x*(centered@x)/max(x@x,1e-12)
    return bool(np.ptp(t)>=20 and np.sqrt(np.mean(r*r))>=250)
