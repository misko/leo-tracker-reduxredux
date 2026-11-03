"""Finite-difference observed curvature; never substitute positive IRLS curvature."""
import numpy as np


def gradient_jacobian(gradient, point, steps):
    """Differentiate a supplied gradient, retaining asymmetry for caller auditing."""
    point, steps = np.asarray(point, dtype=float), np.asarray(steps, dtype=float)
    if (point.ndim != 1 or steps.shape != point.shape or not point.size
            or np.any(~np.isfinite(point)) or np.any(~np.isfinite(steps)) or np.any(steps <= 0)):
        raise ValueError('finite vector and matching positive steps required')
    result = np.empty((point.size, point.size))
    for column, step in enumerate(steps):
        offset = np.zeros_like(point)
        offset[column] = step
        left = np.asarray(gradient(point-offset), dtype=float)
        right = np.asarray(gradient(point+offset), dtype=float)
        if (left.shape != point.shape or right.shape != point.shape
                or np.any(~np.isfinite(left)) or np.any(~np.isfinite(right))):
            raise ValueError('gradient shape or values invalid')
        result[:, column] = (right-left)/(2*step)
    return result
