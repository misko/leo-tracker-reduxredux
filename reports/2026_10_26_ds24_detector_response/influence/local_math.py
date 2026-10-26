"""Frozen Gaussian mean susceptibility, not a measured bias or error forecast."""
import numpy as np


def position_response(j, u, weights, gram, cross, information):
    response=np.linalg.solve(gram,cross)
    effective=j-u@response
    h=np.linalg.solve(information,effective.T*weights)
    replay=j.T@(weights[:,None]*effective)
    if not np.isfinite(h).all() or not np.allclose(replay,information,rtol=1e-6,atol=1e-7):
        raise ValueError('saved Schur information replay failed')
    return h,float(np.max(abs(replay-information)))


def bias_basis(times, q):
    """At reference RF, coefficient unit norm gives 1 Hz RMS over these IDs."""
    times=np.asarray(times,float);q=np.asarray(q,float)
    if len(times)!=len(q) or len(times)==0 or not np.isfinite(np.r_[times,q]).all():
        raise ValueError('finite original observation times/RF factors required')
    degree=min(2,len(np.unique(times))-1)
    z=np.zeros(len(times)) if degree==0 else 2*(times-times.min())/np.ptp(times)-1
    design=np.polynomial.legendre.legvander(z,degree)
    basis,_=np.linalg.qr(design,mode='reduced')
    return q[:,None]*basis*np.sqrt(len(times))


def susceptibility(h, weak, indices, times, q):
    b=bias_basis(times,q)
    vector=np.asarray(weak)@h[:,np.asarray(indices,dtype=int)]@b
    return float(np.linalg.norm(vector)),b,vector


def quantile_indices(n):
    if n<2:raise ValueError('two distinct original windows required')
    return [int(np.floor(.25*(n-1)+.5)),int(np.floor(.75*(n-1)+.5))]
