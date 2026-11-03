"""Matrix-product implementation of stationary receiver acquisition geometry."""
import numpy as np


def stationary_range_rate_grid_blas(positions, velocities, receivers, receiver_up):
    p,v,r,up=(np.asarray(x,dtype=float) for x in (positions,velocities,receivers,receiver_up))
    if (p.ndim!=3 or p.shape[-1]!=3 or v.shape!=p.shape or r.ndim!=2
            or r.shape[-1]!=3 or up.shape!=r.shape
            or any(not np.all(np.isfinite(x)) for x in (p,v,r,up))):
        raise ValueError('invalid Cartesian geometry arrays')
    if not np.allclose(np.linalg.norm(up,axis=1),1.,rtol=1e-12,atol=1e-12):
        raise ValueError('receiver up vectors must be normalized')
    shape=(len(r),*p.shape[:2])
    rp=(r@p.reshape(-1,3).T).reshape(shape)
    squared=np.sum(p*p,axis=-1)[None]+np.sum(r*r,axis=-1)[:,None,None]-2*rp
    if np.any(squared<=0):raise ValueError('nonpositive squared range')
    distance=np.sqrt(squared)
    rv=(r@v.reshape(-1,3).T).reshape(shape)
    rate=(np.sum(p*v,axis=-1)[None]-rv)/distance
    up_p=(up@p.reshape(-1,3).T).reshape(shape)
    sine=(up_p-np.sum(r*up,axis=-1)[:,None,None])/distance
    return rate,np.clip(sine,-1.,1.)
