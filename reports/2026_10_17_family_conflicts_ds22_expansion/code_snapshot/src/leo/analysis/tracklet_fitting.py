"""Common numerical output validation for independent tracklet discoveries.

Discovery belongs to each algorithm. This module generates no proposals: it
arbitrates duplicate ownership, compresses supports into penalized polynomials,
and reports the same conditional residual diagnostics for every algorithm.
"""

import numpy as np

from leo.analysis.polynomial_tracklets import (
    _diagnose,
    _penalty,
    _predict,
    _refine,
    _repair_structured,
    _wrap,
)


def prepare_lane(time_s, cfo_hz):
    times, values = np.asarray(time_s, float), np.asarray(cfo_hz, float)
    if times.ndim != 1 or times.shape != values.shape:
        raise ValueError("time_s and cfo_hz must be matching one-dimensional arrays")
    valid = np.flatnonzero(np.isfinite(times) & np.isfinite(values))
    order = valid[np.lexsort((values[valid], times[valid]))]
    return times[order], values[order], order, len(times)


def finish_lane(t, y, order, n_original, models, cfg, method, diagnostics=None):
    """Emit baseline-compatible results from polynomial supports on sorted inputs.

    A proposed observation belongs to at most one model. Conflicts go to the
    smaller circular residual. Every retained support is compressed and checked
    under the common noise, complexity, degree, span, gap, and slope constraints.
    No new observations are added to an algorithm's proposed memberships.
    """
    owner, best = np.full(len(t), -1, int), np.full(len(t), np.inf)
    gate = cfg.association_sigma * cfg.noise_sigma_hz
    for number, model in enumerate(models):
        ix = np.unique(np.asarray(model["indices"], int))
        if np.any((ix < 0) | (ix >= len(t))):
            raise ValueError("Model indices must reference sorted finite observations")
        distance = np.abs(_wrap(y[ix] - _predict(model, t[ix]), cfg.alias_spacing_hz))
        take = (distance < gate) & (distance < best[ix])
        owner[ix[take]], best[ix[take]] = number, distance[take]
    refined = []
    for number, model in enumerate(models):
        ix = np.flatnonzero(owner == number)
        chunks = np.split(ix, np.flatnonzero(np.diff(t[ix]) > cfg.max_gap_s) + 1)
        for chunk in chunks:
            if len(chunk) < cfg.min_points:
                continue
            piece = _refine(t, y, chunk, _predict(model, t[chunk]), cfg, grow=False)
            if piece is None:
                continue
            # A bounded iterative fit can end with a point just outside its gate.
            # Clip against the final coefficients and preserve those coefficients.
            rr = _wrap(
                y[piece["indices"]] - _predict(piece, t[piece["indices"]]), cfg.alias_spacing_hz
            )
            piece["indices"] = piece["indices"][np.abs(rr) < gate]
            if len(piece["indices"]) < max(
                cfg.min_points, cfg.points_per_coefficient * (piece["degree"] + 1)
            ):
                continue
            support = piece["indices"]
            if np.ptp(t[support]) < cfg.min_span_s:
                continue
            if np.max(np.diff(t[support])) > cfg.max_gap_s:
                continue
            residual = _wrap(y[support] - _predict(piece, t[support]), cfg.alias_spacing_hz)
            gain = np.sum(cfg.association_sigma**2 - (residual / cfg.noise_sigma_hz) ** 2)
            if gain > _penalty(piece, cfg):
                refined.append(piece)
    grouped = _repair_structured(refined, t, y, cfg) if refined else []
    assignment, lifts = np.full(n_original, -1, int), np.zeros(n_original, int)
    tracks = []
    for pieces in grouped:
        indices = np.concatenate([p["indices"] for p in pieces])
        if np.any(assignment[order[indices]] >= 0):
            raise ValueError("Duplicate ownership after final compression")
        first = pieces[0]
        gauge = np.floor(
            (_predict(first, np.array([t[first["indices"][0]]]))[0] + cfg.alias_spacing_hz / 2)
            / cfg.alias_spacing_hz
        )
        piece_diagnostics, residuals = [], []
        for piece in pieces:
            piece["coefficients_hz"] = np.asarray(piece["coefficients_hz"], float).copy()
            piece["coefficients_hz"][0] -= gauge * cfg.alias_spacing_hz
            ix = piece["indices"]
            predicted = _predict(piece, t[ix])
            lifts[order[ix]] = np.rint((predicted - y[ix]) / cfg.alias_spacing_hz).astype(int)
            residuals.extend(_wrap(y[ix] - predicted, cfg.alias_spacing_hz).tolist())
            piece_diagnostics.append(_diagnose(piece, t, y, cfg))
        flags = sorted({f for d in piece_diagnostics for f in d["quality_flags"]})
        status = (
            "structure_flagged"
            if flags
            else (
                "insufficient_support"
                if any(d["quality_status"] == "insufficient_support" for d in piece_diagnostics)
                else "no_structure_detected"
            )
        )
        assignment[order[indices]] = len(tracks)
        for piece in pieces:
            piece["indices"] = order[piece["indices"]]
        tracks.append(
            {
                "indices": order[indices],
                "pieces": pieces,
                "start_s": float(t[indices].min()),
                "end_s": float(t[indices].max()),
                "residual_rms_hz": float(np.sqrt(np.mean(np.square(residuals)))),
                "diagnostics": {
                    "pieces": piece_diagnostics,
                    "quality_flags": flags,
                    "quality_status": status,
                },
            }
        )
    return {
        "tracks": tracks,
        "assignment": assignment,
        "alias_lifts": lifts,
        "diagnostics": {
            "method": method,
            "nonfinite_points": n_original - len(t),
            "common_finalization": "membership arbitration, polynomial compression, "
            "fixed gate and support constraints; no proposal discovery",
            **(diagnostics or {}),
        },
    }
