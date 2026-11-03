"""Bounded state-revision predictor learned without radio or station data."""
import numpy as np
from scipy.optimize import minimize_scalar


def bounded(revision):
    revision=np.asarray(revision,float)
    if revision.ndim!=2 or revision.shape[1]!=6 or not np.isfinite(revision).all():raise ValueError('expected finite N by6 states')
    factors=np.minimum(1.,np.minimum(5/np.maximum(np.linalg.norm(revision[:,:3],axis=1),1e-30),.005/np.maximum(np.linalg.norm(revision[:,3:],axis=1),1e-30)))
    return revision*factors[:,None]


def fit(previous,next_revision):
    x=bounded(previous)[:,:3];y=np.asarray(next_revision)[:,:3]
    def objective(a):return float(np.sum(np.sqrt(1+np.sum((a*x-y)**2,axis=1))-1))
    result=minimize_scalar(objective,bounds=(-1.,1.),method='bounded',options=dict(xatol=1e-12,maxiter=500))
    alpha=min([float(result.x),-1.,1.],key=objective)
    residual=alpha*x-y
    gradient=float(np.sum(np.sum(x*residual,axis=1)/np.sqrt(1+np.sum(residual**2,axis=1))))
    projected=0. if (alpha==-1 and gradient>=0) or (alpha==1 and gradient<=0) else abs(gradient)
    return dict(alpha=alpha,objective=objective(alpha),gradient=gradient,projected_gradient=projected,qualified=bool(result.success and projected<1e-4))


def metrics(previous,next_revision,alpha):
    x=bounded(previous);y=np.asarray(next_revision);error=y-alpha*x
    position=np.linalg.norm(error[:,:3],axis=1);velocity=np.linalg.norm(error[:,3:],axis=1)*1000
    return dict(median_position_km=float(np.median(position)),mean_position_km=float(np.mean(position)),median_velocity_m_s=float(np.median(velocity)),mean_velocity_m_s=float(np.mean(velocity))),position
