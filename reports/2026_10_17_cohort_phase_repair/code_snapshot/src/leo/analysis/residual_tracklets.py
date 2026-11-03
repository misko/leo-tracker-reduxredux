"""Bounded quadratic-seed discovery for points left by a tracklet fitter.

Sparse curved fragments can have no sufficiently large linear seed, even when
a low-order polynomial explains them well. This optional residual pass seeds
quadratics directly and retains the existing penalized degree selection and
final support/gap/alias checks. It neither alters nor imports saved results.
"""

from itertools import combinations

import numpy as np

from leo.analysis.polynomial_tracklets import (
    TrackConfig,
    _penalty,
    _predict,
    _refine,
    _select,
    _wrap,
)
from leo.analysis.tracklet_fitting import finish_lane, prepare_lane


def _triples(n, rng, budget=1024):
    if n * (n - 1) * (n - 2) // 6 <= budget:
        return np.asarray(list(combinations(range(n), 3)), int).reshape(-1, 3)
    candidates = np.sort(rng.integers(0, n, (3 * budget, 3)), axis=1)
    candidates = candidates[np.all(np.diff(candidates, axis=1) > 0, axis=1)]
    # Reproducible sampling without the temporal bias of truncating lexicographic triples.
    candidates = np.unique(candidates, axis=0)
    return candidates[rng.permutation(len(candidates))[:budget]]


def _proposals(t, y, cfg):
    rng = np.random.default_rng(cfg.random_seed)
    proposals, seen = [], set()
    tested, windows = 0, 0
    gate = cfg.noise_sigma_hz * cfg.association_sigma
    for width in (12.0, 24.0, 48.0):
        for start in np.arange(t[0] - width / 2, t[-1] + 0.001, width / 2):
            ix = np.flatnonzero((t >= start) & (t <= start + width))
            if len(ix) < cfg.min_points or np.ptp(t[ix]) < cfg.min_span_s:
                continue
            windows += 1
            triples = ix[_triples(len(ix), rng)]
            left, middle, right = triples.T
            da, db = t[middle] - t[left], t[right] - t[middle]
            keep = (da >= 1) & (db >= 1) & ((da + db) >= cfg.min_span_s)
            keep &= np.minimum(da, db) >= 0.15 * (da + db)
            left, middle, right = left[keep], middle[keep], right[keep]
            da, db = da[keep], db[keep]
            if not len(left):
                continue
            first_delta = _wrap(y[middle] - y[left], cfg.alias_spacing_hz)
            next_delta = _wrap(y[right] - y[middle], cfg.alias_spacing_hz)
            branches = int(np.ceil(cfg.max_slope_hz_s * width / cfg.alias_spacing_hz))
            candidates = []
            for a in range(-branches, branches + 1):
                va = (first_delta + a * cfg.alias_spacing_hz) / da
                for b in range(-branches, branches + 1):
                    vb = (next_delta + b * cfg.alias_spacing_hz) / db
                    acceleration = 2 * (vb - va) / (da + db)
                    velocity = va - 0.5 * acceleration * da
                    allowed = np.abs(va) <= cfg.max_slope_hz_s
                    allowed &= np.abs(vb) <= cfg.max_slope_hz_s
                    for endpoint in (t[ix[0]], t[ix[-1]]):
                        allowed &= np.abs(velocity + acceleration * (endpoint - t[left])) <= (
                            cfg.max_slope_hz_s
                        )
                    chosen = np.flatnonzero(allowed)
                    tested += len(chosen)
                    if not len(chosen):
                        continue
                    dt = t[ix][None, :] - t[left[chosen], None]
                    prediction = (
                        y[left[chosen], None]
                        + velocity[chosen, None] * dt
                        + 0.5 * acceleration[chosen, None] * dt**2
                    )
                    residual = _wrap(y[ix][None, :] - prediction, cfg.alias_spacing_hz)
                    support = np.abs(residual) < gate
                    gains = np.maximum(
                        cfg.association_sigma**2 - (residual / cfg.noise_sigma_hz) ** 2, 0
                    ).sum(axis=1)
                    gains[support.sum(axis=1) < cfg.min_points] = -np.inf
                    for k in np.argsort(-gains, kind="stable")[:8]:
                        if np.isfinite(gains[k]):
                            candidates.append(
                                (float(gains[k]), ix[support[k]], prediction[k, support[k]])
                            )
            for _, indices, prediction in sorted(candidates, key=lambda r: -r[0])[:12]:
                piece = _refine(t, y, indices, prediction, cfg)
                if piece is None:
                    continue
                key = tuple(piece["indices"])
                if key not in seen:
                    seen.add(key)
                    proposals.append(piece)

    def gain(piece):
        rr = _wrap(y[piece["indices"]] - _predict(piece, t[piece["indices"]]), cfg.alias_spacing_hz)
        return float(
            np.sum(cfg.association_sigma**2 - (rr / cfg.noise_sigma_hz) ** 2) - _penalty(piece, cfg)
        )

    proposals.sort(key=gain, reverse=True)
    return proposals[: cfg.max_proposals], {
        "seed_hypotheses": tested,
        "windows": windows,
        "proposals": len(proposals),
    }


def fit_lane(time_s, cfo_hz, config=None):
    """Fit only the supplied residual points; return indices in their input order."""
    cfg = config or TrackConfig()
    t, y, order, n = prepare_lane(time_s, cfo_hz)
    models, diagnostics = [], {"seed_hypotheses": 0, "windows": 0, "proposals": 0}
    if len(t) >= cfg.min_points and np.ptp(t) >= cfg.min_span_s:
        proposals, diagnostics = _proposals(t, y, cfg)
        models = _select(proposals, t, y, cfg)
    return finish_lane(t, y, order, n, models, cfg, "residual_quadratic_seeds", diagnostics)
