"""Position/TLE-independent shared-curvature check within one receiver.

After dividing CFO by actual RF, a same-satellite common curve and shared
receiver smooth term remain common. Arbitrary per-track affine terms absorb
constant aliases, band offsets and the modeled small linear drift. This is
a diagnostic model comparison, not an identity probability or deletion gate.
"""

import numpy as np


def shared_shape(tracks,*,overlap_only=True):
    if len(tracks)!=2 or len({t['receiver'] for t in tracks})!=1:
        raise ValueError('two tracks on the same receiver required')
    start=max(float(t['times'][0]) for t in tracks);end=min(float(t['times'][-1]) for t in tracks)
    if end-start<6:raise ValueError('at least six seconds of actual overlap required')
    times=[];values=[];groups=[];ids=[]
    for group,track in enumerate(tracks):
        t=np.asarray(track['times']);y=np.asarray(track['values'])/(track['rf_hz']/11.5e9)
        use=(t>=start)&(t<=end) if overlap_only else np.ones(len(t),bool)
        if use.sum()<8:raise ValueError('at least eight overlapping points per track required')
        times.extend(t[use]);values.extend(y[use]);groups.extend(np.full(use.sum(),group));ids.extend(np.asarray(track['observation_ids'])[use])
    times,values,groups=map(np.asarray,(times,values,groups))
    if len(set(ids))!=len(ids):raise ValueError('the two tracks reuse physical observations')
    reference=float(times.mean());scale=float(np.ptp(times));z=(times-reference)/scale
    rows=[]
    for degree in range(1,5):
        u=np.polynomial.legendre.legvander(z,degree);affine=np.zeros((len(z),4))
        for group in [0,1]:affine[groups==group,2*group:2*group+2]=u[groups==group,:2]
        shared=np.column_stack((affine,u[:,2:]));independent=np.column_stack((u*(groups==0)[:,None],u*(groups==1)[:,None]))
        for method,design in [('shared',shared),('independent',independent)]:
            coefficient=np.linalg.lstsq(design,values,rcond=None)[0];residual=values-design@coefficient;rank=np.linalg.matrix_rank(design)
            rss=float(residual@residual);bic=len(z)*np.log(max(rss/len(z),1e-12))+rank*np.log(len(z))
            rows.append(dict(method=method,degree=degree,parameters=int(rank),RMS_hz=float(np.sqrt(rss/len(z))),
                BIC=float(bic),coefficient=coefficient,residual_hz=residual,fitted_hz=design@coefficient))
    best={method:min((r for r in rows if r['method']==method),key=lambda r:r['BIC']) for method in ['shared','independent']}
    affine=next(r for r in rows if r['method']=='shared' and r['degree']==1)
    return dict(times=times,values_hz=values,groups=groups,observation_ids=list(ids),reference_s=reference,time_scale_s=scale,
        overlap_s=[start,end],overlap_only=overlap_only,rows=rows,best=best,
        BIC_shared_minus_independent=best['shared']['BIC']-best['independent']['BIC'],
        independent_active_curvature_gain=affine['BIC']-best['independent']['BIC'],
        same_original_observations_in_all_models=True,noise_model='one common unknown white variance profiled in both models',
        diagnostic_only_no_satellite_or_position_or_measurement_change=True)
