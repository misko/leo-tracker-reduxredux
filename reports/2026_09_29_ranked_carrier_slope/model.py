import numpy as np
from scipy.optimize import minimize

TS = 4.4e-6
TRAIN = np.arange(20, 220)
HELD = np.arange(220, 300)


def objective(parameters, y, offsets):
    """Profile carrier gains; parameters are frequency/1000 and slope/100."""
    times = TRAIN * TS
    basis = (
        2
        * np.pi
        * times[:, None, None]
        * np.stack((np.full(len(offsets), 1000.0), -100 * np.asarray(offsets)), axis=1)[None, :, :]
    )
    rotation = np.exp(-1j * np.einsum("nca,a->nc", basis, parameters))
    values = y[:, TRAIN] * rotation[None]
    gain = values.mean(axis=1)
    dg = (-1j * values[:, :, :, None] * basis[None]).mean(axis=1)
    energy = max(float(np.sum(np.mean(abs(y[:, TRAIN]) ** 2, axis=1))), 1e-30)
    loss = -float(np.sum(abs(gain) ** 2)) / energy
    gradient = -2 * np.real(np.sum(gain.conj()[:, :, None] * dg, axis=(0, 1))) / energy
    return loss, gradient


def fit(y, offsets, initial):
    bounds = [(-1.5, 1.5), (-1.0, 1.0)]
    starts = []
    for slope in (-0.5, 0.0, 0.5):
        result = minimize(
            objective,
            [initial / 1000, slope],
            args=(y, offsets),
            jac=True,
            method="L-BFGS-B",
            bounds=bounds,
            options=dict(maxiter=100, maxfun=160, ftol=1e-13, gtol=1e-8, maxls=25),
        )
        gradient = result.jac.copy()
        for i, (lo, hi) in enumerate(bounds):
            if (result.x[i] <= lo + 1e-8 and gradient[i] > 0) or (
                result.x[i] >= hi - 1e-8 and gradient[i] < 0
            ):
                gradient[i] = 0
        pg = float(np.max(abs(gradient)))
        starts.append(
            dict(
                parameters=(result.x * np.array([1000, 100])).tolist(),
                loss=float(result.fun),
                success=bool(result.success),
                message=str(result.message),
                projected_gradient=pg,
                qualified=bool(result.success and pg <= 1e-6),
            )
        )
    qualified = [s for s in starts if s["qualified"]]
    selected = min(qualified, key=lambda s: s["loss"]) if qualified else None
    return selected, starts


def errors(y, offsets, parameters):
    f, ppm = parameters
    frequency = f - np.asarray(offsets) * ppm
    train = np.exp(-2j * np.pi * TRAIN[:, None] * TS * frequency[None])
    gain = np.mean(y[:, TRAIN] * train[None], axis=1)
    prediction = gain[:, None, :] * np.exp(2j * np.pi * HELD[:, None] * TS * frequency[None])[None]
    return np.sum(abs(y[:, HELD] - prediction) ** 2, axis=(1, 2)) / np.maximum(
        np.sum(abs(y[:, HELD]) ** 2, axis=(1, 2)), 1e-30
    )
