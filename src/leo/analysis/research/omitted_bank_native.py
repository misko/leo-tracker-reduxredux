"""Array-only native singleton handoff; no loading, optimization or held scoring.

The source scorer's padded emission/initial-prior arithmetic supplies the full
latent posterior. Score columns use log-likelihood gain, without prior terms.
Joint orthogonal compression bounds latent-design memory while retaining the
original row count, signal mass, column norms and nuisance-only projection.
"""

from dataclasses import dataclass, replace

import numpy as np

from leo.analysis.joint_association_graph import sparse_forward_backward
from leo.analysis.research.omitted_bank_score import profile_geographic_gram


@dataclass(frozen=True)
class NativeSingletonTerms:
    nll: float
    current_signal_density: np.ndarray
    posterior: np.ndarray
    log_prediction_weight: np.ndarray
    signal_mass: float
    clutter_density: float


def singleton_native_terms(
    measured,
    prediction,
    visible,
    rows,
    slots,
    log_emission_prior,
    initial,
    *,
    sigma_hz,
    sample_rate_hz,
):
    """Exact singleton source posterior, packed only at actual native branches."""
    measured, prediction = np.asarray(measured), np.asarray(prediction)
    visible, rows, slots = np.asarray(visible), np.asarray(rows), np.asarray(slots)
    correction, initial = np.asarray(log_emission_prior), np.asarray(initial)
    n, b = correction.shape
    m, k = prediction.shape
    if (
        measured.shape != (m,)
        or visible.shape != (m, k)
        or visible.dtype != bool
        or rows.shape != (m,)
        or slots.shape != (m,)
        or rows.dtype.kind not in "iu"
        or slots.dtype.kind not in "iu"
        or np.any(rows < 0)
        or np.any(rows >= n)
        or np.any(slots < 0)
        or np.any(slots >= b)
        or len(set(zip(rows, slots, strict=True))) != m
        or set(rows) != set(range(n))
        or initial.shape != (1 + k * b,)
        or not np.isfinite(prediction).all()
        or not np.isfinite(measured).all()
        or not np.isfinite(correction).all()
        or not np.isfinite(sigma_hz)
        or sigma_hz <= 0
        or not np.isfinite(sample_rate_hz)
        or sample_rate_hz <= 0
    ):
        raise ValueError("Aligned actual native singleton inventory required")
    residual = (measured[:, None] - prediction + sample_rate_hz / 2) % sample_rate_hz
    residual -= sample_rate_hz / 2
    phi = -0.5 * (residual / sigma_hz) ** 2 - np.log(sigma_hz * np.sqrt(2 * np.pi))
    phi += correction[rows, slots, None]
    phi = np.where(visible, phi, -np.inf)
    dense = np.full((n, k, b), -np.inf)
    dense[rows, :, slots] = phi
    emissions = np.column_stack([np.full(n, -np.log(sample_rate_hz)), dense.reshape(n, k * b)])
    source = sparse_forward_backward(emissions, tuple((i,) for i in range(n)), initial)
    posterior = source.posterior[:, 1:].reshape(n, k, b)[rows, :, slots]
    q = float(1 - initial[0])
    # Initial padded-slot mass and its emission correction are unchanged.
    native_mass = initial[1:].reshape(k, b)[:, slots].T
    signal = np.zeros(n)
    np.add.at(signal, rows, (np.exp(phi) * native_mass).sum(axis=1))
    return NativeSingletonTerms(
        source.nll,
        signal / q,
        posterior,
        posterior * residual / sigma_hz**2,
        q,
        float(initial[0] / sample_rate_hz),
    )


def omitted_native_density(
    measured, prediction, visible, rows, native_cell_prior, *, windows, sigma_hz, sample_rate_hz
):
    """Raw lost-visible mass retained; no omitted-bank-count renormalization."""
    measured, prediction = np.asarray(measured), np.asarray(prediction)
    visible, rows, prior = np.asarray(visible), np.asarray(rows), np.asarray(native_cell_prior)
    if (
        prediction.ndim != 2
        or measured.shape != (len(prediction),)
        or visible.shape != prediction.shape
        or visible.dtype != bool
        or rows.shape != measured.shape
        or prior.shape != measured.shape
        or np.any(prior < 0)
        or not np.isfinite(prior).all()
        or rows.dtype.kind not in "iu"
        or np.any(rows < 0)
        or np.any(rows >= windows)
        or not np.isfinite(prediction).all()
        or not np.isfinite(measured).all()
        or not np.isfinite(sigma_hz)
        or sigma_hz <= 0
        or not np.isfinite(sample_rate_hz)
        or sample_rate_hz <= 0
    ):
        raise ValueError("Aligned finite omitted native inventory required")
    residual = (measured[:, None] - prediction + sample_rate_hz / 2) % sample_rate_hz
    residual -= sample_rate_hz / 2
    density = np.exp(-0.5 * (residual / sigma_hz) ** 2) / (sigma_hz * np.sqrt(2 * np.pi))
    density *= visible * prior[:, None]
    result = np.zeros((windows, prediction.shape[1]))
    np.add.at(result, rows, density)
    return result


def window_parameter_scores(
    rows, log_weight, spatial, timing, calibration_design, timing_basis, *, windows
):
    """Free-basis score matrix: geography, calibration, common, relative timing."""
    geo = np.zeros((windows, 2))
    cal = np.zeros((windows, calibration_design.shape[1]))
    sat = np.zeros((windows, timing.shape[1]))
    np.add.at(geo, rows, np.einsum("mk,mki->mi", log_weight, spatial))
    np.add.at(cal, rows, calibration_design * log_weight.sum(axis=1)[:, None])
    np.add.at(sat, rows, log_weight * timing)
    return geo, np.column_stack([cal, sat.sum(axis=1), sat @ timing_basis])


def compressed_native_gram(
    posterior,
    spatial,
    timing,
    calibration_design,
    timing_basis,
    *,
    sigma_hz,
    block_rows=2048,
    active_geographic_bounds=(),
    active_nuisance_bounds=(),
    guard=lambda: None,
):
    """Common QR of the ENTIRE weighted design; rank tolerances use original rows."""
    posterior, spatial, timing = map(np.asarray, (posterior, spatial, timing))
    design, basis = np.asarray(calibration_design), np.asarray(timing_basis)
    if (
        posterior.ndim != 2
        or spatial.shape != (*posterior.shape, 2)
        or timing.shape != posterior.shape
        or design.ndim != 2
        or len(design) != len(posterior)
        or basis.shape != (posterior.shape[1], posterior.shape[1] - 1)
        or not all(np.isfinite(x).all() for x in (posterior, spatial, timing, design, basis))
        or np.any(posterior < 0)
        or np.any(posterior > 1)
        or not isinstance(block_rows, int)
        or block_rows < 1
        or not np.isfinite(sigma_hz)
        or sigma_hz <= 0
    ):
        raise ValueError("Aligned native latent design and probabilities required")
    m, k = posterior.shape
    width = 2 + design.shape[1] + k
    compact = np.empty((0, width))
    for start in range(0, m * k, block_rows):
        guard()
        index = np.arange(start, min(start + block_rows, m * k))
        branch, sat = index // k, index % k
        shift = timing[branch, sat]
        block = np.column_stack(
            [
                spatial[branch, sat],
                design[branch],
                shift,
                shift[:, None] * basis[sat],
            ]
        )
        block *= (np.sqrt(posterior[branch, sat]) / sigma_hz)[:, None]
        # Preserve one orthogonal row transform across geography AND nuisance.
        compact = np.linalg.qr(np.vstack([compact, block]), mode="r")
    guard()
    audit = profile_geographic_gram(
        compact[:, :2],
        compact[:, 2:],
        np.ones(len(compact)),
        sigma_hz=1,
        active_geographic_bounds=active_geographic_bounds,
        active_nuisance_bounds=active_nuisance_bounds,
        rank_rows=m * k,
    )
    total = float(posterior.sum())
    warnings = tuple(w for w in audit.warnings if not w.startswith("Exactly zero"))
    if total == 0:
        warnings += ("Exactly zero signal mass; no conditional geographic information.",)
    return replace(audit, total_signal_mass=total, no_signal=total == 0, warnings=warnings)
