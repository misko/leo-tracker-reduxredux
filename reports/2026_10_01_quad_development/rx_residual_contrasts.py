"""Offset-free aligned receiver contrasts and covariance propagation."""
import numpy as np


def helmert(n):
    H=np.zeros((n-1,n))
    for k in range(1,n):
        H[k-1,:k]=1/np.sqrt(k*(k+1));H[k-1,k]=-k/np.sqrt(k*(k+1))
    return H


def compare(r0,V0,r1,V1):
    r0=np.asarray(r0,float);r1=np.asarray(r1,float)
    if r0.shape!=r1.shape or r0.ndim!=1 or len(r0)<2:raise ValueError('requires matched vectors of length >=2')
    H=helmert(len(r0));a=H@r0;b=H@r1
    V=H@(np.asarray(V0)+np.asarray(V1))@H.T/2
    L=np.linalg.cholesky(V)
    common=np.linalg.solve(L,(a+b)/np.sqrt(2));difference=np.linalg.solve(L,(a-b)/np.sqrt(2))
    return dict(dimension=len(a),common_energy=float(common@common),differential_energy=float(difference@difference),
                receiver0_contrasts=a.tolist(),receiver1_contrasts=b.tolist())
