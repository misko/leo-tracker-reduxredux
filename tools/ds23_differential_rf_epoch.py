"""Actual carrier-contrast time response, including refitted code coordinates."""

import numpy as np


def frequency_rate_response(workspace,parameters):
    p=workspace;parameters=np.asarray(parameters,float)
    (a,da),(b,db)=[p.columns_and_derivatives(v,k) for k,v in enumerate(parameters.reshape(2,3))]
    design=np.column_stack((a,b,np.ones(len(p.y))));normal=np.zeros((6,6));cross=np.zeros((6,2))
    for ix in p.segments:
        x=design[ix];coefficient=np.linalg.lstsq(x,p.y[ix],rcond=1e-8)[0]
        derivative=np.column_stack((np.einsum('nij,i->nj',da[ix],coefficient[:8]),np.einsum('nij,i->nj',db[ix],coefficient[8:16])))
        signal=np.column_stack((a[ix]@coefficient[:8],b[ix]@coefficient[8:16]))
        rate=1j*np.pi*p.centered[ix,None]**2*signal
        q,_=np.linalg.qr(x,mode='reduced');derivative-=q@(q.conj().T@derivative);rate-=q@(q.conj().T@rate)
        normal+=(derivative.conj().T@derivative).real;cross+=(derivative.conj().T@rate).real
    contrast=np.array([100.,0.,0.,-100.,0.,0.])
    return contrast@np.linalg.solve(normal,cross)


def inject_component_rates(workspace,parameters,rates_hz_s):
    p=workspace;rates=np.asarray(rates_hz_s,float)
    if rates.shape!=(2,) or not np.isfinite(rates).all():raise ValueError('two finite component frequency rates required')
    (a,_),(b,_)=[p.columns_and_derivatives(v,k) for k,v in enumerate(np.asarray(parameters).reshape(2,3))]
    x=np.column_stack((a,b,np.ones(len(p.y))));output=p.y.copy()
    for ix in p.segments:
        c=np.linalg.lstsq(x[ix],p.y[ix],rcond=1e-8)[0]
        signals=np.column_stack((a[ix]@c[:8],b[ix]@c[8:16]))
        output[ix]+=np.sum(signals*np.expm1(1j*np.pi*p.centered[ix,None]**2*rates),axis=1)
    return output
