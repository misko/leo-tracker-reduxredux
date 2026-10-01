"""Small conditional robust regressions; no localization or reference inputs."""
import numpy as np


def basis(times, receivers, contrasts, rf_scale, center, scale):
    if not np.isfinite(scale) or scale <= 0: raise ValueError('Positive common time scale required')
    u = (np.asarray(times)-center)/scale
    rx = np.asarray(receivers)
    return np.column_stack([contrasts @ ((u**power)*(rx == receiver))*rf_scale
                            for power in (1, 2) for receiver in (0, 1)])


def folds(records):
    for group in sorted({r['group'] for r in records}):
        yield group, [r for r in records if r['group'] != group], [r for r in records if r['group'] == group]


def loss(records, beta, columns):
    total = 0.
    for row in records:
        residual = row['y']-row['X'][:, columns]@beta
        total += .5*(4+len(residual))*np.log1p(float(residual@residual)/4)
    return float(total)


def fit(records, columns, max_iterations=64):
    columns = list(columns); beta = np.zeros(len(columns)); history = []
    if not records:
        return dict(converged=False, reason='empty_training', beta=beta.tolist(), iterations=0, history=history)
    design = np.vstack([r['X'][:, columns] for r in records])
    singular = np.linalg.svd(design, compute_uv=False)
    if len(singular) < len(columns) or singular[-1] <= 1e-10*singular[0]:
        return dict(converged=False, reason='rank_deficient', beta=beta.tolist(), iterations=0, history=history)
    history.append(loss(records, beta, columns))
    for iteration in range(max_iterations+1):
        metric = np.zeros((len(beta), len(beta))); gradient = np.zeros(len(beta))
        for row in records:
            X = row['X'][:, columns]; residual = row['y']-X@beta
            weight = (4+len(residual))/(4+float(residual@residual))
            metric += weight*X.T@X; gradient -= weight*X.T@residual
        step = np.linalg.solve(metric, gradient)
        decrement = float(gradient@step)
        if decrement < 1e-8:
            return dict(converged=True, reason='stationary', beta=beta.tolist(), iterations=iteration,
                        decrement_squared=decrement, history=history)
        if iteration == max_iterations: break
        new_beta = beta-step; value = loss(records, new_beta, columns)
        if not np.isfinite(value) or value > history[-1]+1e-8:
            return dict(converged=False, reason='nonmonotone', beta=beta.tolist(), iterations=iteration, history=history)
        beta = new_beta; history.append(value)
    return dict(converged=False, reason='iteration_limit', beta=beta.tolist(), iterations=max_iterations,
                decrement_squared=decrement, history=history)
