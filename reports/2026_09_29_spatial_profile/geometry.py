"""Observed local information and timing-profile geometry; not calibrated error."""

import numpy as np


def information(gradient, x, steps):
    x, steps = np.asarray(x, float), np.asarray(steps, float)
    if x.ndim != 1 or steps.shape != x.shape or np.any(steps <= 0):
        raise ValueError("Require positive coordinate steps")
    columns = []
    for axis, step in enumerate(steps):
        delta = np.eye(len(x))[axis] * step
        columns.append(-(gradient(x + delta) - gradient(x - delta)) / (2 * step))
    raw = np.column_stack(columns)
    symmetric = (raw + raw.T) / 2
    return raw, symmetric


def profile(matrix):
    matrix = np.asarray(matrix, float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or len(matrix) < 3:
        raise ValueError("Require two position and at least one timing coordinate")
    nuisance = matrix[2:, 2:]
    if np.linalg.eigvalsh(nuisance).min() <= 0:
        raise ValueError("Timing block is not positive definite")
    response = -np.linalg.solve(nuisance, matrix[2:, :2])
    spatial = matrix[:2, :2] + matrix[:2, 2:] @ response
    spatial = (spatial + spatial.T) / 2
    values, vectors = np.linalg.eigh(spatial)
    # Deterministic sign for reporting and +/- displacement construction.
    for j in range(2):
        if vectors[np.argmax(abs(vectors[:, j])), j] < 0:
            vectors[:, j] *= -1
    return spatial, response, values, vectors


def relative_difference(a, b):
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), 1e-15))
