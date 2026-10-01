"""Frozen-quadratic group deletion and nuisance profiling."""
import numpy as np


def deletion(metric, gradient, group_metric, group_gradient):
    remaining = metric-group_metric
    try:
        np.linalg.cholesky(remaining)
        delta = -np.linalg.solve(remaining, gradient-group_gradient)
    except np.linalg.LinAlgError:
        return dict(valid=False, reason='remaining_metric_not_positive_definite')
    L = np.linalg.cholesky(metric)
    whitened = np.linalg.solve(L, group_metric)
    whitened = np.linalg.solve(L, whitened.T).T
    leverage = float(np.linalg.eigvalsh((whitened+whitened.T)/2)[-1])
    return dict(valid=True, delta=delta.tolist(), horizontal_step_m=float(np.linalg.norm(delta[:2])*1000),
                maximum_leverage=leverage)


def profile(metric):
    position = metric[:2, :2]
    cross = metric[:2, 2:]
    schur = position-cross@np.linalg.solve(metric[2:, 2:], cross.T)
    schur = (schur+schur.T)/2
    np.linalg.cholesky(schur)
    return schur
