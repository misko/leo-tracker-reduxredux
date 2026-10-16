"""Conditional omitted-component scores and fixed-responsibility design audits.

Array-only research ports: no input loading, optimization, prior intervention,
covariance inversion, or confidence/coverage claim. The caller supplies unchanged
native visibility/branch mass and only free nuisance columns (exclude locked c).
Visibility and sampling-alias regions remain fixed. Active bounds are reported;
the projections remain unconstrained linear diagnostics.
"""

from dataclasses import dataclass

import numpy as np


def _readonly(value):
    result = np.array(value, dtype=float, copy=True)
    result.setflags(write=False)
    return result


def _matrix(value, name, *, rows=None, columns=None):
    result = np.asarray(value, dtype=float)
    if (
        result.ndim != 2
        or not np.isfinite(result).all()
        or (rows is not None and result.shape[0] != rows)
        or (columns is not None and result.shape[1] != columns)
    ):
        raise ValueError(f"Finite aligned {name} matrix required")
    return result


def _bounds(indices, width):
    result = tuple(indices)
    if len(set(result)) != len(result) or any(
        isinstance(i, (bool, np.bool_))
        or not isinstance(i, (int, np.integer))
        or not 0 <= i < width
        for i in result
    ):
        raise ValueError("Unique active-bound column indices required")
    return tuple(sorted(map(int, result)))


@dataclass(frozen=True)
class ColumnSpaceAudit:
    rank: int
    rank_tolerance: float
    singular_values: np.ndarray
    supported_columns: tuple[int, ...]
    unsupported_columns: tuple[int, ...]
    null_dimension: int
    active_bound_columns: tuple[int, ...]


def _span(design, active_bounds=(), *, rank_rows=None):
    """Stable unit-column normalization; exact-zero support, standard SVD rank."""
    n, p = design.shape
    if rank_rows is not None and (not isinstance(rank_rows, int) or rank_rows < n):
        raise ValueError("Rank row count must retain the original design inventory")
    active = _bounds(active_bounds, p)
    maximum = np.max(abs(design), axis=0) if n else np.zeros(p)
    supported = np.flatnonzero(maximum > 0)
    unsupported = np.flatnonzero(maximum == 0)
    if len(supported):
        # Max-abs scaling avoids overflowing/underflowing a finite column norm.
        scaled = design[:, supported] / maximum[supported]
        normalized = scaled / np.linalg.norm(scaled, axis=0)
        u, singular, _ = np.linalg.svd(normalized, full_matrices=False)
        tolerance = (
            max(n if rank_rows is None else rank_rows, p) * np.finfo(float).eps * singular[0]
        )
        rank = int(np.sum(singular > tolerance))
        basis = u[:, :rank]
    else:
        singular, tolerance, rank = np.empty(0), 0.0, 0
        basis = np.empty((n, 0))
    return basis, ColumnSpaceAudit(
        rank,
        float(tolerance),
        _readonly(singular),
        tuple(map(int, supported)),
        tuple(map(int, unsupported)),
        p - rank,
        active,
    )


def omitted_component_scores(
    current_signal_density, omitted_signal_density, *, signal_mass, clutter_density
):
    """Window log-likelihood derivative q(fd-F)/(c+qF), not an NLL derivative.

    Densities already include raw native visibility and within-cell weights;
    this port never renormalizes them. One row is one original observation.
    An omitted component's physical/timing convention is fixed by the caller.
    """
    current = np.asarray(current_signal_density, dtype=float)
    if current.ndim != 1 or not len(current) or not np.isfinite(current).all():
        raise ValueError("One finite current signal density per original window required")
    omitted = _matrix(omitted_signal_density, "omitted density", rows=len(current))
    if (
        np.any(current < 0)
        or np.any(omitted < 0)
        or not np.isfinite(signal_mass)
        or not 0 <= signal_mass <= 1
        or not np.isfinite(clutter_density)
        or clutter_density <= 0
    ):
        raise ValueError("Nonnegative densities, fixed signal mass and positive clutter required")
    difference = omitted - current[:, None]
    if signal_mass == 0:
        return _readonly(np.zeros_like(difference))
    with np.errstate(over="ignore", under="ignore", divide="ignore", invalid="ignore"):
        signal_density = signal_mass * current
        density = clutter_density + signal_density
        numerator = signal_mass * difference
        score = numerator / density[:, None]
        tiny = np.finfo(float).tiny
        # A representable ratio can have an unrepresentable intermediate
        # product. Keep ordinary arithmetic, but route unsafe cells through
        # signed log arithmetic before a tiny product loses its mass.
        unsafe_density = (
            ~np.isfinite(density) | (density < tiny) | ((current > 0) & (signal_density < tiny))
        )
        unsafe = unsafe_density[:, None] | (
            (difference != 0) & ((abs(numerator) < tiny) | ~np.isfinite(score))
        )
        if np.any(unsafe):
            log_density = np.logaddexp(
                np.log(clutter_density), np.log(signal_mass) + np.log(current)
            )
            log_score = np.log(signal_mass) + np.log(abs(difference)) - log_density[:, None]
            stable = np.sign(difference) * np.exp(log_score)
            score = np.where(unsafe, stable, score)
    if not np.isfinite(score).all() or np.any((difference != 0) & (score == 0)):
        raise ValueError("Replacement score exceeds finite float64 arithmetic")
    return _readonly(score)


@dataclass(frozen=True)
class OmittedScoreProjection:
    raw_scores: np.ndarray
    projected_scores: np.ndarray
    raw_sum: np.ndarray
    projected_sum: np.ndarray
    projected_norm_fraction: tuple[float | None, ...]
    all_parameter_space: ColumnSpaceAudit
    warnings: tuple[str, ...]


def project_omitted_scores(
    scores,
    geographic_scores,
    nuisance_scores,
    *,
    active_geographic_bounds=(),
    active_nuisance_bounds=(),
):
    """Project original-window scores against geography AND free nuisance.

    These are log-likelihood score columns, not prediction Jacobians. The
    residual is descriptive; no calibrated significance or feasible refit is
    inferred. A zero score has an undefined norm fraction, returned as None.
    """
    scores = _matrix(scores, "replacement score")
    n = len(scores)
    if not n:
        raise ValueError("At least one original window required")
    geo = _matrix(geographic_scores, "geographic score", rows=n, columns=2)
    nuisance = _matrix(nuisance_scores, "free nuisance score", rows=n)
    active_geo = _bounds(active_geographic_bounds, 2)
    active_nuisance = _bounds(active_nuisance_bounds, nuisance.shape[1])
    design = np.column_stack([geo, nuisance])
    basis, audit = _span(design, active_geo + tuple(i + 2 for i in active_nuisance))
    maximum = np.max(abs(scores), axis=0)
    scaled = np.divide(scores, maximum, out=np.zeros_like(scores), where=maximum > 0)
    residual = scaled - basis @ (basis.T @ scaled)
    projected = residual * maximum
    raw_sum, projected_sum = scores.sum(axis=0), projected.sum(axis=0)
    if not all(np.isfinite(x).all() for x in (projected, raw_sum, projected_sum)):
        raise ValueError("Projected score exceeds finite float64 arithmetic")
    fractions = tuple(
        float(np.linalg.norm(residual[:, i]) / np.linalg.norm(scaled[:, i]))
        if maximum[i] > 0
        else None
        for i in range(scores.shape[1])
    )
    warnings = (
        ("Active bounds: projection is unconstrained, not a feasible refit.",)
        if (audit.active_bound_columns)
        else ()
    )
    return OmittedScoreProjection(
        _readonly(scores),
        _readonly(projected),
        _readonly(raw_sum),
        _readonly(projected_sum),
        fractions,
        audit,
        warnings,
    )


@dataclass(frozen=True)
class GeographicGramAudit:
    gram: np.ndarray
    eigenvalues: np.ndarray
    total_signal_mass: float
    no_signal: bool
    rank: int
    rank_tolerance: float
    condition_number: float | None
    nuisance_space: ColumnSpaceAudit
    active_geographic_bounds: tuple[int, ...]
    warnings: tuple[str, ...]


def profile_geographic_gram(
    geographic_jacobian,
    nuisance_jacobian,
    posterior_mass,
    *,
    sigma_hz,
    active_geographic_bounds=(),
    active_nuisance_bounds=(),
    rank_rows=None,
):
    """Nuisance-only Schur design, with frozen latent responsibilities p/sigma².

    Latent rows are expected complete-data curvature bookkeeping, not additional
    observations. This is not observed mixture Fisher information or a confidence
    bound. Rank alone cannot establish usable information: raw magnitudes and
    total signal mass are always returned, with no near-zero availability cutoff.
    """
    geo = _matrix(geographic_jacobian, "geographic Jacobian", columns=2)
    nuisance = _matrix(nuisance_jacobian, "free nuisance Jacobian", rows=len(geo))
    posterior = np.asarray(posterior_mass, dtype=float)
    if (
        posterior.shape != (len(geo),)
        or not np.isfinite(posterior).all()
        or np.any(posterior < 0)
        or np.any(posterior > 1)
        or not np.isfinite(sigma_hz)
        or sigma_hz <= 0
    ):
        raise ValueError("Aligned posterior probabilities and positive finite sigma required")
    active_geo = _bounds(active_geographic_bounds, 2)
    weights = np.sqrt(posterior) / sigma_hz
    weighted_geo = _matrix(geo * weights[:, None], "weighted geographic Jacobian")
    weighted_nuisance = _matrix(nuisance * weights[:, None], "weighted nuisance Jacobian")
    basis, nuisance_audit = _span(weighted_nuisance, active_nuisance_bounds, rank_rows=rank_rows)
    profiled = weighted_geo - basis @ (basis.T @ weighted_geo)
    singular = np.linalg.svd(profiled, compute_uv=False)
    reference = np.linalg.svd(weighted_geo, compute_uv=False)
    # Anchor tolerance to original geography so projection roundoff cannot
    # manufacture information when geography lies exactly in nuisance span.
    tolerance = (
        max(len(geo) if rank_rows is None else rank_rows, nuisance.shape[1] + 2)
        * np.finfo(float).eps
        * (reference[0] if len(reference) else 0)
    )
    rank = int(np.sum(singular > tolerance))
    gram = profiled.T @ profiled
    eigenvalues = np.sort(np.r_[singular**2, np.zeros(2 - len(singular))])
    if not np.isfinite(gram).all() or not np.isfinite(eigenvalues).all():
        raise ValueError("Geographic Gram exceeds finite float64 arithmetic")
    condition = float((singular[0] / singular[1]) ** 2) if rank == 2 else None
    total = float(posterior.sum())
    warnings = ["Fixed-responsibility local design; excludes reassociation and visibility changes."]
    if total == 0:
        warnings.append("Exactly zero signal mass; no conditional geographic information.")
    if active_geo or nuisance_audit.active_bound_columns:
        warnings.append("Active bounds: projection is unconstrained, not a feasible refit.")
    if np.any(singular > 0) and np.max(eigenvalues, initial=0) == 0:
        warnings.append(
            "Raw Gram magnitudes underflowed; numerical rank is not usable information."
        )
    return GeographicGramAudit(
        _readonly(gram),
        _readonly(eigenvalues),
        total,
        total == 0,
        rank,
        float(tolerance),
        condition,
        nuisance_audit,
        active_geo,
        tuple(warnings),
    )
