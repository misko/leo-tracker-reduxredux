"""Exact Gaussian-prior minimization for explicitly unused epoch coordinates."""
import numpy as np


def profile_unused_epochs(state, assignments, candidate_count, *, precision=4.):
    """Return a copy and prior reduction; caller must verify likelihood independence.

    State has five shared coordinates followed by one epoch per satellite.
    Assignment ``candidate_count`` is clutter. Shared satellite epochs remain
    active until their last track is removed. No observation model is assumed.
    """
    state = np.asarray(state, dtype=float)
    assignments = np.asarray(assignments)
    if (candidate_count < 1 or state.shape != (5+candidate_count,)
            or not np.all(np.isfinite(state)) or assignments.ndim != 1
            or not np.issubdtype(assignments.dtype, np.integer)
            or np.any(assignments < 0) or np.any(assignments > candidate_count)
            or not np.isfinite(precision) or precision <= 0):
        raise ValueError('invalid epoch profile inputs')
    unused = np.ones(candidate_count, dtype=bool)
    unused[assignments[assignments < candidate_count]] = False
    out = state.copy()
    gain = float(.5*precision*np.sum(out[5:][unused]**2))
    out[5:][unused] = 0.
    return out, gain
