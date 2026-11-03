"""Delta-method uncertainty for the fixed monotonic native CFO inverse map."""

import numpy as np


def inverse_noise_scale(native_cfo_hz,response,origin_hz):
    f=np.asarray(native_cfo_hz,float)-origin_hz;step=response['step_hz']
    local=f-np.floor(f/step+.5)*step
    reported=np.asarray(response['reported_offset_hz'],float)
    actual=np.asarray(response['actual_offset_hz'],float)
    if np.any(np.diff(reported)<=0):
        raise ValueError('monotonic response required')
    indices=np.clip(np.searchsorted(reported,local,side='right')-1,0,len(reported)-2)
    return np.diff(actual)[indices]/np.diff(reported)[indices]
