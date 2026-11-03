"""Batch orbit-only timing queries; calibration still uses original times."""
from dataclasses import replace
import numpy as np


def batches(predictor,bank,observations,prior,point,grid,chunk_size=16):
    grid=np.asarray(grid,float)
    if grid.ndim!=1 or not np.isfinite(grid).all() or chunk_size<1:
        raise ValueError('Finite timing grid and positive chunk size required')
    count=len(observations.times_s)
    for start in range(0,len(grid),chunk_size):
        selected=grid[start:start+chunk_size];width=len(selected)
        query=replace(observations,
            window_ids=tuple(f'timing-query-{i}' for i in range(width*count)),
            times_s=(selected[:,None]+observations.times_s[None,:]).ravel(),
            measured_hz=np.zeros(width*count),
            rf_hz=np.tile(observations.rf_hz,width),receiver=np.tile(observations.receiver,width),
            channel=np.tile(observations.channel,width),margin=np.ones(width*count))
        prediction,visible,_,_=predictor(bank,query,prior,point,np.zeros(len(bank.numbers)),derivatives=False)
        yield start,prediction.reshape(width,count,-1),visible.reshape(width,count,-1)
