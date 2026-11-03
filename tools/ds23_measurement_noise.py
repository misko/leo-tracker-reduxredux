"""Separate CFO measurement scatter from polynomial prediction uncertainty."""

import numpy as np
from ds23_refined_noise import learn_noise
from probe_ds23_refined_curve_position import proposed_delta


def measurement_scatter(times,residual,degree):
    t,r=np.asarray(times,float),np.asarray(residual,float)
    if t.shape!=r.shape or t.ndim!=1 or len(t)<=degree+1 or not np.isfinite(t).all() or not np.isfinite(r).all():
        raise ValueError('supported finite residual/time samples required')
    z=(t-t.mean())/max(1.,float(np.ptp(t)));q,_=np.linalg.qr(np.vander(z,degree+1,increasing=True))
    h=np.sum(q*q,axis=1)
    sigma=float(np.sqrt(np.mean(r*r/np.maximum(1-h,1e-8))))
    return sigma,float(max(h))


def learn_measurement_noise(raw):
    _,receipts=learn_noise(raw);lookup={r['point']['observation_id']:r for r in raw['rows']}
    tracks={t['key']:t for t in raw['panel_metadata']['tracks']};noise={};corrected=[]
    for receipt in receipts:
        t=tracks[receipt['track']];good=np.array([proposed_delta(lookup[o],'joint_CFO_epoch_rate')[1]=='refined' for o in t['observation_ids']])
        sigma,leverage=measurement_scatter(np.array(t['times'])[good],receipt['residual_hz'],receipt['degree'])
        selected=max(5.,sigma,receipt['split_frame_proxy_hz'])
        for oid,valid in zip(t['observation_ids'],good,strict=True):
            if valid:noise[oid]=selected
        corrected.append(dict(receipt,selected_sigma_hz=selected,studentized_measurement_scatter_hz=sigma,
            maximum_leverage=leverage,old_PRESS_selected_sigma_hz=receipt['selected_sigma_hz'],
            prediction_uncertainty_is_not_used_as_raw_measurement_noise=True))
    return noise,corrected


def local_scatter(times,values,window=16):
    t,y=np.asarray(times,float),np.asarray(values,float)
    width=min(window,len(t));estimates=[]
    for start in range(len(t)-width+1):
        x=t[start:start+width];v=y[start:start+width];z=(x-x.mean())/max(1.,float(np.ptp(x)));models=[]
        for degree in range(4):
            if width<2*(degree+1)+3:continue
            a=np.vander(z,degree+1,increasing=True);q,_=np.linalg.qr(a);r=v-q@(q.T@v)
            score=width*np.log(max(float(np.mean(r*r)),25))+(degree+1)*np.log(width)
            models.append((score,float(np.sqrt(np.sum(r*r)/(width-degree-1)))))
        if models:estimates.append(min(models)[1])
    if not estimates:raise ValueError('at least five reliable radio points needed for local scatter')
    return float(np.median(estimates)),len(estimates)


def learn_local_noise(raw):
    _,receipts=learn_measurement_noise(raw);lookup={r['point']['observation_id']:r for r in raw['rows']}
    tracks={t['key']:t for t in raw['panel_metadata']['tracks']};noise={};result=[]
    for r in receipts:
        track=tracks[r['track']];rows=[lookup[o] for o in track['observation_ids']]
        changes=[proposed_delta(row,'joint_CFO_epoch_rate') for row in rows];valid=np.array([reason=='refined' for _,reason in changes])
        y=np.array(track['values'])+np.array([delta for delta,_ in changes]);sigma,windows=local_scatter(np.array(track['times'])[valid],y[valid])
        selected=max(5.,sigma,r['split_frame_proxy_hz'])
        for oid,good in zip(track['observation_ids'],valid,strict=True):
            if good:noise[oid]=selected
        result.append(dict(r,selected_sigma_hz=selected,local_measurement_scatter_hz=sigma,local_windows=windows,
            no_global_polynomial_or_geographic_residual_enters_local_variance=True))
    return noise,result
