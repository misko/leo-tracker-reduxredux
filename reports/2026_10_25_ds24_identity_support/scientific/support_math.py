"""Positive Woodbury energy and independently checked log-domain integration."""
import numpy as np
from scipy.integrate import tanhsinh
from scipy.linalg import solve_triangular
from scipy.special import logsumexp,roots_legendre

CHUNK=512
TOL=1e-3
LOG_RTOL=np.log(1e-9)


def positive_costs(raw,covariance,shape,shifts):
    root=np.linalg.cholesky(covariance)
    white=solve_triangular(root,np.asarray(raw).T,lower=True).T
    alias=solve_triangular(root,np.asarray(shifts).T,lower=True).T
    b=np.asarray(shape);n,m,k=b.shape
    wb=solve_triangular(root,b.transpose(1,0,2).reshape(m,-1),lower=True).reshape(m,n,k).transpose(1,0,2)
    gram=np.eye(k)[None]+np.einsum('nki,nkj->nij',wb,wb)
    logdet=2*np.log(np.diag(root)).sum()+np.linalg.slogdet(gram)[1]
    values=[]
    for shift in alias:
        w=white+shift
        rhs=np.einsum('nki,nk->ni',wb,w)
        coefficient=np.linalg.solve(gram,rhs[...,None])[...,0]
        residual=w-np.einsum('nki,ni->nk',wb,coefficient)
        energy=np.sum(residual**2,axis=1)+np.sum(coefficient**2,axis=1)
        values.append(energy+logdet+m*np.log(2*np.pi))
    return np.column_stack(values)


def objective_error_bound(log_integral,log_error):
    relative=float(np.exp(min(710.,log_error-log_integral)))
    if not np.isfinite(relative) or relative>=1:return None
    return float(2*max(np.log1p(relative),-np.log1p(-relative)))


def log_integrate(fun,pieces):
    pieces=np.asarray(pieces,float).reshape(-1,2)
    if not len(pieces):return dict(log_integral=None,log_error=None,objective=None,error_bound=0.,success=True,panels=0,status_counts={})
    def wrapped(x):
        flat=np.asarray(x).reshape(-1);values=[]
        for start in range(0,len(flat),CHUNK):values.append(fun(flat[start:start+CHUNK]))
        return np.concatenate(values).reshape(np.shape(x))
    result=tanhsinh(wrapped,pieces[:,0],pieces[:,1],log=True,minlevel=0,maxlevel=6,
        atol=-np.inf,rtol=LOG_RTOL)
    integral=float(logsumexp(result.integral));error=float(logsumexp(result.error))
    bound=objective_error_bound(integral,error)
    status,count=np.unique(result.status,return_counts=True)
    finite=bool(np.isfinite(integral) and not np.isnan(error))
    return dict(log_integral=integral if finite else None,log_error=error if np.isfinite(error) else None,
        objective=-2*integral if finite else None,error_bound=bound,
        success=bool(finite and bound is not None and bound<=1e-4 and np.all(result.success)),
        panels=len(pieces),status_counts={str(int(s)):int(c) for s,c in zip(status,count,strict=True)},
        evaluations=int(np.sum(result.nfev)),maximum_level=int(np.max(result.maxlevel)))


def composite(fun,pieces,order):
    pieces=np.asarray(pieces,float).reshape(-1,2)
    if not len(pieces):return None
    z,w=roots_legendre(order);half=(pieces[:,1]-pieces[:,0])/2;center=pieces.mean(axis=1)
    nodes=center[:,None]+half[:,None]*z;weights=np.log(half[:,None])+np.log(w)[None]
    flat=nodes.reshape(-1);logs=[]
    for start in range(0,len(flat),CHUNK):logs.append(fun(flat[start:start+CHUNK]))
    return float(logsumexp(np.concatenate(logs).reshape(nodes.shape)+weights))


def reference(fun,pieces):
    first=composite(fun,pieces,32);second=composite(fun,pieces,64)
    if first is None:return dict(objective=None,score_error=0.,success=True,orders=[32,64])
    error=2*abs(first-second)
    return dict(objective=-2*second,score_error=float(error),success=bool(np.isfinite(second) and error<=TOL),orders=[32,64])


def support_range(inner,brackets):
    if inner['log_integral'] is None:
        return dict(score_uncertainty=0. if brackets['log_integral'] is None else None,objective=None,success=brackets['log_integral'] is None)
    outer=float(np.logaddexp(inner['log_integral'],brackets['log_integral'])) if brackets['log_integral'] is not None else inner['log_integral']
    uncertainty=2*(outer-inner['log_integral'])
    return dict(objective=inner['objective'],outer_objective=-2*outer,score_uncertainty=float(uncertainty),
        success=bool(uncertainty<=1e-4 and inner['success'] and brackets['success']))
