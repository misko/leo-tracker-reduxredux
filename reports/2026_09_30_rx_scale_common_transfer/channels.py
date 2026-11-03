"""Reconstruct matched RX channels with training-only centering."""
import numpy as np


def channels(a,b):
    ta,tb=np.asarray(a['times']),np.asarray(b['times'])
    distances=abs(ta[:,None]-tb[None,:])
    ab=distances.argmin(axis=1);ba=distances.argmin(axis=0)
    ia=np.array([i for i,j in enumerate(ab) if ba[j]==i and distances[i,j]<=1e-6],dtype=int)
    ib=ab[ia]
    ma,mb=np.asarray(a['mask'],bool)[ia],np.asarray(b['mask'],bool)[ib]
    train=ma&mb;held=~ma&~mb
    assert train.sum()>=8 and held.sum()>=3 and np.ptp(ta[ia][train])>=5
    e0,e1=np.asarray(a['residual'])[ia],np.asarray(b['residual'])[ib]
    raw=dict(rx0=e0,rx1=e1,common=(e0+e1)/2,difference=e0-e1)
    centers={name:float(np.median(values[train])) for name,values in raw.items()}
    return dict(centers=centers,held={name:(values[held]-centers[name]).tolist() for name,values in raw.items()},
                feature=max(1.,1.4826*float(np.median(abs(raw['difference'][train]-centers['difference'])))),
                training_pairs=int(train.sum()),held_pairs=int(held.sum()))
