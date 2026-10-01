"""Experimental elevation differential for line-of-sight and receiver normal."""
import numpy as np


def elevation_jacobian(line,normal,line_jacobian,normal_jacobian):
    line=np.asarray(line,dtype=float);normal=np.asarray(normal,dtype=float)
    dl=np.asarray(line_jacobian,dtype=float);dn=np.asarray(normal_jacobian,dtype=float)
    if line.shape!=normal.shape or line.shape[-1:]!=(3,) or dl.shape!=dn.shape or dl.shape[:-1]!=line.shape:
        raise ValueError('aligned vectors and vector-by-parameter derivatives required')
    if not all(np.all(np.isfinite(a)) for a in [line,normal,dl,dn]):raise ValueError('finite inputs required')
    radius=np.linalg.norm(line,axis=-1);scale=np.linalg.norm(normal,axis=-1)
    if np.any(radius<=0) or np.any(scale<=0):raise ValueError('nonzero vectors required')
    unit=line/radius[...,None];up=normal/scale[...,None]
    du=(dl-unit[...,None]*np.einsum('...i,...id->...d',unit,dl)[...,None,:])/radius[...,None,None]
    dn_unit=(dn-up[...,None]*np.einsum('...i,...id->...d',up,dn)[...,None,:])/scale[...,None,None]
    sine=np.einsum('...i,...i->...',unit,up)
    cosine_squared=1-sine*sine
    if np.any(cosine_squared<=1e-12):raise ValueError('zenith/nadir elevation derivative is singular')
    ds=np.einsum('...i,...id->...d',up,du)+np.einsum('...i,...id->...d',unit,dn_unit)
    return np.degrees(np.arcsin(sine)),np.degrees(ds/np.sqrt(cosine_squared)[...,None])
