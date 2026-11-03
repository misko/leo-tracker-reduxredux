"""Reuse identical trajectory predictions without merging observation evidence."""

from dataclasses import dataclass

import numpy as np
from prediction_jacobian import paired_prediction_jacobian


@dataclass(frozen=True)
class ExpandedJacobian:
    base: object
    order: np.ndarray
    starts: np.ndarray
    row_count: int
    satellite_count: int

    def transpose_multiply(self, weights):
        weights = np.asarray(weights, dtype=float)
        if weights.shape != (self.row_count * self.satellite_count,):
            raise ValueError("weights must match expanded paired predictions")
        matrix = weights.reshape(self.row_count, self.satellite_count)
        collapsed = np.add.reduceat(matrix[self.order], self.starts, axis=0)
        return self.base.transpose_multiply(collapsed.ravel())

    def normal_matrix(self, weights):
        weights = np.asarray(weights, dtype=float)
        if weights.shape != (self.row_count * self.satellite_count,):
            raise ValueError("weights must match expanded paired predictions")
        if np.any(~np.isfinite(weights)) or np.any(weights < 0):
            raise ValueError("precision weights must be finite and nonnegative")
        matrix = weights.reshape(self.row_count, self.satellite_count)
        collapsed = np.add.reduceat(matrix[self.order], self.starts, axis=0)
        return self.base.normal_matrix(collapsed.ravel())


class SharedPredictionPlan:
    def __init__(self, data, satellites):
        self.data = data
        self.satellites = np.asarray(satellites, dtype=int).copy()
        if self.satellites.ndim != 1 or len(self.satellites) == 0:
            raise ValueError("satellites must be a nonempty vector")
        if len(np.unique(self.satellites)) != len(self.satellites):
            raise ValueError("satellites must be unique")
        keys = np.column_stack([data.times, data.rf, data.receiver])
        if len(keys) == 0 or np.any(~np.isfinite(keys)):
            raise ValueError("prediction features must be nonempty and finite")
        _, unique_rows, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
        self.inverse = inverse.reshape(-1)
        self.order = np.argsort(self.inverse, kind="stable")
        counts = np.bincount(self.inverse)
        self.starts = np.r_[0, np.cumsum(counts[:-1])]
        self.unique_rows = unique_rows
        self.rows = np.repeat(unique_rows, len(self.satellites))
        self.paired_satellites = np.tile(self.satellites, len(unique_rows))

    def predict(self, parameters):
        predicted, visible, base = paired_prediction_jacobian(
            self.data, parameters, self.rows, self.paired_satellites
        )
        count = len(self.satellites)
        expanded_prediction = predicted.reshape(-1, count)[self.inverse].ravel()
        expanded_visibility = visible.reshape(-1, count)[self.inverse].ravel()
        jacobian = ExpandedJacobian(base, self.order, self.starts, len(self.inverse), count)
        return expanded_prediction, expanded_visibility, jacobian
