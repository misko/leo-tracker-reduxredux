"""Stationary-receiver Doppler geometry without a point/satellite vector cube."""
import numpy as np


def stationary_range_rate_grid(
    positions: np.ndarray,
    velocities: np.ndarray,
    receivers: np.ndarray,
    receiver_up: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return range rate and sine elevation on a point/satellite/time grid.

    Satellite arrays have shape (satellites, times, 3), receiver arrays
    (points, 3); outputs have shape (points, satellites, times). All vectors
    are in the same Cartesian frame; receivers are stationary in that frame.
    Up vectors must be unit length. Units of output rate follow input velocity.
    Equivalent dot products replace large explicit line-of-sight vector arrays.
    Very short ranges relative to coordinate magnitudes can lose precision;
    nonpositive computed squared ranges are rejected rather than clipped.
    """
    p, v, r, up = (np.asarray(x, dtype=float) for x in
                   (positions, velocities, receivers, receiver_up))
    if (p.ndim != 3 or p.shape[-1] != 3 or v.shape != p.shape
            or r.ndim != 2 or r.shape[-1] != 3 or up.shape != r.shape
            or any(not np.all(np.isfinite(x)) for x in (p, v, r, up))):
        raise ValueError("invalid Cartesian geometry arrays")
    if not np.allclose(np.linalg.norm(up, axis=1), 1., rtol=1e-12, atol=1e-12):
        raise ValueError("receiver up vectors must be normalized")
    squared_range = (np.einsum('stc,stc->st', p, p)[None]
                     + np.einsum('pc,pc->p', r, r)[:, None, None]
                     - 2*np.einsum('stc,pc->pst', p, r))
    if np.any(squared_range <= 0):
        raise ValueError("nonpositive squared range")
    distance = np.sqrt(squared_range)
    rate = (np.einsum('stc,stc->st', p, v)[None]
            - np.einsum('stc,pc->pst', v, r))/distance
    sine_elevation = (np.einsum('stc,pc->pst', p, up)
                      - np.einsum('pc,pc->p', r, up)[:, None, None])/distance
    return rate, np.clip(sine_elevation, -1., 1.)
