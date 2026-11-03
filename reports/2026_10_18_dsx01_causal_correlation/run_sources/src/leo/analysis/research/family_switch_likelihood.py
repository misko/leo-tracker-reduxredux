"""Smooth bounded family evidence, including shared orbit-prior residuals."""

import numpy as np


def family_residuals(residual, blocks, effective_points, *, cap_per_point=4.0):
    """Normalize families to 50 effective points and optionally bound each cost.

    Both data and family-specific priors belong in a block. Shared receiver
    priors remain outside blocks. The bounded cost C*E/(C+E) is continuous and
    suppresses an inconsistent family's entire position influence; it does not
    merely make a large orbital adjustment inexpensive.
    """
    r = np.asarray(residual, float)
    if r.ndim != 1 or not np.isfinite(r).all():
        raise ValueError("finite one-dimensional residual required")
    if len(blocks) != len(effective_points) or (
        cap_per_point is not None and (not np.isfinite(cap_per_point) or cap_per_point <= 0)
    ):
        raise ValueError("matching families and positive finite cap required")
    result, used, diagnostics = r.copy(), set(), []
    for block, n in zip(blocks, effective_points, strict=True):
        ix = np.asarray(block, int)
        if n <= 0 or not np.isfinite(n) or np.any(ix < 0) or np.any(ix >= len(r)):
            raise ValueError("valid family indices and effective support required")
        if len(set(ix)) != len(ix) or used.intersection(ix):
            raise ValueError("family-specific residual blocks must be disjoint")
        used.update(ix)
        z = r[ix] * np.sqrt(50 / n)
        energy = float(z @ z)
        scale = 1.0 if cap_per_point is None else 50 * cap_per_point / (50 * cap_per_point + energy)
        result[ix] = np.sqrt(scale) * z
        diagnostics.append(
            dict(
                unbounded_energy=energy,
                energy=float(result[ix] @ result[ix]),
                influence_weight=scale**2,
            )
        )
    return result, diagnostics
