"""Contrast prior groups with exact collapse of unobserved independent priors."""

import numpy as np


def prior_groups(width, phase_begin, phase_count, active_fragments, phase_nu):
    active = np.asarray(active_fragments, bool)
    if active.ndim != 1 or width < phase_begin+phase_count+len(active):
        raise ValueError('matching phase and fragment feature blocks required')
    groups = np.full(width, -1, int)
    if phase_nu is not None:
        groups[phase_begin:phase_begin+phase_count] = np.arange(phase_count)
    # An unobserved independent contrast integrates to one. Keeping it Gaussian
    # in the zero design column computes that collapse exactly instead of a
    # gratuitous Gaussian/Gamma mean-field gap for a wholly unobserved prior.
    indices = width-len(active)+np.flatnonzero(active)
    groups[indices] = phase_count+np.flatnonzero(active)
    return groups
