"""RF-only receiver transfer of same-family channel-relative frequency rates.

A common quartic captures smooth frequency geometry, while300Hz Gaussian
fragment constants remain independent. Channel rates have a zero-sum1Hz/s
Gaussian contrast prior. The target RX never updates the source clock vector.
"""

import numpy as np
from scipy.linalg import helmert


def designs(times,channels,fragments,all_channels,all_fragments,*,center_s,scale_s,rate_sigma_hz_s=1.):
    t,ch,fr=np.asarray(times,float),np.asarray(channels),np.asarray(fragments)
    if t.ndim!=1 or ch.shape!=t.shape or fr.shape!=t.shape or not np.isfinite(t).all():raise ValueError('aligned finite RF samples required')
    if len(set(all_channels))!=len(all_channels) or len(all_channels)<2 or len(set(all_fragments))!=len(all_fragments):
        raise ValueError('unique fragments and at least two channel identities required')
    if scale_s<=0 or rate_sigma_hz_s<=0 or not np.isfinite([center_s,scale_s,rate_sigma_hz_s]).all():raise ValueError('positive finite scale and rate prior required')
    channel_index={v:k for k,v in enumerate(all_channels)};fragment_index={v:k for k,v in enumerate(all_fragments)}
    try:ci=np.array([channel_index[v] for v in ch],int);fi=np.array([fragment_index[v] for v in fr],int)
    except KeyError as exc:raise ValueError('unknown channel or fragment') from exc
    trend=np.polynomial.legendre.legvander((t-center_s)/scale_s,4)
    base=np.column_stack((trend,300.*np.eye(len(all_fragments))[fi]))
    contrast=helmert(len(all_channels),full=False).T
    clock=rate_sigma_hz_s*(t-150.)[:,None]*contrast[ci]
    return base,clock


def fit(base,clock,values,sigma_hz):
    b,c,y,s=map(lambda v:np.asarray(v,float),(base,clock,values,sigma_hz))
    if b.ndim!=2 or b.shape[1]<5 or c.ndim!=2 or len(c)!=len(b) or y.shape!=(len(b),) or s.shape!=y.shape or len(y)<10:
        raise ValueError('ten matching observations, quartic base and channel clock design required')
    if not all(np.isfinite(v).all() for v in (b,c,y,s)) or np.any(s<=0):raise ValueError('finite data and positive per-point RF noise required')
    x=np.column_stack((b,c));a=x/s[:,None];z=y/s;precision=np.r_[np.zeros(5),np.ones(x.shape[1]-5)]
    normal=a.T@a+np.diag(precision);root=np.linalg.cholesky((normal+normal.T)/2)
    covariance=np.linalg.solve(root.T,np.linalg.solve(root,np.eye(len(root))))
    coefficient=np.linalg.solve(root.T,np.linalg.solve(root,a.T@z));residual=z-a@coefficient
    score=float(residual@residual+np.sum(precision*coefficient**2)+2*np.log(np.diag(root)).sum())
    return dict(coefficient=coefficient,covariance=covariance,score=score,base_width=b.shape[1],clock_width=c.shape[1])


def baseline_prediction(model,base,sigma_hz):
    b,s=np.asarray(base,float),np.asarray(sigma_hz,float)
    return b@np.asarray(model['coefficient']),np.diag(s*s)+b@np.asarray(model['covariance'])@b.T


def transfer(source,target_baseline,base_train,clock_train,sigma_train,base_test,clock_test,sigma_test):
    """Cut prediction: clock inferred solely on source, target learns its trend."""
    b,c,s,bt,ct,st=map(lambda a:np.asarray(a,float),(base_train,clock_train,sigma_train,base_test,clock_test,sigma_test))
    if c.shape[1]!=source['clock_width'] or ct.shape[1]!=source['clock_width'] or target_baseline['clock_width']!=0:
        raise ValueError('same channel contrasts and clock-free target baseline required')
    width=source['base_width'];mean=np.asarray(source['coefficient'])[width:];cov=np.asarray(source['covariance'])[width:,width:]
    target_cov=np.asarray(target_baseline['covariance']);projection=target_cov@b.T@(c/s[:,None]**2)
    innovation=ct-bt@projection
    predicted=bt@np.asarray(target_baseline['coefficient'])+innovation@mean
    variance=np.diag(st*st)+bt@target_cov@bt.T+innovation@cov@innovation.T
    return predicted,variance
