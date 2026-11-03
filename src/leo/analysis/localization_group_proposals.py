"""Whole-group identity proposals with one shared epoch prior per satellite."""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class GroupIdentityProposal:
    source: int
    target: int
    epoch_index: int
    track_indices: tuple[int, ...]
    conditional_gain: float


def rank_group_proposals(scores, epoch_grid, assignments, current_scores, current_epochs,
                         *, epoch_precision=4., limit=3):
    """Rank unused-target replacements; scores contain signal branches only.

    ``scores`` has axes epoch, track, satellite. Each proposal is independent,
    at fixed position/clock/drift. Background changes and all-track refitting are
    the caller's responsibility; these conditional gains are not full scores.
    """
    scores = np.asarray(scores, dtype=float)
    epochs = np.asarray(epoch_grid, dtype=float)
    assigned = np.asarray(assignments)
    current = np.asarray(current_scores, dtype=float)
    offsets = np.asarray(current_epochs, dtype=float)
    if scores.ndim != 3:
        raise ValueError('scores must have epoch, track and satellite axes')
    count_t, count_n, count_s = scores.shape
    if (not count_t or not count_n or not count_s or epochs.shape != (count_t,)
            or assigned.shape != (count_n,) or current.shape != (count_n,)
            or offsets.shape != (count_s,) or assigned.dtype.kind not in 'iu'
            or np.any(assigned < 0) or np.any(assigned > count_s)
            or np.any(~np.isfinite(epochs)) or np.any(~np.isfinite(current))
            or np.any(~np.isfinite(offsets)) or np.any(np.isnan(scores))
            or np.any(np.isposinf(scores)) or not np.isfinite(epoch_precision)
            or epoch_precision <= 0 or not isinstance(limit, int) or limit < 1):
        raise ValueError('invalid proposal arrays or settings')
    used = sorted(set(assigned[assigned < count_s].tolist()))
    unused = sorted(set(range(count_s))-set(used))
    proposals = []
    for source in used:
        tracks = np.flatnonzero(assigned == source)
        grouped = scores[:, tracks, :].sum(axis=1)
        gains = (grouped-.5*epoch_precision*epochs[:, None]**2
                 +.5*epoch_precision*offsets[None, :]**2-current[tracks].sum()
                 +.5*epoch_precision*offsets[source]**2)
        for target in unused:
            best = int(np.argmax(gains[:, target]))
            gain = float(gains[best, target])
            if np.isfinite(gain):
                proposals.append(GroupIdentityProposal(source, target, best,
                                                        tuple(map(int, tracks)), gain))
    return sorted(proposals, key=lambda p: (-p.conditional_gain, p.source, p.target))[:limit]
