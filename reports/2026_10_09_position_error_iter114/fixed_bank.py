"""Research-only streamed fixed-bank score; no fitting or recording inputs."""

import numpy as np

from leo.analysis.regional_position_score import ALIAS_HZ, circular, zero_sum_basis


def streamed_score(measured_hz, batches, *, candidate_count, score, penalty):
    """Consume ordered (prediction, visibility) column batches exactly once.

    candidate_count is the fixed denominator. Fewer supplied columns intentionally
    means normalization-only scoring, equivalent to invisible missing columns.
    Caller retains the original penalty; this function never reconstructs it.
    """
    measured = np.asarray(measured_hz, float)
    if measured.ndim != 1 or not np.isfinite(measured).all():
        raise ValueError("finite one-dimensional observations required")
    if (
        isinstance(candidate_count, bool)
        or not isinstance(candidate_count, (int, np.integer))
        or candidate_count <= score.detection_budget
        or score.sigma_hz > 1000
        or not np.isfinite(penalty)
        or penalty < 0
    ):
        raise ValueError("invalid count, narrow score, or preserved penalty")
    q = score.detection_budget / candidate_count
    normalization = q / (1 - q) / (score.sigma_hz * np.sqrt(2 * np.pi))
    signal = np.zeros(len(measured))
    visible_count = np.zeros(len(measured), dtype=np.int64)
    supplied = 0
    for prediction, visible in batches:
        prediction, visible = np.asarray(prediction, float), np.asarray(visible)
        if (
            prediction.ndim != 2
            or prediction.shape[0] != len(measured)
            or visible.shape != prediction.shape
            or visible.dtype != bool
            or not np.isfinite(prediction).all()
        ):
            raise ValueError("invalid prediction/visibility batch")
        supplied += prediction.shape[1]
        if supplied > candidate_count:
            raise ValueError("more supplied columns than fixed candidate count")
        residual = circular(measured[:, None] - prediction)
        density = np.exp(-0.5 * (residual / score.sigma_hz) ** 2) * visible
        # Multiplication before summation matches production's per-column formula.
        signal += (density * normalization).sum(axis=1)
        visible_count += visible.sum(axis=1)
    log_p0 = -score.clutter_rate + visible_count * np.log1p(-q)
    log_density = (
        log_p0 - np.log(-np.expm1(log_p0)) + np.log(score.clutter_rate / ALIAS_HZ + signal)
    )
    nll = float(-log_density.sum())
    return {
        "data_nll": nll,
        "penalty": float(penalty),
        "objective": nll + penalty,
        "supplied_columns": supplied,
        "candidate_count": int(candidate_count),
        "visible_count": visible_count,
    }


def transport_timing(old_ids, new_ids, common_s, relative_s, *, tolerance=1e-10):
    """Embed zero-sum physical shifts without modifying the common shift.

    Raise on an infeasible old state or non-superset bank; never recenter/clip.
    Production common bound is +/-10 s and total per-satellite bound +/-20 s.
    """
    old, new = np.asarray(old_ids), np.asarray(new_ids)
    relative = np.asarray(relative_s, float)
    if (
        old.ndim != 1
        or new.ndim != 1
        or len(old) < 2
        or len(np.unique(old)) != len(old)
        or len(np.unique(new)) != len(new)
        or not set(old).issubset(set(new))
        or relative.shape != old.shape
        or not np.isfinite(relative).all()
        or not np.isfinite(common_s)
        or not np.isfinite(tolerance)
        or tolerance <= 0
    ):
        raise ValueError("invalid timing inventory/state")
    if abs(common_s) > 10 + tolerance or np.max(abs(common_s + relative)) > 20 + tolerance:
        raise ValueError("timing state outside physical constraints")
    if abs(relative.sum()) > tolerance:
        raise ValueError("relative shifts are not zero-sum; refusing recentering")
    indices = {identifier: i for i, identifier in enumerate(new)}
    transported = np.zeros(len(new))
    for identifier, shift in zip(old, relative, strict=True):
        transported[indices[identifier]] = shift
    basis = zero_sum_basis(len(new))
    coefficients = basis.T @ transported
    reconstructed = basis @ coefficients
    if np.max(abs(reconstructed - transported), initial=0) > tolerance:
        raise ValueError("basis cannot preserve physical timing shifts")
    return {
        "common_s": float(common_s),
        "relative_s": transported,
        "relative_coefficients": coefficients,
        "physical_shifts_s": common_s + transported,
        "maximum_basis_error_s": float(np.max(abs(reconstructed - transported), initial=0)),
    }
