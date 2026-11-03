"""Signed range-curvature controls for the unused frame-epoch observable."""

import numpy as np
from probe_ds23_frame_timing import clock_segments


def compare_clock_curvature(times,arrival_seconds,range_km,window_phase_s=0.,window_s=15.):
    t,a,r=map(lambda x:np.asarray(x,float),(times,arrival_seconds,range_km))
    if t.shape!=a.shape or t.shape!=r.shape or t.ndim!=1 or window_s<=0:
        raise ValueError('matching timing/range arrays and positive window duration required')
    groups=np.floor((t+window_phase_s)/window_s);rows=[]
    for key in np.unique(groups):
        selected=np.flatnonzero(groups==key);tt,aa,rr=t[selected],a[selected],r[selected]
        for segment in clock_segments(tt,aa,np.zeros(len(rr))):
            start,stop=segment['start_index'],segment['stop_index'];x=tt[start:stop]
            affine=np.column_stack((np.ones(len(x)),x-x.mean()))
            delay=rr[start:stop]/299792.458*1e6
            geometric=delay-affine@np.linalg.lstsq(affine,delay,rcond=None)[0]
            observed=np.array(segment['affine_residual_us']);information=float(geometric@geometric)
            gamma=float(geometric@observed/max(information,1e-24))
            rows.append(dict(indices=selected[start:stop],time_s=x,observed_curvature_us=observed,
                geometric_curvature_us=geometric,gamma=gamma,points=len(x),
                raw_RMS_us=float(np.sqrt(np.mean(observed**2))),
                positive_range_RMS_us=float(np.sqrt(np.mean((observed-geometric)**2))),
                negative_range_RMS_us=float(np.sqrt(np.mean((observed+geometric)**2))),
                geometric_RMS_us=float(np.sqrt(information/len(x))),
                free_gamma_RMS_us=float(np.sqrt(np.mean((observed-gamma*geometric)**2))),
                window_phase_s=window_phase_s,window_s=window_s))
    return rows
