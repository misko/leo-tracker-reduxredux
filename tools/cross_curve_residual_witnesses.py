"""Descriptive rate witnesses; frozen full-fit residuals are not holdout evidence."""
import numpy as np
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def rate(times,residual):
    t,r=np.asarray(times,float),np.asarray(residual,float)
    if t.ndim!=1 or r.shape!=t.shape or len(t)<4 or not np.isfinite(np.r_[t,r]).all() or np.ptp(t)<=0:
        raise ValueError('four finite matching points with positive span required')
    x=t-t.mean();slope=float(x@r/(x@x));remaining=r-r.mean()-slope*x
    return dict(points=len(t),span_s=float(np.ptp(t)),mean_hz=float(r.mean()),slope_hz_s=slope,
        RMS_hz=float(np.sqrt(np.mean(r*r))),affine_RMS_hz=float(np.sqrt(np.mean(remaining*remaining))),
        descriptive_slope_scale_hz_s=float(max(np.std(remaining,ddof=1),75.)/np.sqrt(x@x)))


def summarize(tracks,target_component):
    target=next(r for r in tracks if r['component']==target_component)
    t=np.asarray(target['times_s']);r=np.asarray(target['residual_hz']);start,end=t.min(),t.max()
    minimum_span=max(5.,.5*(end-start));local=[]
    for track in tracks:
        times=np.asarray(track['times_s']);keep=(times>=start)&(times<=end)
        if keep.sum()<4 or np.ptp(times[keep])<minimum_span:continue
        residual=np.asarray(track['residual_hz'])[keep];q=track['rf_hz']/11.5e9
        local.append(dict(component=track['component'],norad=track['norad'],receiver=track['receiver'],channel=track['channel'],
            times_s=times[keep],residual_hz=residual,q=q,**rate(times[keep],residual)))
    groups=[]
    for name in ('same_receiver','same_receiver_band','other_receiver','same_satellite_other_curve'):
        if name=='same_satellite_other_curve':
            selected=[w for w in local if w['norad']==target['norad'] and w['component']!=target_component]
        else:
            selected=[w for w in local if w['norad']!=target['norad'] and
                ((w['receiver']!=target['receiver']) if name=='other_receiver' else (w['receiver']==target['receiver']))]
            if name=='same_receiver_band':selected=[w for w in selected if (w['channel']>4)==(target['channel']>4)]
        # Every family gets one vote, preventing duplicated channels from
        # overwhelming the receiver-level descriptive rate.
        for scaling in ('hz','fractional'):
            families=sorted({w['norad'] for w in selected})
            rates=[float(np.median([w['slope_hz_s']/(w['q'] if scaling=='fractional' else 1.) for w in selected if w['norad']==n])) for n in families]
            needed=rate(t,r)['slope_hz_s'];predicted=None;after=None;gates=None
            if rates:
                predicted=float(np.median(rates))*(target['rf_hz']/11.5e9 if scaling=='fractional' else 1.)
                after=r-predicted*(t-t.mean());gates={k:v[0].item() for k,v in batch_noise_screen(after[None,:],t).items()}
            groups.append(dict(group=name,scaling=scaling,witness_components=[w['component'] for w in selected],
                distinct_families=len(families),witness_curves=len(selected),family_rates=rates,needed_target_rate_hz_s=needed,
                predicted_target_rate_hz_s=predicted,target_RMS_after_hz=float(np.sqrt(np.mean(after**2))) if after is not None else None,
                target_noise_after=gates,descriptive_only=True))
    return dict(target=target,target_rate=rate(t,r),window_s=[float(start),float(end)],minimum_witness_span_s=float(minimum_span),
        witnesses=local,groups=groups,fit_used_full_scan=True,independent_predictive_validation=False,acceptance_authorized=False)
