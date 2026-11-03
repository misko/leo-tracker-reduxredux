"""Exact three-track MAP assignment on a fixed candidate/timing grid."""
import numpy as np
from scipy.optimize import linear_sum_assignment

PARTITIONS=(((0,),(1,),(2,)),((0,1),(2,)),((0,2),(1,)),((1,2),(0,)),((0,1,2),))


def select(data_cost,timing_prior):
    cost,prior=np.asarray(data_cost,float),np.asarray(timing_prior,float)
    if (cost.ndim!=3 or cost.shape[0]!=3 or cost.shape[1]!=len(prior)
            or cost.shape[2]<1 or not np.isfinite(prior).all()
            or np.isnan(cost).any() or np.any(cost<0) or np.any(prior<0)):
        raise ValueError('Three nonnegative track cost grids and a finite timing prior required')
    best=None
    for partition in PARTITIONS:
        if len(partition)>cost.shape[2]:continue
        grids=[cost[list(block)].sum(axis=0)+prior[:,None] for block in partition]
        block_cost=np.array([grid.min(axis=0) for grid in grids])
        try:row,col=linear_sum_assignment(block_cost)
        except ValueError:continue
        if len(row)!=len(partition):continue
        value=float(block_cost[row,col].sum())
        if not np.isfinite(value) or (best is not None and value>=best['score']):continue
        identities=np.zeros(3,int);timings=np.zeros(3,int)
        for block_index,k in zip(row,col):
            t=int(grids[block_index][:,k].argmin())
            for group in partition[block_index]:identities[group]=k;timings[group]=t
        best=dict(score=value,candidate_indices=identities,timing_indices=timings,
                  partition=[list(block) for block in partition])
    if best is None:raise ValueError('No jointly visible candidate assignment')
    return best
