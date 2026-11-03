"""Window layout for timing errors shared only within a satellite/TLE snapshot.

Receiver clocks and drifts remain scan-specific. Each shared epoch gets one
Gaussian prior, rather than one copy per observation or per scan.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SharedEpochLayout:
    columns: tuple[np.ndarray, ...]
    precision: np.ndarray
    epoch_keys: tuple[tuple[str, int], ...]


def shared_epoch_layout(
    catalogues: Sequence[Sequence[int]], snapshot_ids: Sequence[str],
) -> SharedEpochLayout:
    """Map local scan states; catalogue ordering is never assumed identical."""
    if not catalogues or len(catalogues) != len(snapshot_ids):
        raise ValueError('one snapshot identity per nonempty scan is required')
    if any(not isinstance(s, str) or not s for s in snapshot_ids):
        raise ValueError('snapshot identities must be nonempty strings')
    for catalogue in catalogues:
        if (not len(catalogue) or len(set(catalogue)) != len(catalogue)
                or any(not isinstance(n, (int,np.integer)) or n <= 0 for n in catalogue)):
            raise ValueError('each catalogue needs distinct positive NORAD identifiers')
    # Sorting gives a stable epoch order even when scan or catalogue order changes.
    keys = tuple(sorted({(snapshot,int(n)) for catalogue,snapshot in zip(catalogues,snapshot_ids)
                         for n in catalogue}))
    epoch_start = 2+3*len(catalogues)
    index = {key:epoch_start+i for i,key in enumerate(keys)}
    precision = np.zeros(epoch_start+len(keys))
    columns=[]
    for i,(catalogue,snapshot) in enumerate(zip(catalogues,snapshot_ids)):
        start=2+3*i
        precision[start:start+3]=[1.,4.,4.]
        local=np.array([0,1,start,start+1,start+2,*[index[(snapshot,int(n))] for n in catalogue]])
        local.setflags(write=False)
        columns.append(local)
    precision[epoch_start:]=4.
    precision.setflags(write=False)
    return SharedEpochLayout(tuple(columns),precision,keys)
