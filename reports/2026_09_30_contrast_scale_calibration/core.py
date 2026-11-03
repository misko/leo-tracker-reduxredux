"""Sufficient-statistic q020 contrast likelihood and log-scale derivatives."""
import math
import numpy as np
from scipy.special import logsumexp


def moments(y,t,prediction,visible):
    y,t=np.asarray(y),np.asarray(t)
    residual=y[None,:]-prediction
    residual-=residual[:,:1]
    residual-=residual.mean(axis=1,keepdims=True)
    yy=y-y[0];yy-=yy.mean()
    tt=t-t[0];tt-=tt.mean()
    t2=float(tt@tt)
    if t2:
        direction=tt/math.sqrt(t2);projection=float(yy@direction)
        perpendicular=yy-projection*direction
        perpendicular2=float(perpendicular@perpendicular)
        projection2=projection**2
    else:
        perpendicular2=float(yy@yy);projection2=0.
    return dict(n=len(y),candidate_ss=(residual**2).sum(axis=1).tolist(),visible=np.asarray(visible,bool).tolist(),
                perpendicular2=perpendicular2,projection2=projection2,slope_variance=2000.**2*t2)


def pack(records):
    width=max(len(r['candidate_ss']) for r in records)
    ss=np.zeros((len(records),width));visible=np.zeros_like(ss,dtype=bool)
    for i,r in enumerate(records):
        ss[i,:len(r['candidate_ss'])]=r['candidate_ss']
        visible[i,:len(r['visible'])]=r['visible']
    assert np.all(visible.sum(axis=1)>0)
    n=np.array([r['n'] for r in records]);d=n-1
    constant=np.array([math.lgamma((4+v)/2)-math.lgamma(2)-.5*v*math.log(4*math.pi) for v in d])-.5*np.log(n)
    return dict(ss=ss,visible=visible,d=d,constant=constant,
                perpendicular2=np.array([r['perpendicular2'] for r in records]),
                projection2=np.array([r['projection2'] for r in records]),
                slope_variance=np.array([r['slope_variance'] for r in records]))


def density(stats,logscale):
    variance=np.exp(2*logscale)
    q=stats['ss']/variance[:,None];d=stats['d']
    signal=stats['constant'][:,None]-d[:,None]*logscale[:,None]-(4+d[:,None])/2*np.log1p(q/4)
    signal=np.where(stats['visible'],signal,-np.inf)
    signal_gradient=-d[:,None]+(4+d[:,None])*q/(4+q)
    count=stats['visible'].sum(axis=1)
    k=stats['slope_variance'];den=variance+k
    qp=stats['perpendicular2']/variance
    qb=qp+stats['projection2']/den
    bg=stats['constant']-d*logscale-.5*np.log1p(k/variance)-(4+d)/2*np.log1p(qb/4)
    bg_gradient=-d+k/den+(4+d)/(4+qb)*(qp+variance*stats['projection2']/den**2)
    terms=np.column_stack([signal+np.log(.8)-np.log(count[:,None]),bg+np.log(.2)])
    gradients=np.column_stack([signal_gradient,bg_gradient])
    normal=logsumexp(terms,axis=1)
    derivative=(np.exp(terms-normal[:,None])*gradients).sum(axis=1)
    return normal,derivative


def conditional(train,full,logscale):
    a,ga=density(train,logscale);b,gb=density(full,logscale)
    return b-a,gb-ga
