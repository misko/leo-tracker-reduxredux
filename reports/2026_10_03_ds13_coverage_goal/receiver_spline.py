"""Small zero-centered shared receiver drift; no satellite/channel parameters."""
import numpy as np

NODES=np.linspace(0.,300.,11)
# Exact removal of constant/linear components on the fixed knot grid.
NULL=np.linalg.svd(np.stack([np.ones(11),(NODES-150)/150]),full_matrices=True)[2][2:].T
SECOND=np.diff(np.eye(11),n=2,axis=0)
PRECISION=np.eye(9)/50.**2+(SECOND@NULL).T@(SECOND@NULL)/25.**2


def design(times):
    times=np.asarray(times,float)
    if np.any((times<0)|(times>300)):raise ValueError('Outside scan support')
    return np.column_stack([np.interp(times,NODES,np.eye(11)[:,j]) for j in range(11)])@NULL


def fit(times,receiver,residual):
    times=np.asarray(times);receiver=np.asarray(receiver);residual=np.asarray(residual)
    if not(times.shape==receiver.shape==residual.shape):raise ValueError('Training shape mismatch')
    if not np.all(np.isfinite(residual)):raise ValueError('Nonfinite training residual')
    if np.any(~np.isin(receiver,[0,1])):raise ValueError('Unknown receiver')
    x=design(times);result=np.zeros((2,9))
    for rx in (0,1):
        mask=receiver==rx;a=x[mask];y=residual[mask]
        if not len(y):continue
        weights=np.ones(len(y))/200.**2
        for _ in range(3):
            beta=np.linalg.solve(a.T@(weights[:,None]*a)+PRECISION,a.T@(weights*y))
            weights=np.minimum(1.,200./np.maximum(abs(y-a@beta),1e-9))/200.**2
        result[rx]=beta
    return result


def predict(parameters,times,receiver):
    x=design(times);receiver=np.asarray(receiver,int)
    if np.any(~np.isin(receiver,[0,1])):raise ValueError('Unknown receiver')
    return np.sum(x*np.asarray(parameters)[receiver],axis=1)
