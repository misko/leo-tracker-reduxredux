"""Orbit-blind same-lane stitching with continuous curves and residual audits.

These are bootstrap proposals, not satellite identities. Each accepted union
is checked again as a whole, so pairwise compatibility cannot silently bridge
an incompatible chain. No frequency offset other than an integer pilot alias
is introduced at a join.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ContinuousMergeConfiguration:
    policy: str = "continuous-same-lane-gap8-v1"
    maximum_gap_s: float = 8.0
    maximum_overlap_s: float = 0.05
    endpoint_gate_hz: float = 2500.0
    maximum_held_rms_hz: float = 500.0
    maximum_step_hz: float = 200.0
    maximum_slope_change_hz_s: float = 20.0
    block_s: float = 2.0
    folds: int = 5
    repeats: int = 8
    seed: int = 20261012
    degrees: tuple[int, ...] = (2, 3, 4)

    def __post_init__(self):
        if self.policy != "continuous-same-lane-gap8-v1":
            raise ValueError("unknown merge policy")
        for value in (
            self.maximum_gap_s,
            self.maximum_overlap_s,
            self.endpoint_gate_hz,
            self.maximum_held_rms_hz,
            self.maximum_step_hz,
            self.maximum_slope_change_hz_s,
            self.block_s,
        ):
            if not np.isfinite(value) or value <= 0:
                raise ValueError("merge limits must be finite and positive")
        if self.folds < 2 or self.repeats < 1 or self.degrees != (2, 3, 4):
            raise ValueError("invalid merge model search")


@dataclass(frozen=True)
class TrackSeries:
    member_ids: tuple[str, ...]
    lane_key: tuple
    point_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    times_s: np.ndarray
    values_hz: np.ndarray
    weights: np.ndarray
    alias_spacing_hz: float

    def __post_init__(self):
        n = len(self.times_s)
        if n < 8 or not (
            n
            == len(self.values_hz)
            == len(self.weights)
            == len(self.point_ids)
            == len(self.source_ids)
        ):
            raise ValueError("invalid track support")
        if len(set(self.source_ids)) != n or len(set(self.point_ids)) != n:
            raise ValueError("track reuses an observation")
        if not all(np.isfinite(v).all() for v in (self.times_s, self.values_hz, self.weights)):
            raise ValueError("nonfinite track values")
        if np.any(np.diff(self.times_s) <= 0) or np.any(self.weights <= 0):
            raise ValueError("track times/weights invalid")
        if not np.isfinite(self.alias_spacing_hz) or self.alias_spacing_hz <= 0:
            raise ValueError("invalid pilot alias")


def _matrix(times, boundary, degree, right=None):
    x = (times - boundary) / 20.0
    matrix = np.polynomial.polynomial.polyvander(x, degree)
    if right is not None:
        matrix = np.column_stack((matrix, right, right * x))
    return matrix


def _fit(matrix, values, weights):
    coefficients, _, rank, _ = np.linalg.lstsq(
        matrix * np.sqrt(weights)[:, None], values * np.sqrt(weights), rcond=None
    )
    if rank != matrix.shape[1]:
        raise ValueError("rank-deficient curve")
    return coefficients


def _rms(residual, weights):
    return float(np.sqrt(np.average(residual**2, weights=weights)))


def _endpoint(series, boundary, left):
    # A local quadratic estimates the alias branch across the gap. The
    # subsequent joint fit still has only one global intercept and drift.
    indexes = np.arange(len(series.times_s))[-12:] if left else np.arange(len(series.times_s))[:12]
    matrix = _matrix(series.times_s[indexes], boundary, 2)
    return float(_fit(matrix, series.values_hz[indexes], series.weights[indexes])[0])


def evaluate_join(left, right, config=None, *, residual_guard=True):
    config = config or ContinuousMergeConfiguration()
    receipt = {"left": left.member_ids, "right": right.member_ids, "accepted": False}
    if left.lane_key != right.lane_key or left.alias_spacing_hz != right.alias_spacing_hz:
        return None, dict(receipt, reason="different-lane")
    gap = float(right.times_s[0] - left.times_s[-1])
    receipt["gap_s"] = gap
    if not -config.maximum_overlap_s <= gap <= config.maximum_gap_s:
        return None, dict(receipt, reason="gap-or-overlap")
    boundary = float((right.times_s[0] + left.times_s[-1]) / 2)
    try:
        a, b = _endpoint(left, boundary, True), _endpoint(right, boundary, False)
    except ValueError:
        return None, dict(receipt, reason="endpoint-rank")
    alias_shift = int(round((a - b) / left.alias_spacing_hz))
    endpoint_error = float(b + alias_shift * left.alias_spacing_hz - a)
    receipt.update(alias_shift=alias_shift, endpoint_error_hz=endpoint_error)
    if abs(endpoint_error) > config.endpoint_gate_hz:
        return None, dict(receipt, reason="endpoint-frequency")
    # Keep one existing candidate per original probe, including the possible
    # shared support-center observation at the segment boundary.
    records = {}
    for side, series in enumerate((left, right)):
        for i, source in enumerate(series.source_ids):
            row = (
                series.times_s[i],
                series.values_hz[i] + side * alias_shift * left.alias_spacing_hz,
                series.weights[i],
                series.point_ids[i],
                side,
            )
            previous = records.get(source)
            if previous is None or (-row[2], row[3]) < (-previous[2], previous[3]):
                records[source] = row
    ordered = sorted(records, key=lambda source: (records[source][0], source))
    times, values, weights = [np.array([records[s][i] for s in ordered]) for i in range(3)]
    sides = np.array([records[s][4] for s in ordered], bool)
    blocks = np.floor(times / config.block_s).astype(int)
    unique = np.unique(blocks)
    if len(unique) < config.folds + 2 or min(np.sum(sides), np.sum(~sides)) < 6:
        return None, dict(receipt, reason="insufficient-independent-support")
    rng = np.random.default_rng(config.seed)
    assignments = []
    for _ in range(config.repeats):
        mapping = {int(v): i % config.folds for i, v in enumerate(rng.permutation(unique))}
        assignments.append(np.array([mapping[int(v)] for v in blocks]))

    def held_score(matrix):
        scores = []
        for assignment in assignments:
            residual = np.empty(len(times))
            for fold in range(config.folds):
                test = assignment == fold
                coefficients = _fit(matrix[~test], values[~test], weights[~test])
                residual[test] = values[test] - matrix[test] @ coefficients
            scores.append(_rms(residual, weights))
        return float(np.median(scores))

    models = []
    for degree in config.degrees:
        matrix = _matrix(times, boundary, degree)
        try:
            held = held_score(matrix)
            coefficients = _fit(matrix, values, weights)
            models.append((held, degree, coefficients, matrix))
        except ValueError:
            continue
    if not models:
        return None, dict(receipt, reason="curve-rank")
    best = min(m[0] for m in models)
    # Prefer the least flexible model within 10% plus 5 Hz of the best
    # predictive error; degree selection is a development diagnostic.
    held, degree, coefficients, matrix = min(
        (m for m in models if m[0] <= 1.1 * best + 5), key=lambda m: m[1]
    )
    residual = values - matrix @ coefficients
    fitted_rms = _rms(residual, weights)
    receipt.update(
        degree=degree,
        held_rms_hz=held,
        fitted_rms_hz=fitted_rms,
        model_scores=[{"degree": m[1], "held_rms_hz": m[0]} for m in models],
        boundary_s=boundary,
        coefficients=coefficients.tolist(),
        random_blocks=unique.tolist(),
        seed=config.seed,
    )
    if held > config.maximum_held_rms_hz:
        return None, dict(receipt, reason="held-residual")
    kink = _matrix(times, boundary, degree, sides)
    try:
        extra = _fit(kink, values, weights)
        kink_held = held_score(kink)
    except ValueError:
        return None, dict(receipt, reason="discontinuity-audit-rank")
    jump, slope_change = float(extra[-2]), float(extra[-1] / 20)
    shorter_span = min(np.ptp(times[sides]), np.ptp(times[~sides]))
    step_limit = max(config.maximum_step_hz, 2 * fitted_rms)
    slope_limit = max(config.maximum_slope_change_hz_s, 2 * fitted_rms / shorter_span)
    segment_audits = []
    for mask in (~sides, sides):
        t, y, w = times[mask], residual[mask], weights[mask]
        centered = t - np.average(t, weights=w)
        trend_matrix = np.polynomial.polynomial.polyvander(centered / 20, 2)
        trend = trend_matrix @ _fit(trend_matrix, y, w)
        segment_audits.append(
            {
                "mean_hz": float(np.average(y, weights=w)),
                "trend_peak_to_peak_hz": float(np.ptp(trend)),
                "rms_hz": _rms(y, w),
            }
        )
    receipt.update(
        boundary_jump_hz=jump,
        boundary_slope_change_hz_s=slope_change,
        kink_held_rms_hz=kink_held,
        step_limit_hz=step_limit,
        slope_limit_hz_s=slope_limit,
        segments=segment_audits,
    )
    if residual_guard:
        if abs(jump) > step_limit or abs(slope_change) > slope_limit:
            return None, dict(receipt, reason="boundary-discontinuity")
        if held - kink_held > max(20, 0.2 * held):
            return None, dict(receipt, reason="split-predicts-better")
        if any(
            abs(s["mean_hz"]) > max(100, fitted_rms)
            or s["trend_peak_to_peak_hz"] > max(100, 2 * fitted_rms)
            for s in segment_audits
        ):
            return None, dict(receipt, reason="segment-residual-structure")
    merged = TrackSeries(
        tuple(sorted((*left.member_ids, *right.member_ids))),
        left.lane_key,
        tuple(records[s][3] for s in ordered),
        tuple(ordered),
        times,
        values,
        weights,
        left.alias_spacing_hz,
    )
    return merged, dict(receipt, accepted=True, reason=None)


def merge_tracks(tracks, config=None, *, residual_guard=True):
    """Greedy best-qualified unions; every later union re-audits the full chain."""
    config = config or ContinuousMergeConfiguration()
    active = list(tracks)
    receipts, cache = [], {}
    while True:
        proposed = []
        ordered = sorted(enumerate(active), key=lambda p: (p[1].times_s[0], p[1].member_ids))
        for li, (i, left) in enumerate(ordered):
            for j, right in ordered[li + 1 :]:
                if left.lane_key != right.lane_key:
                    continue
                gap = right.times_s[0] - left.times_s[-1]
                if not -config.maximum_overlap_s <= gap <= config.maximum_gap_s:
                    continue
                key = (left.member_ids, right.member_ids)
                if key not in cache:
                    cache[key] = evaluate_join(left, right, config, residual_guard=residual_guard)
                    receipts.append(cache[key][1])
                merged, receipt = cache[key]
                if merged is not None:
                    proposed.append((receipt["held_rms_hz"], key, i, j, merged))
        if not proposed:
            break
        _, _, i, j, merged = min(proposed, key=lambda p: (p[0], p[1]))
        active = [t for k, t in enumerate(active) if k not in (i, j)] + [merged]
    return tuple(sorted(active, key=lambda t: (t.times_s[0], t.member_ids))), tuple(receipts)
