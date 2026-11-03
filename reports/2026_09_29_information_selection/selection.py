import numpy as np


def profile(matrix):
    assert matrix.shape == (3, 3) and np.isfinite(matrix).all()
    result = matrix[:2, :2].copy()
    if matrix[2, 2] > 0:
        result -= np.outer(matrix[:2, 2], matrix[2, :2]) / matrix[2, 2]
    result = (result + result.T) / 2
    assert np.linalg.eigvalsh(result).min() >= -1e-8
    return result


def greedy(matrices, count):
    matrices = np.asarray(matrices)
    assert matrices.ndim == 3 and matrices.shape[1:] == (2, 2)
    assert 0 < count <= len(matrices) and np.isfinite(matrices).all()
    ridge = float(np.trace(matrices.sum(axis=0)) / 2 * 1e-9)
    assert ridge > 0
    total = np.eye(2) * ridge
    selected, scores = [], []
    for _ in range(count):
        candidates = []
        for i, matrix in enumerate(matrices):
            if i not in selected:
                sign, value = np.linalg.slogdet(total + matrix)
                assert sign > 0
                candidates.append((float(value), -i))
        value, negative_index = max(candidates)
        index = -negative_index
        selected.append(index)
        scores.append(value)
        total += matrices[index]
    return dict(indices=selected, log_determinants=scores, ridge=ridge)
