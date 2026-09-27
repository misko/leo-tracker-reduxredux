"""Vectorized multistart Student-t offsets, with stationary scalar fallback."""
import importlib.util
from pathlib import Path
import numpy as np
from scipy.special import gammaln
path=Path(__file__).resolve().parent.parent/'2026_09_27_ds6_stationary_offsets/solver.py'
spec=importlib.util.spec_from_file_location('reference',path);reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)


def fit(train):
    train=np.asarray(train,float);shape=train.shape[:-1];flat=train.reshape(-1,train.shape[-1]);center=np.median(flat,axis=1);y=flat-center[:,None]
    v=np.quantile(y,np.linspace(0,1,9),axis=1).T
    # Batched starts retain different attraction basins. Fixed iteration is
    # initialization only; acceptance below requires derivative and curvature.
    for _ in range(60):
        r=y[:,None,:]-v[:,:,None];w=5/(40000+r*r)
        v=(np.sum(w*y[:,None,:],axis=-1)-center[:,None]/1e12)/(np.sum(w,axis=-1)+1e-12)
    def terms(values):
        r=values[:,:,None]-y[:,None,:];den=40000+r*r
        loss=2.5*np.log1p(r*r/40000).sum(axis=-1)+.5*((values+center[:,None])/1e6)**2
        gradient=np.sum(5*r/den,axis=-1)+(values+center[:,None])/1e12
        curvature=np.sum(5*(40000-r*r)/(den*den),axis=-1)+1e-12
        return loss,gradient,curvature
    for _ in range(18):
        loss,g,h=terms(v);active=(abs(g)>1e-11)&(h>0)
        if not active.any():break
        step=np.where(active,g/np.maximum(h,1e-18),0.);step=np.clip(step,-1000,1000)
        for _ in range(20):
            trial=v-step;newloss,_,_=terms(trial);bad=(newloss>loss+1e-12)&active
            if not bad.any():break
            step=np.where(bad,step*.5,step)
        v=np.where(newloss<=loss+1e-12,trial,v)
    loss,g,h=terms(v);valid=(abs(g)<1e-9)&(h>0)
    chosen=np.argmin(np.where(valid,loss,np.inf),axis=1);idx=np.arange(len(flat));offset=center+v[idx,chosen];fallback=~valid.any(axis=1)
    # A failed competing start could hide a better mode: do not merely keep
    # whichever easy start happened to converge.
    fallback|=np.any((~valid)&(loss<loss[idx,chosen,None]+1e-7),axis=1)
    # Initial basins alone can miss a better stationary root. Audit sign
    # brackets spanning starts, converged points, local neighborhoods and
    # the full penalized data interval before accepting the fast solution.
    initial=np.quantile(y,np.linspace(0,1,9),axis=1).T
    lower=np.minimum(y.min(axis=1),-center);upper=np.maximum(y.max(axis=1),-center)
    nodes=[initial,v,lower[:,None],upper[:,None]]
    for distance in [1e-4,.01,1.,10.,100.,1000.]:
        nodes.extend([np.maximum(lower[:,None],v-distance),np.minimum(upper[:,None],v+distance)])
    nodes=np.sort(np.concatenate(nodes,axis=1),axis=1)
    rr=nodes[:,:,None]-y[:,None,:]
    dg=(5*rr/(40000+rr*rr)).sum(axis=-1)+(nodes+center[:,None])/1e12
    crossings=(dg[:,:-1]<=0)&(dg[:,1:]>=0)&(nodes[:,1:]>nodes[:,:-1])
    covered=np.any(valid[:,None,:]&(v[:,None,:]>=nodes[:,:-1,None]-1e-7)&(v[:,None,:]<=nodes[:,1:,None]+1e-7),axis=-1)
    fallback|=np.any(crossings&~covered,axis=1)
    for i in np.flatnonzero(fallback):offset[i],_=reference.fit(flat[i])
    r=offset[:,None]-flat;den=40000+r*r;gradient=(5*r/den).sum(axis=1)+offset/1e12;curvature=(5*(40000-r*r)/(den*den)).sum(axis=1)+1e-12
    if np.any(abs(gradient)>1e-7) or np.any(curvature<=0):raise RuntimeError('Offset stationarity failure')
    return offset.reshape(shape),dict(fallbacks=int(fallback.sum()),candidates=len(flat),max_gradient=float(abs(gradient).max()))


def scores(residual,mask,sigma=100.):
    assert sigma==100.
    residual=np.asarray(residual);offset,audit=fit(residual[...,mask]);z=(residual-offset[...,None])/100.
    density=gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(100.)-2.5*np.log1p(z*z/4)
    train=density[...,mask].sum(axis=-1)-.5*offset**2/1e12
    return train,train+density[...,~mask].sum(axis=-1),audit
