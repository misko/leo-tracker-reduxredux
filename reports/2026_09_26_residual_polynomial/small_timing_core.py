"""OLS constant profiles and training-only shared satellite timing."""
import numpy as np


def profile(measured,predictions,training):
    y=np.asarray(measured,float); pred=np.asarray(predictions,float);mask=np.asarray(training,bool)
    if not mask.any() or mask.all():raise ValueError('both partitions required')
    residual=y[None,:]-pred
    offset=residual[:,mask].mean(axis=1)
    residual-=offset[:,None]
    return {'train_sse':np.sum(residual[:,mask]**2,axis=1),
            'eval_mse':np.mean(residual[:,~mask]**2,axis=1),'offset':offset}


def choose_shared(rows,grid):
    selected={}
    for cid in sorted({r['satellite_id'] for r in rows}):
        loss=sum(r['train_sse'] for r in rows if r['satellite_id']==cid)
        selected[cid]=min(range(len(grid)),key=lambda j:(loss[j],abs(grid[j]),grid[j]))
    return selected


def aggregate(rows,key):
    mse=np.array([r[key] for r in rows]);n=np.array([r['observations'] for r in rows])
    return {'equal_track_rms_hz':float(np.sqrt(np.mean(mse))),
            'size_weighted_rms_hz':float(np.sqrt(np.average(mse,weights=n)))}
