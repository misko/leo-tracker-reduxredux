"""Whiten and remove per-curve affine and shared receiver smooth terms."""

from dataclasses import dataclass

import numpy as np


def remove_columns(values, columns):
    return values - columns @ (columns.T @ values)


@dataclass(frozen=True)
class CurveRows:
    times: np.ndarray
    values: np.ndarray
    inverse_sigma: np.ndarray
    smooth: np.ndarray
    rf_ratio: float


class ReceiverProjector:
    def __init__(self, curves):
        self.curves = tuple(curves)
        self.affine, residual_design = [], []
        for curve in self.curves:
            t, w = curve.times, curve.inverse_sigma
            if len(t) < 3 or np.any(t[1:] <= t[:-1]) or not np.all(np.isfinite(w) & (w > 0)):
                raise ValueError("Projection requires signed curves with three distinct epochs and positive scale")
            level = w/np.linalg.norm(w)
            slope = w*(t-t[0])
            slope -= level*(level @ slope)
            columns = np.column_stack((level, slope/np.linalg.norm(slope)))
            self.affine.append(columns)
            residual_design.append(remove_columns(curve.rf_ratio*w[:, None]*curve.smooth, columns))
        design = np.concatenate(residual_design)
        left, singular, _ = np.linalg.svd(design, full_matrices=False)
        tolerance = singular[0]*max(design.shape)*np.finfo(float).eps
        self.rank = int(np.count_nonzero(singular > tolerance))
        self.smooth = left[:, :self.rank]
        self.dimension = len(design)-2*len(curves)-self.rank

    def score(self, frequencies):
        residuals = [remove_columns((c.values-c.rf_ratio*f)*c.inverse_sigma, q)
                     for c, f, q in zip(self.curves, frequencies, self.affine, strict=True)]
        z = remove_columns(np.concatenate(residuals), self.smooth)
        return float(z @ z)


def rank_preference(scores):
    first, second = scores
    if not np.isfinite(scores).all():
        raise ValueError("Comparable finite fixed candidate scores required")
    return int(first > second) if first != second else None
