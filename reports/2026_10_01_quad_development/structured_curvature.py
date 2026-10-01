"""Solve a two-position plus diagonal-prior nuisance curvature system.

The curvature is diag(precision) + whitened_rows.T @ whitened_rows.
Nuisance elimination uses Woodbury; the position Schur complement is 2 x 2.
This is a direction preconditioner, not an uncertainty calibration.
"""
import numpy as np


def solve_curvature(precision, whitened_rows, gradient):
    precision=np.asarray(precision,dtype=float)
    rows=np.asarray(whitened_rows,dtype=float)
    gradient=np.asarray(gradient,dtype=float)
    if (precision.ndim!=1 or len(precision)<3 or gradient.shape!=precision.shape
            or rows.ndim!=2 or rows.shape[1]!=len(precision)
            or not all(np.all(np.isfinite(a)) for a in [precision,rows,gradient])
            or np.any(precision[:2]<0) or np.any(precision[2:]<=0)):
        raise ValueError('finite compatible arrays and positive nuisance precision required')
    p,n=rows[:,:2],rows[:,2:]
    inv=1/precision[2:]
    cross=n.T@p
    rhs=np.column_stack([gradient[2:],cross])
    weighted=inv[:,None]*rhs
    middle=np.eye(len(rows))+(n*inv)@n.T
    nuisance_solutions=weighted-inv[:,None]*(n.T@np.linalg.solve(middle,n@weighted))
    schur=np.diag(precision[:2])+p.T@p-cross.T@nuisance_solutions[:,1:]
    # Reject unidentifiable position geometry instead of silently adding a prior.
    chol=np.linalg.cholesky((schur+schur.T)/2)
    position_rhs=gradient[:2]-cross.T@nuisance_solutions[:,0]
    position=np.linalg.solve(chol.T,np.linalg.solve(chol,position_rhs))
    nuisance=nuisance_solutions[:,0]-nuisance_solutions[:,1:]@position
    answer=np.r_[position,nuisance]
    if not np.all(np.isfinite(answer)):raise ValueError('nonfinite curvature solve')
    return answer
