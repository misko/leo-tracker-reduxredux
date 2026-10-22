"""Exact post-fit time lookup for original and appended native observations."""

import copy
import numpy as np


def exact_time_union(scan):
    changed=copy.copy(scan)
    changed.times=np.unique(np.concatenate([np.asarray(scan.times)]+[np.asarray(t['times']) for t in scan.tracks]))
    changed.index=[np.searchsorted(changed.times,np.asarray(t['times'])) for t in scan.tracks]
    for t,ix in zip(scan.tracks,changed.index,strict=True):
        if not np.array_equal(changed.times[ix],t['times']):raise ValueError('native track time missing from exact prediction grid')
    return changed
