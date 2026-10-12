"""Sparse conditional GLRT candidate-set frequency model (research).

One receiver/probe is one factor: candidate peaks are alternatives, not repeated
measurements. Given the observed marks and candidate count, exactly one candidate
can be signal, or all are clutter. This is a normalized conditional density under
the stated model. Across probes it is a composite likelihood until dependence and
mark calibration have been qualified. No storage or orbital implementation here.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FrequencyEvidence:
    ids: tuple[str, ...]
    frequency_hz: np.ndarray
    candidate_weight: np.ndarray
    signal_probability: np.ndarray
    group: np.ndarray
    time_s: np.ndarray

    def __post_init__(self):
        n = len(self.ids)
        y, w = self.frequency_hz, self.candidate_weight
        if not n or len(set(self.ids)) != n:
            raise ValueError("nonempty unique physical observation IDs required")
        if y.ndim != 2 or y.shape != w.shape or y.shape[0] != n:
            raise ValueError("candidate array shape mismatch")
        if any(a.shape != (n,) for a in (self.signal_probability, self.group, self.time_s)):
            raise ValueError("factor array shape mismatch")
        if any(
            not np.all(np.isfinite(a))
            for a in (y, w, self.signal_probability, self.group, self.time_s)
        ):
            raise ValueError("finite evidence required")
        if (
            np.any(w < 0)
            or not np.allclose(w.sum(axis=1), 1)
            or np.any(self.signal_probability < 0)
            or np.any(self.signal_probability > 1)
            or np.any(self.group < 0)
            or self.group.dtype.kind not in "iu"
        ):
            raise ValueError("invalid weights, probabilities or groups")


@dataclass(frozen=True)
class SparseConfig:
    scale_hz: float = 1500.0
    background_scale_hz: float = 300000.0
    offset_sigma_hz: float = 300000.0
    satellite_penalty: float = 8.0
    maximum_satellites: int = 12
    iterations: int = 24
    em_iterations: int = 35

    def __post_init__(self):
        if any(
            not np.isfinite(v) or v <= 0
            for v in (self.scale_hz, self.background_scale_hz, self.offset_sigma_hz)
        ):
            raise ValueError("positive finite scales required")
        if (
            not np.isfinite(self.satellite_penalty)
            or self.satellite_penalty < 0
            or min(self.maximum_satellites, self.iterations, self.em_iterations) < 1
        ):
            raise ValueError("invalid search limits or penalty")


def candidate_ratios(evidence, prediction_hz, visible, offsets, config, derivative=False):
    """Signal/clutter ratios, including mark-conditioned null probability.

    A satellite below the horizon contributes the clutter density. This transfers
    its unobservable activity mass to background without inventing nondetections.
    The background is a proper Cauchy density on the real frequency axis.
    """
    mu = np.asarray(prediction_hz, dtype=float)
    visible = np.asarray(visible, dtype=bool)
    offsets = np.asarray(offsets, dtype=float)
    if (
        mu.ndim != 2
        or mu.shape[0] != len(evidence.ids)
        or visible.shape != mu.shape
        or offsets.shape != (int(evidence.group.max()) + 1,)
        or not np.all(np.isfinite(mu))
        or not np.all(np.isfinite(offsets))
    ):
        raise ValueError("invalid predictions, visibility or offsets")
    n, satellites = mu.shape
    value = np.zeros((n, satellites))
    gradient = np.zeros_like(value)
    curvature = np.zeros_like(value)
    scale2 = config.scale_hz**2
    for k in range(evidence.frequency_hz.shape[1]):
        y = evidence.frequency_hz[:, k]
        background = config.background_scale_hz / (np.pi * (config.background_scale_hz**2 + y * y))
        r = y[:, None] - mu - offsets[evidence.group, None]
        denominator = scale2 + r * r
        term = (evidence.candidate_weight[:, k] / background)[:, None] * (
            config.scale_hz / (np.pi * denominator)
        )
        value += term
        if derivative:
            gradient += term * 2 * r / denominator
            # Positive complete-data IRLS information; proposals checked below.
            curvature += term * 2 / denominator
    q = evidence.signal_probability[:, None] * visible
    return (1 - q + q * value, q * gradient, q * curvature) if derivative else 1 - q + q * value


def fit_weights(ratios, iterations=35, initial=None):
    """EM on a normalized simplex including an always-present clutter column."""
    matrix = np.column_stack((np.ones(len(ratios)), ratios))
    weights = (
        np.full(matrix.shape[1], 1 / matrix.shape[1])
        if initial is None
        else np.asarray(initial, dtype=float).copy()
    )
    for _ in range(iterations):
        mixture = matrix @ weights
        updated = weights * np.mean(matrix / mixture[:, None], axis=0)
        updated /= updated.sum()
        if np.max(np.abs(updated - weights)) < 1e-7:
            weights = updated
            break
        weights = updated
    return weights, float(np.log(matrix @ weights).sum())


def select_sparse(ratios, config, incumbent=(), penalties=None, initial_weights=None):
    """Forward additions and backward deletions; every candidate is considered.

    This is a bounded local subset search, not a certificate of minimality.
    """
    costs = (
        np.full(ratios.shape[1], config.satellite_penalty)
        if penalties is None
        else np.asarray(penalties, float)
    )
    if costs.shape != (ratios.shape[1],) or not np.isfinite(costs).all() or np.any(costs < 0):
        raise ValueError("one finite nonnegative penalty per satellite required")
    active = list(incumbent)
    if initial_weights is not None:
        initial_weights = np.asarray(initial_weights, float)
        if (
            initial_weights.shape != (len(active) + 1,)
            or np.any(initial_weights < 0)
            or not np.isfinite(initial_weights).all()
            or not np.isclose(initial_weights.sum(), 1.0)
        ):
            raise ValueError("normalized incumbent weights required")
    weights, ll = fit_weights(ratios[:, active], config.em_iterations, initial_weights)
    score = ll - costs[active].sum()
    if score < 0:
        active, weights, score = [], np.ones(1), 0.0
    mixture = weights[0] + ratios[:, active] @ weights[1:]
    curve = [
        {"satellites": len(active), "log_ratio": float(np.log(mixture).sum()), "penalized": score}
    ]
    for _ in range(min(config.maximum_satellites, ratios.shape[1]) - len(active)):
        # Screen the full catalogue by its exact directional derivative at zero
        # insertion mass, then refit the three strongest additions. This bounds
        # work; it is a proposal heuristic, not an exhaustive discrete search.
        gains = np.sum(ratios / mixture[:, None], axis=0) - len(ratios)
        gains[active] = -np.inf
        best = None
        for candidate in np.argsort(gains)[-3:][::-1]:
            if candidate in active:
                continue
            chosen = active + [int(candidate)]
            w, ll = fit_weights(ratios[:, chosen], config.em_iterations)
            objective = ll - costs[chosen].sum()
            if best is None or objective > best[0]:
                best = objective, chosen, w, ll
        if best is None or best[0] <= score + 1e-7:
            break
        score, active, weights, ll = best
        mixture = weights[0] + ratios[:, active] @ weights[1:]
        curve.append({"satellites": len(active), "log_ratio": ll, "penalized": score})
    # Preserve the previous feasible subset: reselection must never discard an
    # improvement from the continuous solve merely because greedy order changed.
    if len(incumbent):
        old_weights, ll = fit_weights(ratios[:, incumbent], config.em_iterations, initial_weights)
        old_score = ll - costs[list(incumbent)].sum()
        if old_score > score:
            active, weights, score = list(incumbent), old_weights, old_score
    # A bounded swap pass can escape a greedy choice even at the cardinality cap.
    if active:
        mixture = weights[0] + ratios[:, active] @ weights[1:]
        gain = np.sum(ratios / mixture[:, None], axis=0)
        gain[active] = -np.inf
        additions = np.argsort(gain)[-3:]
        removals = np.argsort(weights[1:])[:3]
        best = None
        for add in additions:
            if add in active:
                continue
            for remove in removals:
                chosen = [s for k, s in enumerate(active) if k != remove] + [int(add)]
                w, ll = fit_weights(ratios[:, chosen], config.em_iterations)
                objective = ll - costs[chosen].sum()
                if objective > score + 1e-7 and (best is None or objective > best[0]):
                    best = objective, chosen, w
        if best is not None:
            score, active, weights = best
    # Removal can improve a solution after another satellite has been added.
    while active:
        best = None
        for k in range(len(active)):
            chosen = active[:k] + active[k + 1 :]
            w, ll = fit_weights(ratios[:, chosen], config.em_iterations)
            objective = ll - costs[chosen].sum()
            if objective > score + 1e-7 and (best is None or objective > best[0]):
                best = objective, chosen, w
        if best is None:
            break
        score, active, weights = best
    return active, weights, score, curve


def fit_sparse(evidence, prediction_hz, visible, seeds, config=None):
    """Profile group offsets jointly with sparse satellite activity.

    All starts have identical budgets. Full-catalogue reselection follows each
    offset solve. Returns scores relative to the same all-clutter observations.
    """
    config = SparseConfig() if config is None else config
    results = []
    prior_precision = 1 / config.offset_sigma_hz**2
    for seed in seeds:
        offsets = np.asarray(
            seed["offsets_hz"] if isinstance(seed, dict) else seed, dtype=float
        ).copy()
        previous = -np.inf
        history = []
        converged = False
        active = list(seed.get("active", ())) if isinstance(seed, dict) else []
        if (
            len(set(active)) != len(active)
            or len(active) > config.maximum_satellites
            or any(i < 0 or i >= prediction_hz.shape[1] for i in active)
        ):
            raise ValueError("invalid seed satellite subset")
        for iteration in range(config.iterations):
            ratios = candidate_ratios(evidence, prediction_hz, visible, offsets, config)
            active, weights, raw_score, curve = select_sparse(ratios, config, active)
            score = raw_score - 0.5 * np.dot(offsets, offsets) * prior_precision
            history.append(score)
            if not active or (iteration and abs(score - previous) < 1e-4):
                converged = True
                break
            previous = score
            # A few monotone IRLS steps, with identity fixed but weights refitted.
            for _ in range(24):
                ratio, derivative, information = candidate_ratios(
                    evidence,
                    prediction_hz[:, active],
                    visible[:, active],
                    offsets,
                    config,
                    derivative=True,
                )
                mixture = weights[0] + ratio @ weights[1:]
                gradient = (
                    np.bincount(
                        evidence.group,
                        weights=(derivative @ weights[1:]) / mixture,
                        minlength=len(offsets),
                    )
                    - offsets * prior_precision
                )
                precision = (
                    np.bincount(
                        evidence.group,
                        weights=(information @ weights[1:]) / mixture,
                        minlength=len(offsets),
                    )
                    + prior_precision
                )
                step = np.clip(gradient / precision, -10000.0, 10000.0)
                accepted = False
                for damping in (1.0, 0.5, 0.25, 0.125, 0.0625):
                    trial = offsets + damping * step
                    new_ratio = candidate_ratios(
                        evidence, prediction_hz[:, active], visible[:, active], trial, config
                    )
                    new_weights, ll = fit_weights(new_ratio, config.em_iterations, weights)
                    new_score = (
                        ll
                        - config.satellite_penalty * len(active)
                        - 0.5 * np.dot(trial, trial) * prior_precision
                    )
                    if new_score > score + 1e-9:
                        offsets, weights, score = trial, new_weights, new_score
                        accepted = True
                        break
                if not accepted or np.max(np.abs(step)) < 0.02:
                    break
        ratio = candidate_ratios(evidence, prediction_hz, visible, offsets, config)
        active, weights, raw_score, curve = select_sparse(ratio, config, active)
        score = raw_score - 0.5 * np.dot(offsets, offsets) * prior_precision
        mixture = weights[0] + ratio[:, active] @ weights[1:]
        # The signal-only responsibility excludes the component's clutter part.
        signal = np.zeros((len(evidence.ids), len(active)))
        for k, s in enumerate(active):
            q = evidence.signal_probability * visible[:, s]
            signal[:, k] = weights[k + 1] * (ratio[:, s] - (1 - q)) / mixture
        results.append(
            dict(
                score=float(score),
                log_ratio=float(np.log(mixture).sum()),
                offset_prior_cost=float(0.5 * np.dot(offsets, offsets) * prior_precision),
                satellite_penalty=float(config.satellite_penalty * len(active)),
                active=active,
                weights=weights.tolist(),
                offsets_hz=offsets.tolist(),
                signal_support=signal.sum(axis=0).tolist(),
                effective_background=float(np.mean(1 - signal.sum(axis=1))),
                converged=converged,
                iterations=iteration + 1,
                history=history,
                cardinality_curve=curve,
            )
        )
    if not results:
        raise ValueError("at least one nuisance seed required")
    # The all-clutter model has no informed offset parameters: its prior mode is
    # zero regardless of supplied starts. Always retain that feasible baseline.
    if max(item["score"] for item in results) < 0:
        results.append(
            dict(
                score=0.0,
                log_ratio=0.0,
                offset_prior_cost=0.0,
                satellite_penalty=0.0,
                active=[],
                weights=[1.0],
                offsets_hz=[0.0] * (int(evidence.group.max()) + 1),
                signal_support=[],
                effective_background=1.0,
                converged=True,
                iterations=0,
                history=[0.0],
                cardinality_curve=[dict(satellites=0, log_ratio=0.0, penalized=0.0)],
            )
        )
    best = max(results, key=lambda item: item["score"])
    return {
        **best,
        "starts": [
            {k: r[k] for k in ("score", "active", "offsets_hz", "converged", "iterations")}
            for r in results
        ],
        "search_exact": False,
        "at_satellite_cap": len(best["active"]) == config.maximum_satellites,
    }
