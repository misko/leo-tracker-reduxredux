"""All-catalogue family proposals with one shared phase and fragment constants."""

import numpy as np
from leo.analysis.research.retained_track_likelihood import PERIOD


def screen_family(curves,phase_widths,bias_sigma_hz=300.):
    widths=np.asarray(phase_widths,float)
    if widths.ndim!=1 or np.any(widths<=0) or not np.isfinite(widths).all() or bias_sigma_hz<=0 or not curves:
        raise ValueError('positive phase/constant widths and at least one curve required')
    count=len(widths);information=np.ones(count);rhs=np.zeros(count);raw_cost=np.zeros(count)
    fragments=[];visible=np.ones(count,bool)
    for curve in curves:
        y,f,d,noise=map(lambda k:np.asarray(curve[k],float),('observed','predicted','derivative','sigma'))
        if y.ndim!=1 or f.shape!=(count,len(y)) or d.shape!=f.shape or noise.shape!=y.shape or np.any(noise<=0):
            raise ValueError('matching finite curve/candidate arrays and positive per-point noise required')
        if not all(np.isfinite(a).all() for a in (y,f,d,noise)):raise ValueError('finite inputs required')
        power=float(curve['power'])
        if not 0<power<=1:raise ValueError('fixed likelihood power in (0,1] required')
        w=power/noise**2
        aliases=np.rint((np.sum(f*w,axis=1)/sum(w)-np.sum(y*w)/sum(w))/PERIOD).astype(int)
        r=y+aliases[:,None]*PERIOD-f;u=d*widths[:,None]
        diagonal=1+bias_sigma_hz**2*sum(w);cross=np.sum(w*u*bias_sigma_hz,axis=1)
        fragment_rhs=np.sum(w*r*bias_sigma_hz,axis=1)
        information+=np.sum(w*u*u,axis=1)-cross*cross/diagonal
        rhs+=np.sum(w*u*r,axis=1)-cross*fragment_rhs/diagonal
        raw_cost+=np.sum(w*r*r,axis=1)-fragment_rhs**2/diagonal+np.log(diagonal)
        visible&=np.asarray(curve['visible'],bool)
        fragments.append(dict(aliases=aliases,diagonal=diagonal,cross=cross,rhs=fragment_rhs))
    information=np.maximum(information,1e-15)
    cost=raw_cost-rhs*rhs/information+np.log(information);cost[~visible]=np.inf
    coefficient=rhs/information
    return dict(cost=cost,phase_correction_s=coefficient*widths,
        aliases=[r['aliases'] for r in fragments],
        bias_hz=[bias_sigma_hz*(r['rhs']-r['cross']*coefficient)/r['diagonal'] for r in fragments])
