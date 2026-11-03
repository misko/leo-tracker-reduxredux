"""Delete-group jackknife-shaped sensitivity, without a coverage guarantee."""
import numpy as np


def deletion_spread(displacements):
    """Return (G-1)/G times the centered outer-product sum of 2D shifts.

    This is the conventional delete-one jackknife covariance formula applied
    to supplied deletion shifts. Approximate nonlinear fits, unequal satellite
    groups and inferred associations need not satisfy jackknife assumptions.
    The caller must not present the result as calibrated uncertainty merely
    because the algebra is valid.
    """
    shifts = np.asarray(displacements, dtype=float)
    if shifts.ndim != 2 or shifts.shape[1] != 2 or shifts.shape[0] < 2:
        raise ValueError('at least two two-dimensional deletion shifts required')
    if not np.all(np.isfinite(shifts)):
        raise ValueError('deletion shifts must be finite')
    centered = shifts-shifts.mean(axis=0)
    result = (len(shifts)-1)/len(shifts)*(centered.T@centered)
    return .5*(result+result.T)
