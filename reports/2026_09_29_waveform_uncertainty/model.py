import numpy as np


def line_predict(times, values, targets, sigma=None):
    times, values, targets = [np.asarray(v, dtype=float) for v in (times, values, targets)]
    assert len(times) == len(values) and len(times) >= 2
    center = times.mean()
    design = np.column_stack((np.ones(len(times)), times - center))
    scale = np.ones(len(times)) if sigma is None else 1 / np.maximum(np.asarray(sigma), 25.0)
    beta, _, rank, _ = np.linalg.lstsq(design * scale[:, None], values * scale, rcond=None)
    assert rank == 2
    return beta[0] + beta[1] * (targets - center), float(beta[1])


def jackknife_sigma(estimates):
    values = np.asarray(estimates, dtype=float)
    assert len(values) == 8
    return float(np.sqrt(7 / 8 * np.sum((values - values.mean()) ** 2)))
