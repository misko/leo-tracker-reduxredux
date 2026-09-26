"""Small, report-local models for synchronized multi-mode phase observations.

The decomposition is deliberately conditional.  A polynomial present in every
mode can be moved between ``common`` and every mode trajectory.  We fix that
gauge by requiring the mode-specific coefficient mean to be zero; the returned
nullity records how many coefficients were unidentifiable before that choice.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class JointFit:
    modes: tuple[str, ...]
    origin_s: float
    scale_s: float
    common: np.ndarray
    deviations: np.ndarray
    rank: int
    unconstrained_nullity: int
    rms_rad: float

    def predict(self, mode: str, time_s: np.ndarray) -> np.ndarray:
        index = self.modes.index(mode)
        x = (np.asarray(time_s) - self.origin_s) / self.scale_s
        return np.polynomial.polynomial.polyval(x, self.common + self.deviations[index])


def unwrap_contiguous(
    time_s: np.ndarray, phase_rad: np.ndarray, *, max_gap_s: float
) -> tuple[np.ndarray, np.ndarray]:
    """Unwrap each contiguous finite segment, never selecting cycles across a gap."""
    time_s = np.asarray(time_s, dtype=float)
    phase_rad = np.asarray(phase_rad, dtype=float)
    if time_s.shape != phase_rad.shape:
        raise ValueError("time and phase shapes differ")
    out = np.full_like(phase_rad, np.nan)
    segment = np.full(phase_rad.shape, -1, dtype=int)
    previous = None
    sid = -1
    for i in range(len(time_s)):
        if not (np.isfinite(time_s[i]) and np.isfinite(phase_rad[i])):
            previous = None
            continue
        if previous is None or time_s[i] - time_s[previous] > max_gap_s:
            sid += 1
        segment[i] = sid
        previous = i
        indices = np.flatnonzero(segment == sid)
        out[indices] = np.unwrap(phase_rad[indices])
    return out, segment


def fit_joint_gauge(
    mode: np.ndarray,
    time_s: np.ndarray,
    phase_rad: np.ndarray,
    *,
    degree: int = 2,
    weight: np.ndarray | None = None,
) -> JointFit:
    """Fit common + mode polynomials under the zero-mean deviation gauge."""
    mode = np.asarray(mode).astype(str)
    time_s = np.asarray(time_s, dtype=float)
    phase_rad = np.asarray(phase_rad, dtype=float)
    if not (mode.shape == time_s.shape == phase_rad.shape):
        raise ValueError("observation shapes differ")
    modes = tuple(sorted(set(mode.tolist())))
    if len(modes) < 2:
        raise ValueError("joint fit requires at least two modes")
    origin = float(np.mean(time_s))
    scale = float(np.ptp(time_s) / 2)
    if not scale:
        raise ValueError("joint fit requires time extent")
    x = (time_s - origin) / scale
    basis = np.polynomial.polynomial.polyvander(x, degree)
    # Last deviation is minus the sum of the explicitly represented ones.
    blocks = [basis]
    for represented in modes[:-1]:
        sign = (mode == represented).astype(float) - (mode == modes[-1]).astype(float)
        blocks.append(basis * sign[:, None])
    design = np.column_stack(blocks)
    w = np.ones_like(time_s) if weight is None else np.sqrt(np.asarray(weight, dtype=float))
    finite = np.isfinite(phase_rad) & np.isfinite(w) & (w > 0)
    coef, _, rank, _ = np.linalg.lstsq(
        design[finite] * w[finite, None], phase_rad[finite] * w[finite], rcond=None
    )
    width = degree + 1
    common = coef[:width]
    deviations = np.zeros((len(modes), width))
    for i in range(len(modes) - 1):
        deviations[i] = coef[width * (i + 1) : width * (i + 2)]
    deviations[-1] = -np.sum(deviations[:-1], axis=0)
    residual = phase_rad[finite] - design[finite] @ coef
    return JointFit(
        modes=modes,
        origin_s=origin,
        scale_s=scale,
        common=common,
        deviations=deviations,
        rank=int(rank),
        unconstrained_nullity=width,
        rms_rad=float(np.sqrt(np.average(residual**2, weights=w[finite] ** 2))),
    )


def synchronized_increments(
    time_s: np.ndarray, phase_rad: np.ndarray, segment: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return midpoint times and within-segment increments; gaps are unsupported."""
    time_s = np.asarray(time_s, dtype=float)
    phase_rad = np.asarray(phase_rad, dtype=float)
    segment = np.asarray(segment)
    ok = (
        (segment[1:] >= 0)
        & (segment[1:] == segment[:-1])
        & np.isfinite(phase_rad[1:])
        & np.isfinite(phase_rad[:-1])
    )
    return (time_s[1:] + time_s[:-1])[ok] / 2, np.diff(phase_rad)[ok]


def increment_transfer_score(reference: np.ndarray, target: np.ndarray) -> dict[str, float]:
    """Score held increments without fitting a held-mode phase offset."""
    reference = np.asarray(reference, dtype=float)
    target = np.asarray(target, dtype=float)
    finite = np.isfinite(reference) & np.isfinite(target)
    if np.count_nonzero(finite) < 2:
        raise ValueError("at least two paired increments are required")
    ref, dst = reference[finite], target[finite]
    error = dst - ref
    denom = float(np.sum((dst - np.mean(dst)) ** 2))
    return {
        "n": int(len(ref)),
        "correlation": float(np.corrcoef(ref, dst)[0, 1]),
        "rmse_rad": float(np.sqrt(np.mean(error**2))),
        "skill_vs_constant": float(1 - np.sum(error**2) / denom) if denom else float("nan"),
    }


def calibrated_donor_prediction(
    time_s: np.ndarray,
    donor_phase: np.ndarray,
    target_phase: np.ndarray,
    train: np.ndarray,
    *,
    difference_degree: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Calibrate wrapped target-minus-donor on training and freeze it.

    Prediction still requires the donor phase at the prediction time.  It is a
    simultaneous common-component correction, not a forecast of future phase.
    """
    time_s = np.asarray(time_s, dtype=float)
    donor_phase = np.asarray(donor_phase, dtype=float)
    target_phase = np.asarray(target_phase, dtype=float)
    train = np.asarray(train, dtype=bool)
    if np.count_nonzero(train) <= difference_degree:
        raise ValueError("insufficient training samples for phase-difference model")
    origin = float(np.mean(time_s[train]))
    scale = float(np.ptp(time_s[train]))
    if not scale:
        raise ValueError("training times have no extent")
    x = (time_s - origin) / scale
    # Only the training difference selects cycle branches. Independent absolute
    # unwrapping of donor and target would create an arbitrary inter-mode cycle.
    wrapped_difference = np.angle(np.exp(1j * (target_phase - donor_phase)))
    training_difference = np.unwrap(wrapped_difference[train])
    coefficients = np.polynomial.polynomial.polyfit(
        x[train], training_difference, difference_degree
    )
    prediction = np.angle(
        np.exp(1j * (donor_phase + np.polynomial.polynomial.polyval(x, coefficients)))
    )
    return prediction, coefficients
