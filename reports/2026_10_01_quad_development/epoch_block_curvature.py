"""Solve candidate-weighted residual curvature with independent epoch blocks.

Each candidate contributes a 6x6 block for five scan coordinates and its epoch.
Eliminate diagonal epochs, then solve only shared position and scan nuisances.
"""
import numpy as np


def solve_blocks(precision,column_maps,blocks,gradient):
    precision=np.asarray(precision,dtype=float);gradient=np.asarray(gradient,dtype=float)
    maps=[np.asarray(c,dtype=int) for c in column_maps]
    if len(maps)!=len(blocks) or not maps or gradient.shape!=precision.shape:
        raise ValueError('aligned curvature blocks required')
    core=np.array(sorted({int(i) for c in maps for i in c[:5]}),dtype=int)
    epochs=np.array(sorted(set(range(len(precision)))-set(core)),dtype=int)
    core_lookup={int(c):i for i,c in enumerate(core)};epoch_lookup={int(c):i for i,c in enumerate(epochs)}
    a=np.diag(precision[core]);b=np.zeros((len(core),len(epochs)));diagonal=precision[epochs].copy()
    for columns,curvature in zip(maps,blocks,strict=True):
        curvature=np.asarray(curvature,dtype=float)
        if curvature.shape!=(len(columns)-5,6,6) or not np.all(np.isfinite(curvature)):
            raise ValueError('invalid candidate curvature shape or values')
        c=np.array([core_lookup[int(i)] for i in columns[:5]])
        e=np.array([epoch_lookup[int(i)] for i in columns[5:]])
        a[np.ix_(c,c)]+=np.sum(curvature[:,:5,:5],axis=0)
        b[np.ix_(c,e)]+=curvature[:,:5,5].T
        diagonal[e]+=curvature[:,5,5]
    if (not np.all(np.isfinite(precision)) or not np.all(np.isfinite(gradient))
            or np.any(precision<0) or np.any(diagonal<=0)):
        raise ValueError('finite state and positive epoch precision required')
    inv=1/diagonal;schur=a-(b*inv)@b.T
    chol=np.linalg.cholesky((schur+schur.T)/2)
    rhs=gradient[core]-b@(inv*gradient[epochs])
    shared=np.linalg.solve(chol.T,np.linalg.solve(chol,rhs))
    result=np.empty_like(gradient);result[core]=shared;result[epochs]=inv*(gradient[epochs]-b.T@shared)
    if not np.all(np.isfinite(result)):raise ValueError('nonfinite curvature solve')
    return result
