"""Frozen random whole-block partitions used by the evaluated recovery."""
import numpy as np

def split(times,seed):
    groups=np.floor(times/12).astype(int);unique=np.unique(groups);rng=np.random.default_rng(seed)
    chosen=rng.choice(unique,max(1,round(len(unique)/3)),replace=False)
    held=np.isin(groups,chosen);train=~held
    for g in chosen:train&=(times<g*12-2)|(times>=(g+1)*12+2)
    return train,held,chosen
