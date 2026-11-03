import numpy as np
from scipy.optimize import minimize, minimize_scalar

TS = 4.4e-6
TRAIN = np.arange(20, 220)
HELD = np.arange(220, 300)


def objective(parameters, values, mhz, coarse):
    t = (TRAIN - TRAIN.mean()) * TS
    f = coarse + parameters[:-1]
    drift = parameters[-1]
    z = values[:, TRAIN] * np.exp(
        -2j * np.pi * t[None, :, None] * (f[:, None, None] - mhz[None, None, :] * drift)
    )
    gain = z.mean(axis=1)
    energy = np.maximum(np.mean(np.sum(abs(values[:, TRAIN]) ** 2, axis=2), axis=1), 1e-30)
    power = np.sum(abs(gain) ** 2, axis=1) / energy
    df = np.mean(z * (-2j * np.pi * t)[None, :, None], axis=1)
    dd = np.mean(z * (2j * np.pi * t)[None, :, None] * mhz[None, None, :], axis=1)
    grad_f = -2 * np.real(np.sum(gain.conj() * df, axis=1)) / energy / len(values)
    grad_d = -2 * np.mean(np.real(np.sum(gain.conj() * dd, axis=1)) / energy)
    return -float(power.mean()), np.r_[grad_f, grad_d]


def learn(values, mhz, coarse):
    fit = minimize(
        lambda p: objective(p, values, mhz, coarse),
        np.zeros(len(values) + 1),
        jac=True,
        method="L-BFGS-B",
        bounds=[(-1500.0, 1500.0)] * len(values) + [(-300.0, 300.0)],
        options=dict(maxiter=400, ftol=1e-13, gtol=1e-8, maxls=30),
    )
    boundary = bool(np.any(abs(fit.x[:-1]) > 1499) or abs(fit.x[-1]) > 299)
    pg = float(max(abs(fit.jac)))
    return dict(
        drift_ppm=float(fit.x[-1]),
        frequency_corrections_hz=fit.x[:-1].tolist(),
        success=bool(fit.success),
        boundary=boundary,
        max_gradient=pg,
        qualified=bool(fit.success and not boundary and pg < 1e-5),
        objective=float(fit.fun),
        message=str(fit.message),
    )


def prediction(values, mhz, coarse, drift):
    def gain(f):
        rotation = np.exp(2j * np.pi * (TRAIN * TS)[:, None] * (f - mhz[None, :] * drift))
        return np.mean(values[TRAIN] * rotation.conj(), axis=0)

    result = minimize_scalar(
        lambda f: -float(np.sum(abs(gain(f)) ** 2)),
        bounds=(coarse - 1500, coarse + 1500),
        method="bounded",
    )
    if not result.success:
        raise RuntimeError("Frequency fit failed")
    f = float(result.x)
    expected = gain(f) * np.exp(2j * np.pi * (HELD * TS)[:, None] * (f - mhz[None, :] * drift))
    nmse = float(
        np.sum(abs(values[HELD] - expected) ** 2) / max(np.sum(abs(values[HELD]) ** 2), 1e-30)
    )
    return dict(frequency_hz=f, nmse=nmse)
