"""RF-only predictive scatter for locally refined, complete polynomial curves."""

import numpy as np
from probe_ds23_refined_curve_position import proposed_delta


def curve_noise(times,values,*,floor_hz=5.):
    t,y=np.asarray(times,float),np.asarray(values,float)
    if t.shape!=y.shape or t.ndim!=1 or len(t)<8 or not np.isfinite(t).all() or not np.isfinite(y).all() or np.ptp(t)<=0 or floor_hz<1:
        raise ValueError('finite supported curve and noise floor >=1 Hz required')
    center,span=float(t.mean()),max(1.,float(np.ptp(t)))
    z=(t-center)/span;models=[]
    for degree in range(5):
        if len(t)<4*(degree+1):continue
        a=np.vander(z,degree+1,increasing=True);q,_=np.linalg.qr(a)
        coefficients=np.linalg.lstsq(a,y,rcond=None)[0];r=y-a@coefficients
        leverage=np.sum(q*q,axis=1);press=r/np.maximum(1-leverage,1e-8)
        cost=len(t)*np.log(max(float(np.mean(r*r)),floor_hz**2))+(degree+1)*np.log(len(t))
        models.append(dict(degree=degree,profile_BIC=cost,residual_hz=r,
            predictive_scatter_hz=float(np.sqrt(np.mean(press*press))),
            fitted_RMS_hz=float(np.sqrt(np.mean(r*r))),
            lag_one_correlation=float(np.corrcoef(r[:-1],r[1:])[0,1]) if np.std(r)>1e-9 else 0.,
            coefficients=coefficients,time_center_s=center,time_span_s=span))
    return min(models,key=lambda r:r['profile_BIC'])


def learn_noise(raw,*,floor_hz=5.):
    lookup={r['point']['observation_id']:r for r in raw['rows']};by_id={};receipts=[]
    if len(lookup)!=len(raw['rows']):raise ValueError('unique original observations required')
    for track in raw['panel_metadata']['tracks']:
        rows=[lookup[o] for o in track['observation_ids']];t=np.array(track['times']);y=np.array(track['values'])
        changes=[proposed_delta(r,'joint_CFO_epoch_rate') for r in rows]
        valid=np.array([reason=='refined' for _,reason in changes]);v=y+np.array([delta for delta,_ in changes])
        if valid.sum()<8:continue
        model=curve_noise(t[valid],v[valid],floor_hz=floor_hz)
        z=(t-model['time_center_s'])/model['time_span_s'];c=model['coefficients']
        derivative=np.polynomial.polynomial.polyval(z,np.arange(1,len(c))*c[1:])/model['time_span_s']
        differences=[]
        for k,r in enumerate(rows):
            a,b=r['odd_frames'],r['even_frames']
            if not valid[k] or a['frequency_search_boundary'] or b['frequency_search_boundary']:continue
            dt=a['effective_time_from_probe_start_s']-b['effective_time_from_probe_start_s']
            differences.append(a['CFO_hz']-b['CFO_hz']-derivative[k]*dt)
        split=float(np.sqrt(np.mean(np.array(differences)**2))/2) if differences else 0.
        sigma=max(floor_hz,model['predictive_scatter_hz'],split)
        for oid,good in zip(track['observation_ids'],valid,strict=True):
            if good:by_id[oid]=sigma
        receipts.append(dict(track=track['key'],receiver=track['receiver'],channel=track['channel'],
            retained_original_points=len(rows),refined_points_used_to_learn_noise=int(valid.sum()),
            original_boundary_values_do_not_learn_refined_noise=True,
            selected_sigma_hz=sigma,split_frame_proxy_hz=split,split_frame_pairs=len(differences),**model))
    return by_id,receipts
