"""Array-only discovery of receiver steps corroborated across satellite families.

Affine elimination is proposal-only. This neither changes calibration nor
authorizes association or position updates. Input identities remain conditional.
"""
import numpy as np


def step_candidates(curves,times,*,prior_sigma_hz=200.,minimum_per_side=3):
    grid=np.asarray(times,float)
    if grid.ndim!=1 or not len(grid) or not np.isfinite(grid).all() or not np.isfinite(prior_sigma_hz) or prior_sigma_hz<=0 or minimum_per_side<1:
        raise ValueError('finite event grid, positive prior and point count required')
    prepared=[]
    for curve in curves:
        t=np.asarray(curve['times_s'],float);y=np.asarray(curve['residual_hz'],float);sigma=np.broadcast_to(curve['sigma_hz'],t.shape).astype(float)
        if t.ndim!=1 or y.shape!=t.shape or len(t)<3 or not all(np.isfinite(v).all() for v in [t,y,sigma]) or np.any(sigma<=0) or np.ptp(t)<=0:
            raise ValueError('finite curves, positive duration and noise required')
        q=float(curve['rf_hz'])/11.5e9
        if not np.isfinite(q) or q<=0:raise ValueError('positive RF required')
        affine=np.column_stack([np.ones(len(t)),t-t.mean()])/sigma[:,None]
        raw=y/sigma;raw=raw-affine@np.linalg.lstsq(affine,raw,rcond=None)[0]
        prepared.append((curve,t,sigma,q,affine,raw))
    results=[];receivers=sorted({c['receiver'] for c in curves});penalty=2*np.log(max(2,len(grid)*len(receivers)))
    for receiver in receivers:
        for tau in grid:
            pieces=[];families={}
            for curve,t,sigma,q,affine,raw in prepared:
                if curve['receiver']!=receiver or sum(t<tau)<minimum_per_side or sum(t>=tau)<minimum_per_side:continue
                u=(t>=tau)*prior_sigma_hz*q/sigma;u=u-affine@np.linalg.lstsq(affine,u,rcond=None)[0]
                info=float(u@u);cross=float(u@raw);family=curve['norad'];f=families.setdefault(family,dict(information=0.,cross=0.))
                f['information']+=info;f['cross']+=cross
                pieces.append(dict(component=curve['component'],norad=family,channel=curve['channel'],information=info,cross=cross))
            if not pieces:continue
            info=1+sum(p['information'] for p in pieces);cross=sum(p['cross'] for p in pieces)
            gain=cross*cross/info-np.log(info);family_rows=[]
            for family,f in families.items():
                fi=1+f['information'];fg=f['cross']**2/fi-np.log(fi)
                family_rows.append(dict(norad=family,gain=float(fg),amplitude_hz=prior_sigma_hz*f['cross']/fi,
                    supports_common_step=bool(fg>0 and f['cross']*cross>0)))
            supporting=[f['norad'] for f in family_rows if f['supports_common_step']]
            results.append(dict(receiver=receiver,time_s=float(tau),gain=float(gain),search_penalty=float(penalty),
                amplitude_hz=prior_sigma_hz*cross/info,spanning_families=sorted(families),supporting_families=sorted(supporting),
                families=family_rows,pieces=pieces,candidate=bool(gain>penalty and len(supporting)>=2),discovery_only=True))
    return sorted(results,key=lambda r:-r['gain'])
