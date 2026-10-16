"""Array-only native residual and calibration/timing design diagnostics.

These are descriptive frozen-state quantities, not observed Fisher information,
hardware measurements, confidence bounds, or an optimizer. Native visibility,
waveform weights and genuine continuity families retain the source likelihood.
"""

from dataclasses import dataclass

import numpy as np
from scipy.special import logsumexp

from leo.analysis.joint_association_graph import sparse_forward_backward
from leo.analysis.research.omitted_bank_score import _span


@dataclass(frozen=True)
class NativeHistoryResiduals:
    nll: float
    residual_hz: np.ndarray
    posterior: np.ndarray
    clutter_probability: np.ndarray
    log_prediction_weight: np.ndarray


def native_history_residuals(
    measured,
    prediction,
    visible,
    rows,
    slots,
    available,
    waveform_log_evidence,
    families,
    initial,
    *,
    sigma_hz,
    sample_rate_hz,
    signal_stay,
    clutter_stay,
):
    """Full native posterior, including branch histories and lost visibility mass."""
    measured, prediction = np.asarray(measured), np.asarray(prediction)
    rows, slots = np.asarray(rows), np.asarray(slots)
    visible, available = np.asarray(visible), np.asarray(available)
    waveform = np.asarray(waveform_log_evidence)
    if available.ndim != 2 or prediction.ndim != 2:
        raise ValueError("Native branch matrices required")
    n, b = available.shape
    m, k = prediction.shape
    if (
        available.dtype != bool
        or not available.any(axis=1).all()
        or measured.shape != (m,)
        or visible.shape != (m, k)
        or visible.dtype != bool
        or rows.shape != (m,)
        or slots.shape != (m,)
        or rows.dtype.kind not in "iu"
        or slots.dtype.kind not in "iu"
        or not np.array_equal(np.column_stack([rows, slots]), np.argwhere(available))
        or waveform.shape != (n, b)
        or not all(np.isfinite(x).all() for x in (measured, prediction, waveform))
        or np.asarray(initial).shape != (1 + k * b,)
        or not np.isfinite(sigma_hz)
        or sigma_hz <= 0
        or not np.isfinite(sample_rate_hz)
        or sample_rate_hz <= 0
    ):
        raise ValueError("Aligned finite native inventory required")
    residual = (measured[:, None] - prediction + sample_rate_hz / 2) % sample_rate_hz
    residual -= sample_rate_hz / 2
    phi = -0.5 * (residual / sigma_hz) ** 2 - np.log(sigma_hz * np.sqrt(2 * np.pi))
    phi += np.log(b / available.sum(axis=1))[rows, None]
    weights = np.where(available, waveform, -np.inf)
    weights -= logsumexp(weights, axis=1)[:, None]
    weights += np.log(available.sum(axis=1))[:, None]
    phi += weights[rows, slots, None]
    phi = np.where(visible, phi, -np.inf)
    dense = np.full((n, k, b), -np.inf)
    dense[rows, :, slots] = phi
    emissions = np.column_stack([np.full(n, -np.log(sample_rate_hz)), dense.reshape(n, k * b)])
    history = sparse_forward_backward(
        emissions,
        families,
        initial,
        signal_stay=signal_stay,
        clutter_stay=clutter_stay,
    )
    posterior = history.posterior[:, 1:].reshape(n, k, b)[rows, :, slots]
    return NativeHistoryResiduals(
        history.nll,
        residual,
        posterior,
        history.posterior[:, 0],
        posterior * residual / sigma_hz**2,
    )


def residual_groups(residual, posterior, rows, labels, clutter_probability):
    """Actual native alternatives remain latent; counts are not independent samples.

    Clutter has no native branch time: reported clutter is the unique intersecting
    original-window mass. Groups of branch times can overlap in those windows.
    """
    residual, posterior = np.asarray(residual), np.asarray(posterior)
    rows, labels, clutter = np.asarray(rows), np.asarray(labels), np.asarray(clutter_probability)
    if (
        residual.ndim != 2
        or posterior.shape != residual.shape
        or rows.shape != (len(residual),)
        or labels.shape != rows.shape
        or rows.dtype.kind not in "iu"
        or clutter.ndim != 1
        or np.any(rows < 0)
        or np.any(rows >= len(clutter))
        or not all(np.isfinite(x).all() for x in (residual, posterior, clutter))
        or np.any(posterior < 0)
        or np.any(clutter < 0)
        or np.any(clutter > 1)
    ):
        raise ValueError("Aligned residual, posterior and original windows required")
    result = []
    for label in np.unique(labels):
        mask = labels == label
        p, r = posterior[mask], residual[mask]
        mass = float(p.sum())
        mean = float(np.sum(p * r) / mass) if mass else None
        rms = float(np.sqrt(np.sum(p * r**2) / mass)) if mass else None
        windows = np.unique(rows[mask])
        result.append(
            dict(
                label=label.item() if hasattr(label, "item") else label,
                original_windows=int(len(windows)),
                native_candidates=int(mask.sum()),
                signal_mass=mass,
                intersecting_window_clutter_mass=float(clutter[windows].sum()),
                conditional_mean_hz=mean,
                conditional_rms_hz=rms,
                conditional_std_hz=float(np.sqrt(max(0, rms**2 - mean**2))) if mass else None,
            )
        )
    return result


def rf_scaling_audit(native, reference, rf_hz, reference_rf_hz):
    """Compare same-position/time/shifts orbit ports; calibration is excluded."""
    rf = np.asarray(rf_hz)
    if (
        len(native) != 4
        or len(reference) != 4
        or rf.shape != (len(native[0]),)
        or np.any(rf <= 0)
        or not np.isfinite(rf).all()
        or not np.isfinite(reference_rf_hz)
        or reference_rf_hz <= 0
    ):
        raise ValueError("Aligned positive recorded/reference RF required")
    result = dict(visibility_equal=bool(np.array_equal(native[1], reference[1])))
    for name, index in (("doppler", 0), ("spatial", 2), ("timing", 3)):
        actual, expected = np.asarray(native[index]), np.asarray(reference[index])
        if actual.shape != expected.shape or not np.isfinite(actual).all():
            raise ValueError("Aligned finite RF prediction derivatives required")
        scale = (rf / reference_rf_hz).reshape((-1,) + (1,) * (actual.ndim - 1))
        difference = actual - expected * scale
        result[name] = dict(
            maximum_abs=float(np.max(abs(difference))),
            rms=float(np.sqrt(np.mean(difference**2))),
            relative_max=float(np.max(abs(difference)) / max(1, np.max(abs(actual)))),
        )
    return result


def compact_latent_design(
    posterior,
    spatial,
    timing,
    calibration,
    timing_basis,
    *,
    sigma_hz,
    block_rows=2048,
    guard=lambda: None,
):
    """Joint QR preserves crossproducts; use original row count for all rank tests."""
    p, geo, time, cal, basis = map(
        np.asarray, (posterior, spatial, timing, calibration, timing_basis)
    )
    if (
        p.ndim != 2
        or geo.shape != (*p.shape, 2)
        or time.shape != p.shape
        or cal.ndim != 2
        or len(cal) != len(p)
        or basis.shape != (p.shape[1], p.shape[1] - 1)
        or not all(np.isfinite(x).all() for x in (p, geo, time, cal, basis))
        or np.any(p < 0)
        or np.any(p > 1)
        or not np.isfinite(sigma_hz)
        or sigma_hz <= 0
        or not isinstance(block_rows, int)
        or block_rows < 1
    ):
        raise ValueError("Aligned conditional latent design required")
    m, k = p.shape
    compact = np.empty((0, 2 + cal.shape[1] + k))
    for start in range(0, m * k, block_rows):
        guard()
        index = np.arange(start, min(start + block_rows, m * k))
        branch, sat = index // k, index % k
        shift = time[branch, sat]
        block = np.column_stack([geo[branch, sat], cal[branch], shift, shift[:, None] * basis[sat]])
        block *= (np.sqrt(p[branch, sat]) / sigma_hz)[:, None]
        compact = np.linalg.qr(np.vstack([compact, block]), mode="r")
    return compact, m * k, float(p.sum())


def profile_targets(compact, targets, nuisance, *, original_rows, target_scales):
    """Fixed-responsibility local design; scales declare physical target units.

    This unconstrained projection excludes priors and assignment uncertainty.
    Raw column norms accompany scaled Gram eigenvalues; no covariance inversion.
    """
    compact = np.asarray(compact, float)
    targets, nuisance = tuple(targets), tuple(nuisance)
    scales = np.asarray(target_scales, float)
    if (
        compact.ndim != 2
        or not np.isfinite(compact).all()
        or not targets
        or len(set(targets + nuisance)) != len(targets + nuisance)
        or any(not 0 <= i < compact.shape[1] for i in targets + nuisance)
        or scales.shape != (len(targets),)
        or np.any(scales <= 0)
        or not np.isfinite(scales).all()
    ):
        raise ValueError("Separate target/nuisance columns and positive physical scales required")
    target = compact[:, targets]
    span, audit = _span(compact[:, nuisance], rank_rows=original_rows)
    residual = target - span @ (span.T @ target)
    raw, projected = target.T @ target, residual.T @ residual
    scaled = projected * scales[:, None] * scales[None, :]
    singular = np.linalg.svd(residual * scales, compute_uv=False)
    values = np.sort(np.r_[singular**2, np.zeros(max(0, len(targets) - len(singular)))])
    # Reference the unprofiled target, avoiding rank inflation from cancellation.
    reference = float(np.linalg.norm(target * scales, ord=2))
    tolerance = max(original_rows, len(targets)) * np.finfo(float).eps * reference
    rank = int(np.sum(singular > tolerance))
    fractions = np.divide(
        np.diag(projected), np.diag(raw), out=np.zeros(len(targets)), where=np.diag(raw) > 0
    )
    return dict(
        targets=list(targets),
        nuisance=list(nuisance),
        target_scales=scales.tolist(),
        raw_gram=raw.tolist(),
        projected_gram=projected.tolist(),
        scaled_gram=scaled.tolist(),
        scaled_eigenvalues=values.tolist(),
        rank=rank,
        singular_rank_tolerance=float(tolerance),
        condition=float(values[-1] / values[0]) if rank == len(targets) and values[0] > 0 else None,
        retained_squared_norm_fraction=fractions.tolist(),
        nuisance_rank=audit.rank,
        nuisance_rank_tolerance=audit.rank_tolerance,
        nuisance_singular_values=audit.singular_values.tolist(),
        unsupported_nuisance_columns=list(audit.unsupported_columns),
    )
