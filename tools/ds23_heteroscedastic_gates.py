"""Residual-structure tests with declared pointwise CFO uncertainty."""

import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from leo.analysis.research.retained_track_likelihood import profile,whitening


def noise_screen(residual,times,sigma):
    r,t,s=map(lambda a:np.asarray(a,float),(residual,times,sigma))
    if r.ndim!=1 or r.shape!=t.shape or r.shape!=s.shape or len(t)<4 or not all(np.isfinite(a).all() for a in (r,t,s)) or np.any(s<=0) or np.ptp(t)<=0:
        raise ValueError('finite matching residual/time/noise and positive scales required')
    n=len(t);z=r/s;scatter=max(1.,float(np.std(z,ddof=1)));w=1/s**2
    mean_z=abs(np.sum(r*w))/np.sqrt(sum(w))/scatter
    x=t-np.sum(t*w)/sum(w);slope_z=abs(np.sum(r*x*w))/max(1e-12,np.sqrt(np.sum(x*x*w))*scatter)
    tx=(t-t.mean())/max(1.,float(np.ptp(t))/2);a=np.column_stack((np.ones(n),tx,tx*tx))/s[:,None]
    fitted=a@np.linalg.lstsq(a,z,rcond=None)[0]
    bic=n*np.log(max(float(z@z),n)/max(float(np.sum((z-fitted)**2)),n))-3*np.log(n)
    step=0.
    for k in range(4,n-3):
        wl,wr=sum(w[:k]),sum(w[k:]);jump=np.sum(r[:k]*w[:k])/wl-np.sum(r[k:]*w[k:])/wr
        step=max(step,abs(jump)/(scatter*np.sqrt(1/wl+1/wr)))
    centered=z-z.mean();acf=float(centered[:-1]@centered[1:]/max(float(centered@centered),1e-12))
    passed=mean_z<=3 and slope_z<=3 and bic<=10 and step<=4 and abs(acf)<=4/np.sqrt(n)
    return dict(noise_screen_pass=bool(passed),mean_z=float(mean_z),slope_z=float(slope_z),quadratic_bic_gain=float(bic),
        maximum_step_z=float(step),lag1_acf=acf,standardized_scatter=scatter)


def metrics(p,x):
    scan=p.scan;state=p.state(x);c=p.calculate(x);frequency,elevation=p.conditional_frequency(x)
    legacy=retained_metrics(p,x);old={r['component']:r for r in legacy['tracks']};rows=[]
    for row,i,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
        track=scan.tracks[i];active=p.keep[sl]
        if not active.any():continue
        t=track['times'][active];s=p.point_noise[sl][active];q=track['rf_hz']/11.5e9
        y=track['values']-scan.hardware(track,state['beta'])-q*scan.rx_basis[i]@state['smooth'][track['receiver']-1]
        terms=profile(y[active],q*frequency[sl][active],np.diag(1/s))
        profile_noise=noise_screen(terms['residual'][0],t,s)
        residual=c['conditional_residual_hz'][sl][active];conditional=noise_screen(residual,t,s)
        previous=old[track['key']]
        hard=previous['profile_rms_hz']<=450 and abs(previous['profile_bias_hz'])<=3000 and previous['aliases_changed']==0
        hard=hard and terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and int(terms['alias'][0])==alias and min(elevation[sl][active])>=0 and np.sqrt(np.mean(residual**2))<=450
        rows.append(dict(component=track['key'],candidate_index=row['candidate_index'],norad=row['candidate_norad'],
            points=int(active.sum()),compatible=bool(hard and profile_noise['noise_screen_pass'] and conditional['noise_screen_pass']),
            hard_bounds_pass=bool(hard),profile_noise=profile_noise,conditional_noise=conditional,
            legacy_compatible=previous['compatible'],profile_bias_hz=float(terms['bias'][0]),
            conditional_RMS_hz=float(np.sqrt(np.mean(residual**2))),observation_ids=np.array(track['observation_ids'])[active]))
    while True:
        owners={};lookup={t['key']:t for t in scan.tracks}
        for r in rows:
            if r['compatible']:
                t=lookup[r['component']];owners.setdefault(r['candidate_index'],set()).add((t['receiver'],t['channel']))
        changed=False
        for r in rows:
            if r['compatible'] and r['candidate_index'] in p.supported and len(owners[r['candidate_index']])<2:r['compatible']=False;changed=True
        if not changed:break
    return dict(tracks=rows,accepted_points=sum(r['points'] for r in rows if r['compatible']),legacy=legacy,
        same_thresholds_physical_bounds_alias_visibility_and_support=True)
