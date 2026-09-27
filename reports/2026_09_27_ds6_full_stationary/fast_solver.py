"""Vectorized initialization of the same scalar stationary offset search."""
import numpy as np
from scipy.optimize import brentq
from scipy.special import gammaln


def fit(train,sigma=100.):
    train=np.asarray(train,dtype=float)
    center=float(np.median(train));y=train-center
    def loss(v):return float(2.5*np.log1p(((y-v)/sigma)**2/4).sum()+.5*((center+v)/1e6)**2)
    def derivative(v):
        r=v-y
        return float(np.sum(5*r/(4*sigma*sigma+r*r))+(center+v)/1e12)
    def curvature(v):
        r=v-y;den=4*sigma*sigma+r*r
        return float(np.sum(5*(4*sigma*sigma-r*r)/(den*den))+1e-12)
    # Every penalized stationary optimum lies between zero and the data range.
    lower=min(float(y.min()),-center);upper=max(float(y.max()),-center)
    if lower==upper:return center+lower,dict(converged=True,gradient=0.,curvature=curvature(lower),roots=1)
    starts=np.unique(np.r_[np.quantile(y,np.linspace(0,1,9)),0.])
    values=starts.copy();active=np.ones(len(starts),dtype=bool)
    for _ in range(100):
        r=(y[None,:]-values[:,None])/sigma;w=5/(4+r*r)
        new=((w*y[None,:]).sum(axis=1)-sigma*sigma*center/1e12)/(w.sum(axis=1)+sigma*sigma/1e12)
        done=np.abs(new-values)<1e-6
        values=np.where(active,new,values);active&=~done
        if not active.any():break
    distances=np.array([1e-4,.01,1.,10.,100.,1000.])
    nodes=np.unique(np.r_[lower,upper,starts,values,
        np.clip(values[:,None]-distances,lower,upper).ravel(),
        np.clip(values[:,None]+distances,lower,upper).ravel()])
    residual=nodes[:,None]-y[None,:]
    values=np.sum(5*residual/(4*sigma*sigma+residual*residual),axis=1)+(center+nodes)/1e12
    roots=[]
    for i in range(len(nodes)-1):
        if values[i]<=0<=values[i+1]:
            root=brentq(derivative,nodes[i],nodes[i+1],xtol=1e-9,rtol=1e-14)
            if curvature(root)>0:roots.append(root)
    if not roots:raise RuntimeError('No positive-curvature stationary offset found')
    best=min(roots,key=loss);gradient=derivative(best)
    return center+best,dict(converged=abs(gradient)<1e-7,gradient=gradient,curvature=curvature(best),roots=len(roots))


def profile(residual,mask):
    residual=np.asarray(residual);flat=residual.reshape(-1,residual.shape[-1]);offsets=[];audits=[]
    for row in flat:
        offset,audit=fit(row[mask]);offsets.append(offset);audits.append(audit)
    offsets=np.array(offsets);z=(flat-offsets[:,None])/100.
    density=gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(100.)-2.5*np.log1p(z*z/4)
    train=density[:,mask].sum(axis=-1)-.5*offsets**2/1e12
    joint=train+density[:,~mask].sum(axis=-1)
    return train.reshape(residual.shape[:-1]),joint.reshape(residual.shape[:-1]),audits,offsets.reshape(residual.shape[:-1])


def scores(residual,mask):return profile(residual,mask)[:3]
