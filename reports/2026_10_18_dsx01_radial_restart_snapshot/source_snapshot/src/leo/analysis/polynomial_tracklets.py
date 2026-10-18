"""Bounded, alias-aware polynomial mixture fitting for exploratory tracklets.

This numerical component operates on one receiver/channel lane. It uses local
RANSAC proposals, a penalized joint assignment objective and optional C1 joins;
it is a deterministic local search, not a globally optimal tracker. Frequency
branches are identifiable only modulo ``alias_spacing_hz``. No orbital or
localization assumptions enter the fit.
"""

from dataclasses import dataclass

import numpy as np
from numpy.polynomial import legendre as leg


@dataclass(frozen=True)
class TrackConfig:
    alias_spacing_hz: float = 1 / 4.4e-6
    noise_sigma_hz: float = 150.0
    association_sigma: float = 3.0
    max_degree: int = 4
    min_points: int = 8
    points_per_coefficient: int = 4
    min_span_s: float = 6.0
    max_slope_hz_s: float = 4000.0
    max_gap_s: float = 10.0
    window_lengths_s: tuple = (24.0, 48.0, 96.0)
    seed_trials: int = 96
    max_proposals: int = 256
    max_tracks: int = 64
    track_penalty: float = 18.0
    breakpoint_penalty: float = 10.0
    max_join_gap_s: float = 8.0
    joint_iterations: int = 4
    random_seed: int = 1701

    def __post_init__(self):
        positive = (
            "alias_spacing_hz",
            "noise_sigma_hz",
            "association_sigma",
            "min_span_s",
            "max_slope_hz_s",
            "max_gap_s",
        )
        nonnegative = ("track_penalty", "breakpoint_penalty", "max_join_gap_s")
        for name in positive + nonnegative:
            value = getattr(self, name)
            if (
                not np.isscalar(value)
                or not np.isfinite(value)
                or value < 0
                or (name in positive and value == 0)
            ):
                raise ValueError(
                    f"{name} must be a finite "
                    f"{'positive' if name in positive else 'nonnegative'} scale"
                )
        for name, minimum in (
            ("min_points", 3),
            ("points_per_coefficient", 2),
            ("seed_trials", 1),
            ("max_proposals", 1),
            ("max_tracks", 1),
            ("joint_iterations", 1),
            ("random_seed", 0),
            ("max_degree", 0),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, np.integer))
                or value < minimum
            ):
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if self.max_degree > 4:
            raise ValueError("max_degree must lie between zero and four")
        if not self.window_lengths_s or any(
            not np.isfinite(w) or w <= 0 for w in self.window_lengths_s
        ):
            raise ValueError("window_lengths_s must contain finite positive widths")


def _wrap(value, period):
    return (value + period / 2) % period - period / 2


def _predict(piece, times):
    return leg.legval(
        (times - piece["reference_time_s"]) / piece["time_scale_s"], piece["coefficients_hz"]
    )


def _piece(t, y, indices, degree):
    ref = float((t[indices].min() + t[indices].max()) / 2)
    scale = max(float(np.ptp(t[indices])) / 2, 1.0)
    x = (t[indices] - ref) / scale
    coeff = leg.legfit(x, y, degree)
    return dict(
        indices=indices.copy(),
        degree=degree,
        reference_time_s=ref,
        time_scale_s=scale,
        coefficients_hz=coeff,
    )


def _supported(t, indices, degree, cfg):
    if len(indices) < max(cfg.min_points, cfg.points_per_coefficient * (degree + 1)):
        return False
    times = np.unique(t[indices])
    if len(times) < max(3, 2 * (degree + 1)) or np.ptp(times) < cfg.min_span_s:
        return False
    # Prevent a high-order fit supported only by two small endpoint clumps.
    return not (degree >= 2 and np.max(np.diff(times)) > 0.6 * np.ptp(times))


def _best_piece(t, y, indices, prediction, cfg):
    """Compare degrees on identical observations and a fixed noise scale."""
    lifted = prediction + _wrap(y[indices] - prediction, cfg.alias_spacing_hz)
    best, best_cost = None, float("inf")
    for degree in range(cfg.max_degree + 1):
        if not _supported(t, indices, degree, cfg):
            continue
        piece = _piece(t, lifted, indices, degree)
        residual = _wrap(y[indices] - _predict(piece, t[indices]), cfg.alias_spacing_hz)
        cost = float(
            np.sum((residual / cfg.noise_sigma_hz) ** 2)
            + (degree + 1) * np.log(max(len(indices), 2))
        )
        # A physical seed bound also guards quartic extrapolation excursions.
        if not _bounded_slope(piece, t, cfg):
            continue
        if cost < best_cost:
            best, best_cost = piece, cost
    return best


def _component_near(t, indices, anchor, gap):
    if len(indices) < 2:
        return indices
    chunks = np.split(indices, np.flatnonzero(np.diff(t[indices]) > gap) + 1)
    return max(chunks, key=lambda chunk: (len(np.intersect1d(chunk, anchor)), len(chunk)))


def _refine(t, y, indices, prediction, cfg, *, grow=True):
    indices = np.sort(indices)
    piece = _best_piece(t, y, indices, prediction, cfg)
    if piece is None:
        return None
    gate = cfg.association_sigma * cfg.noise_sigma_hz
    for _ in range(8 if grow else 3):
        if grow:
            eligible = np.flatnonzero(
                (t >= t[indices].min() - cfg.max_gap_s) & (t <= t[indices].max() + cfg.max_gap_s)
            )
        else:
            eligible = indices
        residual = _wrap(y[eligible] - _predict(piece, t[eligible]), cfg.alias_spacing_hz)
        new = eligible[np.abs(residual) < gate]
        new = _component_near(t, new, indices, cfg.max_gap_s)
        if len(new) < cfg.min_points:
            return None
        fitted = _best_piece(t, y, new, _predict(piece, t[new]), cfg)
        if fitted is None:
            return None
        same = np.array_equal(new, indices)
        indices, piece = new, fitted
        if same:
            break
    piece["indices"] = indices
    return piece


def _penalty(piece, cfg):
    return cfg.track_penalty + (piece["degree"] + 1) * np.log(max(len(piece["indices"]), 2))


def _bounded_slope(piece, t, cfg):
    """Bound slope at all extrema over the full observed support interval."""
    support = t[piece["indices"]]
    endpoints = (np.array([support.min(), support.max()]) - piece["reference_time_s"]) / piece[
        "time_scale_s"
    ]
    derivative = leg.legder(piece["coefficients_hz"])
    roots = leg.legroots(leg.legder(derivative))
    real = roots.real[np.abs(roots.imag) <= 1e-10]
    interior = real[(real > endpoints[0]) & (real < endpoints[1])]
    candidates = np.concatenate((endpoints, interior))
    slope = leg.legval(candidates, derivative) / piece["time_scale_s"]
    return bool(np.max(np.abs(slope)) <= cfg.max_slope_hz_s)


def _cost(piece, t, y, cfg):
    cost = np.full(len(t), cfg.association_sigma**2)
    eligible = (t >= t[piece["indices"]].min()) & (t <= t[piece["indices"]].max())
    rr = _wrap(y[eligible] - _predict(piece, t[eligible]), cfg.alias_spacing_hz)
    cost[eligible] = np.minimum((rr / cfg.noise_sigma_hz) ** 2, cfg.association_sigma**2)
    return cost


def _proposals(t, y, cfg):
    rng = np.random.default_rng(cfg.random_seed)
    proposals, fingerprints = [], set()
    for width in cfg.window_lengths_s:
        for start in np.arange(t[0], t[-1] + 0.001, width / 2):
            local = np.flatnonzero((t >= start) & (t <= start + width))
            if len(local) < cfg.min_points or np.ptp(t[local]) < cfg.min_span_s:
                continue
            aa, bb = np.triu_indices(len(local), 1)
            dt = t[local[bb]] - t[local[aa]]
            valid = (dt >= 1.0) & (dt <= width * 0.8)
            aa, bb = local[aa[valid]], local[bb[valid]]
            if len(aa) > cfg.seed_trials:
                pick = rng.choice(len(aa), cfg.seed_trials, replace=False)
                aa, bb = aa[pick], bb[pick]
            if not len(aa):
                continue
            dt = t[bb] - t[aa]
            delta = _wrap(y[bb] - y[aa], cfg.alias_spacing_hz)
            # Enumerate every alias branch allowed by the declared slope bound.
            max_branch = int(np.ceil(cfg.max_slope_hz_s * dt.max() / cfg.alias_spacing_hz))
            seeds = []
            for branch in range(-max_branch, max_branch + 1):
                slopes = (delta + branch * cfg.alias_spacing_hz) / dt
                good = np.flatnonzero(np.abs(slopes) <= cfg.max_slope_hz_s)
                if not len(good):
                    continue
                pred = y[aa[good], None] + slopes[good, None] * (t[local] - t[aa[good], None])
                residual = _wrap(y[local] - pred, cfg.alias_spacing_hz)
                keep = np.abs(residual) < cfg.association_sigma * cfg.noise_sigma_hz
                support = keep.sum(axis=1)
                for k in np.argsort(-support, kind="stable")[:6]:
                    if support[k] >= cfg.min_points:
                        seeds.append((int(support[k]), local[keep[k]], pred[k, keep[k]]))
            for _, ix, pred in sorted(seeds, key=lambda row: -row[0])[:8]:
                piece = _refine(t, y, ix, pred, cfg)
                if piece is None:
                    continue
                key = tuple(piece["indices"])
                if key in fingerprints:
                    continue
                fingerprints.add(key)
                proposals.append(piece)
    proposals.sort(
        key=lambda p: -(np.sum(cfg.association_sigma**2 - _cost(p, t, y, cfg)) - _penalty(p, cfg))
    )
    return proposals[: cfg.max_proposals], len(proposals)


def _assign(models, t, y, cfg):
    if not models:
        return np.full(len(t), -1, dtype=int)
    costs = np.asarray([_cost(model, t, y, cfg) for model in models])
    chosen = np.argmin(costs, axis=0)
    chosen[costs[chosen, np.arange(len(t))] >= cfg.association_sigma**2] = -1
    return chosen


def _select(proposals, t, y, cfg):
    current = np.full(len(t), cfg.association_sigma**2)
    selected = []
    costs = [_cost(p, t, y, cfg) for p in proposals]
    while costs and len(selected) < cfg.max_tracks:
        gains = [
            float(np.maximum(current - cost, 0).sum() - _penalty(p, cfg))
            for p, cost in zip(proposals, costs, strict=True)
        ]
        best = int(np.argmax(gains))
        if gains[best] <= 0:
            break
        selected.append(proposals.pop(best))
        current = np.minimum(current, costs.pop(best))
    for _ in range(cfg.joint_iterations):
        assignment = _assign(selected, t, y, cfg)
        refined = []
        for number, model in enumerate(selected):
            ix = np.flatnonzero(assignment == number)
            if len(ix) < cfg.min_points:
                continue
            fit = _refine(t, y, ix, _predict(model, t[ix]), cfg, grow=False)
            if fit is None:
                continue
            improvement = np.sum(cfg.association_sigma**2 - _cost(fit, t, y, cfg))
            if improvement > _penalty(fit, cfg):
                refined.append(fit)
        selected = refined
    assignment = _assign(selected, t, y, cfg)
    # Final supports must agree exactly with final competition, with no duplicate
    # ownership at crossings. Refit once on precisely that support.
    final = []
    for number, model in enumerate(selected):
        ix = np.flatnonzero(assignment == number)
        fit = _refine(t, y, ix, _predict(model, t[ix]), cfg, grow=False)
        if fit is not None:
            final.append(fit)
    return final


def _diagnose(piece, t, y, cfg):
    ix = piece["indices"]
    residual = _wrap(y[ix] - _predict(piece, t[ix]), cfg.alias_spacing_hz)
    z = residual / cfg.noise_sigma_hz
    bins = [part for part in np.array_split(np.arange(len(ix)), min(5, len(ix) // 3)) if len(part)]
    means = [float(np.mean(residual[part])) for part in bins]
    local_z = [float(np.mean(z[part]) * np.sqrt(len(part))) for part in bins]
    centered = z - z.mean()
    bridge = float(np.max(np.abs(np.cumsum(centered))) / np.sqrt(len(z)))
    lag = (
        float(np.corrcoef(residual[:-1], residual[1:])[0, 1])
        if len(ix) > 3 and np.std(residual) > 1e-10
        else 0.0
    )
    # Exclude contiguous interior blocks; retain a fixed noise scale. This is a
    # conditional diagnostic on the discovered membership, not independent
    # validation of discovery or of the noise/clutter classification.
    errors = []
    for block in np.array_split(np.arange(len(ix)), 5)[1:-1]:
        train = np.setdiff1d(np.arange(len(ix)), block)
        if len(train) < max(cfg.min_points, 2 * (piece["degree"] + 1)):
            continue
        lifted = _predict(piece, t[ix]) + residual
        held = _piece(t, lifted[train], ix[train], piece["degree"])
        errors.extend(
            _wrap(y[ix[block]] - _predict(held, t[ix[block]]), cfg.alias_spacing_hz).tolist()
        )
    flags = []
    if max(np.abs(local_z), default=0) > 3.5:
        flags.append("local_mean_structure")
    if bridge > 1.6:
        flags.append("cumulative_residual_structure")
    if abs(lag) > max(0.35, 2.5 / np.sqrt(len(ix))):
        flags.append("adjacent_residual_correlation")
    held_rms = float(np.sqrt(np.mean(np.square(errors)))) if errors else None
    if held_rms is not None and held_rms > 2 * cfg.noise_sigma_hz:
        flags.append("blocked_prediction_error")
    return dict(
        residual_mean_hz=float(np.mean(residual)),
        residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
        local_mean_hz=means,
        local_mean_standard_errors=local_z,
        cumulative_bridge=bridge,
        adjacent_residual_correlation=lag,
        conditional_block_holdout_rms_hz=held_rms,
        quality_flags=flags,
        quality_status="structure_flagged"
        if flags
        else ("insufficient_support" if len(ix) < 20 else "no_structure_detected"),
    )


def _join(left, right, t, y, cfg):
    """Fit two pieces with exact shared value and derivative at a midpoint knot."""
    il, ir = left["indices"], right["indices"]
    gap = float(t[ir].min() - t[il].max())
    if gap < 0 or gap > cfg.max_join_gap_s:
        return None
    knot = float((t[ir].min() + t[il].max()) / 2)
    period = cfg.alias_spacing_hz
    offset = float(
        np.round(
            (_predict(left, np.asarray([knot]))[0] - _predict(right, np.asarray([knot]))[0])
            / period
        )
        * period
    )
    mismatch = (
        _predict(left, np.asarray([knot]))[0] - _predict(right, np.asarray([knot]))[0] - offset
    )
    if abs(mismatch) > cfg.association_sigma * cfg.noise_sigma_hz:
        return None
    ix = np.concatenate((il, ir))
    lifted = np.concatenate(
        (
            _predict(left, t[il]) + _wrap(y[il] - _predict(left, t[il]), period),
            _predict(right, t[ir]) + offset + _wrap(y[ir] - _predict(right, t[ir]), period),
        )
    )
    best, score = None, float("inf")
    separate = sum(
        np.sum(
            (_wrap(y[p["indices"]] - _predict(p, t[p["indices"]]), period) / cfg.noise_sigma_hz)
            ** 2
        )
        + _penalty(p, cfg)
        for p in (left, right)
    )
    # Also prefer a single polynomial when it explains both fragments.
    whole = _best_piece(t, y, ix, lifted, cfg)
    if whole is not None:
        rr = _wrap(y[ix] - _predict(whole, t[ix]), period)
        val = float(np.sum((rr / cfg.noise_sigma_hz) ** 2) + _penalty(whole, cfg))
        if np.max(np.abs(rr)) < cfg.association_sigma * cfg.noise_sigma_hz and val < separate:
            best, score = [whole], val
    for dl in range(1, cfg.max_degree + 1):
        for dr in range(1, cfg.max_degree + 1):
            if not (_supported(t, il, dl, cfg) and _supported(t, ir, dr, cfg)):
                continue
            pl = _piece(t, lifted[: len(il)], il, dl)
            pr = _piece(t, lifted[len(il) :], ir, dr)
            vl = leg.legvander((t[il] - pl["reference_time_s"]) / pl["time_scale_s"], dl)
            vr = leg.legvander((t[ir] - pr["reference_time_s"]) / pr["time_scale_s"], dr)
            design = np.zeros((len(ix), dl + dr + 2))
            design[: len(il), : dl + 1], design[len(il) :, dl + 1 :] = vl, vr
            constraints = np.zeros((2, design.shape[1]))
            for p, degree, sl, sign in (
                (pl, dl, slice(0, dl + 1), 1),
                (pr, dr, slice(dl + 1, None), -1),
            ):
                x = (knot - p["reference_time_s"]) / p["time_scale_s"]
                constraints[0, sl] = sign * leg.legvander(x, degree)[0]
                constraints[1, sl] = sign * np.array(
                    [
                        leg.legval(x, leg.legder(np.eye(degree + 1)[k])) / p["time_scale_s"]
                        for k in range(degree + 1)
                    ]
                )
            _, _, vh = np.linalg.svd(constraints, full_matrices=True)
            null = vh[2:].T
            coeff = null @ np.linalg.lstsq(design @ null, lifted, rcond=None)[0]
            rr = lifted - design @ coeff
            free = dl + dr  # two C1 equality constraints
            val = float(
                np.sum((rr / cfg.noise_sigma_hz) ** 2)
                + cfg.track_penalty
                + cfg.breakpoint_penalty
                + free * np.log(len(ix))
            )
            if (
                val < min(score, separate)
                and np.max(np.abs(rr)) < cfg.association_sigma * cfg.noise_sigma_hz
            ):
                pl["coefficients_hz"], pr["coefficients_hz"] = coeff[: dl + 1], coeff[dl + 1 :]
                if not (_bounded_slope(pl, t, cfg) and _bounded_slope(pr, t, cfg)):
                    continue
                pl["join_time_s"] = pr["join_time_s"] = knot
                best, score = [pl, pr], val
    return best


def _group_objective(pieces, t, y, cfg):
    n = sum(len(p["indices"]) for p in pieces)
    free = sum(p["degree"] + 1 for p in pieces) - 2 * (len(pieces) - 1)
    return float(
        sum(
            np.sum(
                (
                    _wrap(y[p["indices"]] - _predict(p, t[p["indices"]]), cfg.alias_spacing_hz)
                    / cfg.noise_sigma_hz
                )
                ** 2
            )
            for p in pieces
        )
        + cfg.track_penalty
        + (len(pieces) - 1) * cfg.breakpoint_penalty
        + free * np.log(max(n, 2))
    )


def _repair_structured(models, t, y, cfg):
    """Repair a real curve braided between competing polynomial proposals.

    Only structured candidates and nearby overlapping pairs are considered;
    each repair uses the same full union of memberships and at most nine knots.
    A true crossing with two resolved frequencies cannot pass the residual gate.
    """
    flags = [bool(_diagnose(p, t, y, cfg)["quality_flags"]) for p in models]
    consumed, repaired = set(), []
    for i, model in enumerate(models):
        if i in consumed:
            continue
        best, best_gain, partner = None, 0.0, None
        alternatives = [None] if flags[i] else []
        for j in range(i + 1, len(models)):
            other = models[j]
            if j in consumed or not (flags[i] or flags[j]):
                continue
            low = max(t[model["indices"]].min(), t[other["indices"]].min())
            high = min(t[model["indices"]].max(), t[other["indices"]].max())
            if high - low < cfg.min_span_s:
                continue
            sample = np.linspace(low, high, 9)
            disagreement = np.abs(
                _wrap(_predict(model, sample) - _predict(other, sample), cfg.alias_spacing_hz)
            )
            if np.median(disagreement) < 2 * cfg.association_sigma * cfg.noise_sigma_hz:
                alternatives.append(j)
        # Strongest temporal competitors first, with a strict pair budget.
        for j in alternatives[:5]:
            source = [model] if j is None else [model, models[j]]
            ix = np.sort(np.concatenate([p["indices"] for p in source]))
            if len(ix) < 2 * cfg.min_points:
                continue
            prediction = np.empty(len(ix))
            ref = float(np.median(t[ix]))
            base = _predict(model, np.asarray([ref]))[0]
            for p in source:
                rows = p["indices"]
                offset = (
                    np.round((base - _predict(p, np.asarray([ref]))[0]) / cfg.alias_spacing_hz)
                    * cfg.alias_spacing_hz
                )
                prediction[np.searchsorted(ix, rows)] = _predict(p, t[rows]) + offset
            baseline = sum(_group_objective([p], t, y, cfg) for p in source)
            for fraction in np.linspace(0.2, 0.8, 9):
                cut = int(np.floor(len(ix) * fraction))
                # Keep simultaneous measurements together.
                cut = int(np.searchsorted(t[ix], t[ix[min(cut, len(ix) - 1)]], side="left"))
                if cut < cfg.min_points or len(ix) - cut < cfg.min_points:
                    continue
                left = _best_piece(t, y, ix[:cut], prediction[:cut], cfg)
                right = _best_piece(t, y, ix[cut:], prediction[cut:], cfg)
                if left is None or right is None:
                    continue
                candidate = _join(left, right, t, y, cfg)
                if candidate is None or any(
                    _diagnose(p, t, y, cfg)["quality_flags"] for p in candidate
                ):
                    continue
                gain = baseline - _group_objective(candidate, t, y, cfg)
                if gain > best_gain:
                    best, best_gain, partner = candidate, gain, j
        if best is not None:
            repaired.append(best)
            consumed.add(i)
            if partner is not None:
                consumed.add(partner)
        else:
            repaired.append([model])
    return repaired


def fit_lane(time_s: np.ndarray, cfo_hz: np.ndarray, config: TrackConfig | None = None) -> dict:
    """Cluster one lane; output indices and assignment preserve input row order.

    Nonfinite measurements are unresolved. Each point has at most one owner.
    ``y + alias_lifts * alias_spacing_hz`` equals prediction plus its residual.
    Quality diagnostics flag concerns; they do not certify white noise. Joining
    is a conservative pairwise C1 operation, with at most two pieces per track.
    """
    cfg = config or TrackConfig()
    times, values = np.asarray(time_s, float), np.asarray(cfo_hz, float)
    if times.ndim != 1 or times.shape != values.shape:
        raise ValueError("time_s and cfo_hz must be matching one-dimensional arrays")
    assignment, lifts = np.full(len(times), -1, int), np.zeros(len(times), int)
    valid = np.flatnonzero(np.isfinite(times) & np.isfinite(values))
    order = valid[np.lexsort((values[valid], times[valid]))]
    t, y = times[order], values[order]
    if len(t) < cfg.min_points or np.ptp(t) < cfg.min_span_s:
        return dict(
            tracks=[],
            assignment=assignment,
            alias_lifts=lifts,
            diagnostics=dict(
                proposals_generated=0,
                proposals_retained=0,
                nonfinite_points=int(len(times) - len(valid)),
            ),
        )
    proposals, generated = _proposals(t, y, cfg)
    retained = len(proposals)
    selected = _select(proposals.copy(), t, y, cfg)
    selected.sort(
        key=lambda p: (
            float(t[p["indices"]].min()),
            float(_predict(p, np.asarray([t[p["indices"][0]]]))[0]),
        )
    )
    repaired = _repair_structured(selected, t, y, cfg)
    # Pieces created by a repair already form a complete C1 track. Single
    # pieces remain eligible for the simpler adjacent-fragment joining pass.
    grouped = [pieces for pieces in repaired if len(pieces) > 1]
    selected = [pieces[0] for pieces in repaired if len(pieces) == 1]
    selected.sort(key=lambda p: float(t[p["indices"]].min()))
    consumed = set()
    for i, left in enumerate(selected):
        if i in consumed:
            continue
        joined = None
        # Never join pieces with substantial residual structure.
        if not _diagnose(left, t, y, cfg)["quality_flags"]:
            for j in range(i + 1, len(selected)):
                if j in consumed or _diagnose(selected[j], t, y, cfg)["quality_flags"]:
                    continue
                joined = _join(left, selected[j], t, y, cfg)
                if joined is not None:
                    consumed.add(j)
                    break
        grouped.append(joined if joined is not None else [left])
    tracks = []
    for pieces in grouped:
        # Choose a deterministic gauge for a whole track, preserving every C1
        # join. The first predicted frequency lies in the principal alias band.
        first = pieces[0]
        gauge = np.floor(
            (_predict(first, np.asarray([t[first["indices"][0]]]))[0] + cfg.alias_spacing_hz / 2)
            / cfg.alias_spacing_hz
        )
        for piece in pieces:
            piece["coefficients_hz"][0] -= gauge * cfg.alias_spacing_hz
        diagnostics = [_diagnose(piece, t, y, cfg) for piece in pieces]
        ix = np.concatenate([p["indices"] for p in pieces])
        # Competition may have changed a winner's support after its last fit.
        # The original final memberships are disjoint by construction.
        if np.any(assignment[order[ix]] >= 0):
            raise RuntimeError("internal duplicate observation ownership")
        residuals = []
        for piece in pieces:
            rows = piece["indices"]
            prediction = _predict(piece, t[rows])
            lifts[order[rows]] = np.rint((prediction - y[rows]) / cfg.alias_spacing_hz).astype(int)
            residuals.extend(_wrap(y[rows] - prediction, cfg.alias_spacing_hz).tolist())
            piece["indices"] = order[rows]
        number = len(tracks)
        assignment[order[ix]] = number
        flags = sorted(set(flag for d in diagnostics for flag in d["quality_flags"]))
        status = (
            "structure_flagged"
            if flags
            else (
                "insufficient_support"
                if any(d["quality_status"] == "insufficient_support" for d in diagnostics)
                else "no_structure_detected"
            )
        )
        tracks.append(
            dict(
                indices=order[ix],
                pieces=pieces,
                residual_rms_hz=float(np.sqrt(np.mean(np.square(residuals)))),
                start_s=float(t[ix].min()),
                end_s=float(t[ix].max()),
                diagnostics=dict(pieces=diagnostics, quality_flags=flags, quality_status=status),
            )
        )
    return dict(
        tracks=tracks,
        assignment=assignment,
        alias_lifts=lifts,
        diagnostics=dict(
            proposals_generated=generated,
            proposals_retained=retained,
            nonfinite_points=int(len(times) - len(valid)),
            objective="capped_fixed_scale_squared_residual_plus_MDL",
            search="deterministic_local_proposals_and_joint_competition",
            limitations=[
                "local optimum; no exhaustive alias or breakpoint search",
                "at most two C1 polynomial pieces per track",
                "conditional residual checks are not independent discovery validation",
            ],
        ),
    )
