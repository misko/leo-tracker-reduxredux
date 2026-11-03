"""Source/RF clock prediction across a held temporal gap."""
import numpy as np
from scipy.optimize import least_squares


def wrap(x, period):
    return (np.asarray(x)+period/2) % period-period/2


def fit(times, phases, training, period):
    t, y, original = np.asarray(times, float), np.asarray(phases, float), np.asarray(training, bool)
    if t.ndim != 1 or y.shape != t.shape or original.shape != t.shape:
        raise ValueError('mismatched arrays')
    if not np.isfinite(t).all() or not np.isfinite(y).all() or not np.isfinite(period) or period <= 0:
        raise ValueError('nonfinite data or invalid period')
    if not original.any():
        return dict(eligible=False, qualified=False, reason='no_training')
    boundary = float(t[original].min()+2*np.ptp(t[original])/3)
    train = original & (t <= boundary)
    held = ~original & (t > boundary)
    if train.sum() < 6 or held.sum() < 3 or len(np.unique(t[train])) < 3:
        return dict(eligible=False, qualified=False, reason='insufficient_support')
    center, scale = float(t[train].mean()), float(np.ptp(t[train]))
    u = (t-center)/scale
    design = np.column_stack((np.ones(len(t)), u, u*u))
    order = np.argsort(t[train], kind='stable')
    x = design[train][order]
    target = np.unwrap(y[train][order], period=period)
    initial = np.linalg.lstsq(x, target, rcond=None)[0]
    result = least_squares(lambda b:x@b-target, initial, jac=lambda b:x,
                           loss='soft_l1', f_scale=.1, max_nfev=300,
                           ftol=1e-12, xtol=1e-12, gtol=1e-10)
    error = wrap(y[held]-design[held]@result.x, period)
    return dict(eligible=True, qualified=bool(result.success and result.optimality < 1e-4),
                coefficients=result.x.tolist(), center_s=center, scale_s=scale,
                boundary_s=boundary, training_points=int(train.sum()), held_points=int(held.sum()),
                optimality=float(result.optimality), evaluations=int(result.nfev),
                held_errors_us=error.tolist(),
                gap_s=(t[held]-t[train].max()).tolist())
