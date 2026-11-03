"""Same-sample separation of actual and wrong-epoch pilot frame gains."""

import numpy as np


def triple_segments(geometries,minimum_samples=80):
    if len(geometries)!=3:raise ValueError('three component geometries required')
    valid=np.logical_and.reduce([g['valid'] for g in geometries])
    labels=np.column_stack([g['frame'] for g in geometries])
    breaks=np.r_[0,np.flatnonzero(np.any(np.diff(labels,axis=0)!=0,axis=1) | (np.diff(valid.astype(int))!=0))+1,len(valid)]
    candidates=[np.arange(a,b) for a,b in zip(breaks[:-1],breaks[1:],strict=True) if valid[a] and b-a>=minimum_samples]
    used=[set(),set(),set()];chosen=[]
    for ix in sorted(candidates,key=lambda ix:(-len(ix),int(ix[0]))):
        keys=[int(g['frame'][ix[0]]) for g in geometries]
        if any(k in u for k,u in zip(keys,used,strict=True)):continue
        chosen.append(ix)
        for k,u in zip(keys,used,strict=True):u.add(k)
    return sorted(chosen,key=lambda ix:ix[0])


def frame_coefficients(samples,columns,segments):
    y=np.asarray(samples);design=np.column_stack([np.asarray(columns),np.ones(len(y))]);coefficients=[];covariances=[]
    for ix in segments:
        x=design[ix];c,_,rank,singular=np.linalg.lstsq(x,y[ix],rcond=1e-8)
        if rank!=x.shape[1] or singular[-1]/singular[0]<1e-6:raise ValueError('joint epoch designs not resolved')
        residual=y[ix]-x@c;variance=float(np.vdot(residual,residual).real/(len(ix)-rank))
        covariance=variance*np.linalg.inv(x.conj().T@x)
        coefficients.append(c[:-1]);covariances.append(covariance[:-1,:-1])
    return np.array(coefficients),np.array(covariances)
