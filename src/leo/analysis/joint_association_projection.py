"""Training-only projection of physical proposal corrections into lean Model C."""

import numpy as np
from scipy.optimize import lsq_linear


def project_native_joint_seed(model, position_km, orbital_shifts_s, target_correction_hz):
    """Project correction values at exact native candidate receive times.

    Each original window has unit total weight across its native candidates.
    Receiver means are removed before fitting bounded drift/RF/group terms, so
    receiver sampling-gauge shifts cannot leak into those physical coefficients.
    Common-clock functions are approximated honestly; their residual is retained.
    No clock-nuisance coefficient vector is copied between model layouts.
    """
    base = model.base
    obs = base.native_observations
    target = np.asarray(target_correction_hz, float)
    point = np.asarray(position_km, float)
    shifts = np.asarray(orbital_shifts_s, float)
    if (
        target.shape != obs.times_s.shape
        or point.shape != (2,)
        or shifts.shape != (len(model.bank.numbers),)
        or not np.isfinite(target).all()
        or not np.isfinite(point).all()
        or not np.isfinite(shifts).all()
        or np.linalg.norm(point) > model.prior.radius_km + 1e-9
        or abs(shifts).max() > 20 + 1e-9
        or abs(shifts.mean()) > 10 + 1e-9
        or model.clock_count
        or model.group_count != model.offset_count
    ):
        raise ValueError("finite physical proposal and lean native Model C layout required")
    rows = base.native_rows
    available = base.branches.available.sum(axis=1)
    weight = 1 / available[rows]
    target = target - base.baseline[rows]
    groups = model.group_design[rows]
    # Keep only slope/RF/group columns until the per-receiver mean is restored.
    columns = np.column_stack([base.native_design[:, [1, 3, 4]], groups])
    centered = columns.copy()
    response = target.copy()
    means = {}
    for receiver in (0, 1):
        mask = obs.receiver == receiver
        if not mask.any():
            means[receiver] = (np.zeros(columns.shape[1]), 0.0)
            continue
        column_mean = np.average(columns[mask], axis=0, weights=weight[mask])
        target_mean = float(np.average(target[mask], weights=weight[mask]))
        centered[mask] -= column_mean
        response[mask] -= target_mean
        means[receiver] = column_mean, target_mean
    scales = np.r_[2.0, 2.0, 200.0, model.group_scales]
    limits = np.r_[60.0, 60.0, 5000.0, model.group_limits]
    root_weight = np.sqrt(weight)
    fit = lsq_linear(
        centered * (root_weight[:, None] * scales),
        response * root_weight,
        bounds=(-limits / scales, limits / scales),
        lsq_solver="exact",
        tol=1e-11,
        max_iter=200,
    )
    if not fit.success:
        raise ValueError("Bounded physical proposal projection did not converge")
    coefficients = fit.x * scales
    vector = np.zeros(model.size)
    vector[:2] = point
    vector[[3, 5, 6]] = coefficients[:3]
    for receiver, (column_mean, target_mean) in means.items():
        vector[2 + 2 * receiver] = target_mean - column_mean @ coefficients
    vector[7] = shifts.mean()
    vector[8:] = model.basis.T @ (shifts - shifts.mean())
    nuisance = coefficients[3:]
    predicted = base.native_design @ vector[2:7] + groups @ nuisance
    residual = target - predicted
    return dict(
        vector=vector,
        nuisance=nuisance,
        projection=dict(
            native_candidates=len(target),
            original_windows=len(available),
            rms_hz=float(np.sqrt(np.average(residual**2, weights=weight))),
            maximum_abs_hz=float(abs(residual).max()),
            active_bounds=np.flatnonzero(fit.active_mask).tolist(),
            receiver_mean_residual_hz={
                str(receiver): float(
                    np.average(
                        residual[obs.receiver == receiver], weights=weight[obs.receiver == receiver]
                    )
                )
                for receiver in (0, 1)
                if (obs.receiver == receiver).any()
            },
            weighting="Each original native window has unit total candidate weight",
            common_clock_transport="Physical function projection; no nuisance coefficient copy",
            native_time_center_s=model.observations.time_center_s,
            native_rf_center_hz=model.observations.rf_center_hz,
        ),
    )


def matched_joint_arm_seeds(seed):
    """Make independent identical seeds before the optimizer's exact c=0 lock."""
    return {
        arm: dict(
            vector=np.array(seed["vector"], copy=True),
            nuisance=np.array(seed["nuisance"], copy=True),
        )
        for arm in ("fitted-c", "zero-c")
    }
