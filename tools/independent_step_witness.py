"""Exploratory step evidence from other satellite families at a frozen fit.

This does not authorize an association or a receiver correction. Full-fit
residuals share fitted parameters and are not independent held-out evidence.
"""
import numpy as np


def fit_at_time(curves,tau,*,noise_hz=150.,prior_hz=150.):
    if noise_hz<=0 or prior_hz<=0:raise ValueError('positive noise and amplitude prior required')
    eligible=[]
    for curve in curves:
        t=np.asarray(curve['times_s'],float);r=np.asarray(curve['residual_hz'],float)
        if t.ndim!=1 or r.shape!=t.shape or not np.isfinite(np.r_[t,r]).all():raise ValueError('finite matching witness arrays required')
        if (t<tau).sum()<4 or (t>=tau).sum()<4:continue
        design=np.column_stack((np.ones(len(t)),t-t.mean()))
        y=r-design@np.linalg.lstsq(design,r,rcond=None)[0]
        z=(t>=tau).astype(float);z-=design@np.linalg.lstsq(design,z,rcond=None)[0]
        info=float(z@z/noise_hz**2);rhs=float(z@y/noise_hz**2)
        if info>1e-12:eligible.append(dict(component=curve['component'],norad=curve['norad'],information=info,rhs=rhs,points=len(t)))
    families=sorted({r['norad'] for r in eligible});per_family=[]
    for family in families:
        rows=[r for r in eligible if r['norad']==family]
        # Multiple channels from the same family cannot manufacture more votes.
        info=float(np.mean([r['information'] for r in rows]));rhs=float(np.mean([r['rhs'] for r in rows]));variance=1/(info+1/prior_hz**2)
        per_family.append(dict(norad=family,curves=len(rows),information=info,rhs=rhs,amplitude_hz=rhs*variance,sigma_hz=np.sqrt(variance)))
    if len(families)<2:return None
    info=sum(r['information'] for r in per_family);rhs=sum(r['rhs'] for r in per_family);variance=1/(info+1/prior_hz**2)
    amplitude=rhs*variance
    return dict(time_s=float(tau),amplitude_hz=amplitude,sigma_hz=np.sqrt(variance),
        log_evidence_gain=rhs**2*variance-np.log1p(info*prior_hz**2),
        same_sign_two_sigma_families=sum(np.sign(r['amplitude_hz'])==np.sign(amplitude) and abs(r['amplitude_hz'])>=2*r['sigma_hz'] for r in per_family),
        distinct_families=len(families),family_votes=per_family,curves=eligible)


def search(tracks,target,*,scope='same_receiver',scaling='hz',step_s=1.):
    if scope not in ('same_receiver','same_receiver_band','other_receiver') or scaling not in ('hz','fractional') or step_s<=0:
        raise ValueError('known scope/scaling and positive time step required')
    t=np.asarray(target['times_s']);window=[float(t.min()-10),float(t.max()+10)];curves=[]
    for track in tracks:
        if track['norad']==target['norad']:continue
        same=track['receiver']==target['receiver']
        if scope=='other_receiver' and same:continue
        if scope!='other_receiver' and not same:continue
        if scope=='same_receiver_band' and (track['channel']>4)!=(target['channel']>4):continue
        times=np.asarray(track['times_s']);mask=(times>=window[0])&(times<=window[1])
        if mask.sum()<8:continue
        q=track['rf_hz']/11.5e9 if scaling=='fractional' else 1.
        curves.append(dict(component=track['component'],norad=track['norad'],times_s=times[mask],residual_hz=np.asarray(track['residual_hz'])[mask]/q))
    grid=np.arange(np.ceil(t.min()/step_s)*step_s,t.max()+1e-8,step_s)
    trials=[v for tau in grid if (v:=fit_at_time(curves,tau)) is not None]
    penalty=2*np.log(max(len(grid),1)*6) # all three scopes and both scalings remain visible
    best=max(trials,key=lambda r:r['log_evidence_gain']) if trials else None
    if best:
        best=dict(best,search_adjusted_gain=best['log_evidence_gain']-penalty,
            predicted_target_amplitude_hz=best['amplitude_hz']*(target['rf_hz']/11.5e9 if scaling=='fractional' else 1.))
    return dict(scope=scope,scaling=scaling,window_s=window,grid_s=grid,search_penalty=penalty,
        witness_curves=len(curves),target_family_excluded=True,best=best,trials=trials,
        supported_exploratory_proposal=bool(best and best['search_adjusted_gain']>0 and best['same_sign_two_sigma_families']>=2),
        independent_holdout_validation=False,acceptance_authorized=False)
