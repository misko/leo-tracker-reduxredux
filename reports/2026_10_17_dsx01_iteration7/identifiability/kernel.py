"""Positive, fixed-posterior Gaussian frequency information via small Grams."""

import numpy as np


def gram_blocks(spatial, timing, calibration, weight):
    s, t, c, w = map(np.asarray, (spatial, timing, calibration, weight))
    if (
        s.ndim != 3
        or s.shape[2] != 2
        or t.shape != s.shape[:2]
        or w.shape != t.shape
        or c.ndim != 2
        or c.shape[0] != len(s)
    ):
        raise ValueError("Expected spatial[n,k,2], timing/weight[n,k], calibration[n,d]")
    if any(not np.isfinite(a).all() for a in (s, t, c, w)) or np.any(w < 0):
        raise ValueError("Finite derivatives and nonnegative fixed weights required")
    rows = w.sum(axis=1)
    spatial_row = np.einsum("nk,nki->ni", w, s)
    spatial_gram = np.einsum("nk,nki,nkj->ij", w, s, s)
    calibration_gram = c.T @ (rows[:, None] * c)
    spatial_calibration = spatial_row.T @ c
    spatial_timing = np.einsum("nk,nki,nk->ik", w, s, t)
    calibration_timing = c.T @ (w * t)
    timing_diagonal = np.sum(w * t * t, axis=0)
    return dict(
        spatial=spatial_gram,
        calibration=calibration_gram,
        spatial_calibration=spatial_calibration,
        spatial_timing=spatial_timing,
        calibration_timing=calibration_timing,
        timing=np.diag(timing_diagonal),
        observations=len(s),
        candidates=s.shape[1],
        calibration_columns=c.shape[1],
    )


def total_timing_precision(count, relative_sigma=2.0, common_sigma=3.0):
    if count < 2 or relative_sigma <= 0 or common_sigma <= 0:
        raise ValueError("At least two candidates and positive timing widths required")
    ones = np.ones((count, count))
    return (np.eye(count) - ones / count) / relative_sigma**2 + ones / (count * common_sigma) ** 2


def schur(spatial, cross, nuisance, *, precision=None, rank_rtol=1e-12):
    """Scale every nuisance column to unit (data+prior) norm, preserving its span."""
    a, b, h = map(np.asarray, (spatial, cross, nuisance))
    if a.shape != (2, 2) or h.ndim != 2 or h.shape[0] != h.shape[1] or b.shape != (2, len(h)):
        raise ValueError("Incompatible information blocks")
    if precision is not None:
        p = np.asarray(precision)
        if p.shape != h.shape:
            raise ValueError("Prior precision must match nuisance layout")
        h = h + p
    diagonal = np.maximum(np.diag(h), 0.0)
    scale = np.ones(len(h))
    np.divide(1.0, np.sqrt(diagonal), out=scale, where=diagonal > 0)
    normalized = scale[:, None] * ((h + h.T) / 2) * scale[None, :]
    eigenvalues, eigenvectors = np.linalg.eigh(normalized)
    largest = max(float(eigenvalues.max(initial=0)), 1.0)
    if eigenvalues.min(initial=0) < -1e-10 * largest:
        raise ValueError("Nuisance Gram/prior is materially indefinite")
    use = eigenvalues > rank_rtol * largest
    projected_cross = (b * scale) @ eigenvectors[:, use]
    removed = (projected_cross / eigenvalues[use]) @ projected_cross.T
    retained = (a - removed + (a - removed).T) / 2
    return dict(
        information=retained,
        removed_information=removed,
        nuisance_rank=int(use.sum()),
        nuisance_columns=len(h),
        rank_rtol=rank_rtol,
        normalized_gram_eigenvalues=eigenvalues,
        original_column_norms=np.sqrt(diagonal),
        zero_norm_columns=np.flatnonzero(diagonal == 0),
        scale_policy="Each column unit data+prior norm; zero-norm columns retained as zero",
    )


def describe(information, raw):
    a, h = np.asarray(information), np.asarray(raw)
    values, vectors = np.linalg.eigh((a + a.T) / 2)
    raw_values, raw_vectors = np.linalg.eigh((h + h.T) / 2)
    tolerance = max(float(np.max(abs(raw_values))), 1.0) * 1e-8
    if values.min(initial=0) < -tolerance:
        raise ValueError("Materially negative retained spatial information")
    # Keep signed raw values visible; only square roots for dimensionless
    # whitening require a positive raw spatial subspace.
    positive = raw_values > max(float(raw_values.max(initial=0)), 1.0) * 1e-14
    inverse = raw_vectors[:, positive] / np.sqrt(raw_values[positive])
    fractions = np.linalg.eigvalsh(inverse.T @ a @ inverse)
    return dict(
        information_hz_gaussian_per_km2=a,
        eigenvalues_per_km2=values,
        eigenvectors_regional_east_north_columns=vectors,
        eigenvector_angles_deg_from_east=np.degrees(np.arctan2(vectors[1], vectors[0])),
        trace_fraction_of_raw=float(np.trace(a) / np.trace(h)) if np.trace(h) else None,
        generalized_fractions_of_raw=fractions,
        signed_eigenvalues_retained=True,
        small_negative_roundoff_tolerance=tolerance,
    )


def compare(blocks, clock_precision, *, calibration_columns=None):
    d, k = blocks["calibration_columns"], blocks["candidates"]
    if calibration_columns is None:
        calibration_columns = np.arange(d)
    ix = np.asarray(calibration_columns, dtype=int)
    raw = blocks["spatial"]
    cc = blocks["calibration"][np.ix_(ix, ix)]
    sc = blocks["spatial_calibration"][:, ix]
    ct = blocks["calibration_timing"][ix]
    nuisance = np.block([[cc, ct], [ct.T, blocks["timing"]]])
    cross = np.column_stack((sc, blocks["spatial_timing"]))
    clock = np.asarray(clock_precision)[np.ix_(ix, ix)]
    prior = np.zeros_like(nuisance)
    prior[: len(ix), : len(ix)] = clock
    prior[len(ix) :, len(ix) :] = total_timing_precision(k)
    results = dict(raw=describe(raw, raw))
    for label, b, h, q in (
        ("after_calibration", sc, cc, None),
        ("after_calibration_and_timing", cross, nuisance, None),
        ("after_calibration_with_clock_prior", sc, cc, clock),
        ("after_calibration_and_timing_with_actual_priors", cross, nuisance, prior),
    ):
        projected = schur(raw, b, h, precision=q)
        results[label] = dict(describe(projected.pop("information"), raw), **projected)
        if q is None:
            results[label]["rank_sensitivity"] = {
                str(tol): describe(schur(raw, b, h, rank_rtol=tol)["information"], raw)
                for tol in (1e-10, 1e-14)
            }
    return results
