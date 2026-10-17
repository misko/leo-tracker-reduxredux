"""Bounded multiple-hypothesis state-space discovery of wrapped CFO tracklets.

Each pair seed grows a beam of Kalman state histories, branching on measurement
aliases and missed observations. Trees compete for observations only at final
polynomial compression. This is a bounded approximation to multiple hypothesis
tracking, not an exact global hypothesis posterior or an orbital tracker.
"""

from dataclasses import dataclass

import numpy as np

from leo.analysis.polynomial_tracklets import (
    TrackConfig,
    _best_piece,
    _penalty,
    _predict,
    _refine,
    _wrap,
)


@dataclass
class _Hypothesis:
    state: np.ndarray
    covariance: np.ndarray
    time: float
    last_observed: float
    indices: tuple
    lifted: tuple
    score: float


def _transition(state, covariance, elapsed, sigma):
    transition = np.array([[1, elapsed, elapsed**2 / 2], [0, 1, elapsed], [0, 0, 1]], dtype=float)
    # Integrated white jerk, discretized using actual elapsed time. The sigma
    # scale is declared in diagnostics rather than estimated from selected noise.
    magnitude = max(0.5, sigma / 150)
    process = magnitude**2 * np.array(
        [
            [elapsed**5 / 20, elapsed**4 / 8, elapsed**3 / 6],
            [elapsed**4 / 8, elapsed**3 / 3, elapsed**2 / 2],
            [elapsed**3 / 6, elapsed**2 / 2, elapsed],
        ],
        dtype=float,
    )
    return transition @ state, transition @ covariance @ transition.T + process


def _seeds(t, y, cfg, limit):
    seeds = []
    for left in range(len(t) - 1):
        right = np.flatnonzero((t - t[left] >= 1) & (t - t[left] <= 5))
        feasible = []
        for index in right:
            dt = t[index] - t[left]
            delta = _wrap(y[index] - y[left], cfg.alias_spacing_hz)
            aliases = int(np.ceil(cfg.max_slope_hz_s * dt / cfg.alias_spacing_hz))
            for alias in range(-aliases, aliases + 1):
                slope = (delta + alias * cfg.alias_spacing_hz) / dt
                if abs(slope) <= cfg.max_slope_hz_s:
                    feasible.append((abs(dt - 3), int(index), float(slope)))
        feasible.sort()
        seeds.extend((left, index, slope) for _, index, slope in feasible[:2])
    if len(seeds) > limit:
        select = np.linspace(0, len(seeds) - 1, limit).astype(int)
        seeds = [seeds[i] for i in select]
    return seeds


def _grow(t, y, seed, cfg, beam_width=3, horizon_s=120):
    left, right, slope = seed
    sigma2 = cfg.noise_sigma_hz**2
    state = np.array([y[left] + slope * (t[right] - t[left]), slope, 0.0])
    lifted_right = (
        y[right] + np.rint((state[0] - y[right]) / cfg.alias_spacing_hz) * cfg.alias_spacing_hz
    )
    state[0] = lifted_right
    covariance = np.diag([sigma2, (2 * cfg.noise_sigma_hz) ** 2, 60.0**2])
    beam = [
        _Hypothesis(
            state,
            covariance,
            t[right],
            t[right],
            (left, right),
            (float(y[left]), float(lifted_right)),
            0.0,
        )
    ]
    finished = []
    branches = 0
    for index in range(right + 1, len(t)):
        if t[index] - t[left] > horizon_s:
            break
        candidates = []
        for hypothesis in beam:
            if t[index] - hypothesis.last_observed > cfg.max_gap_s:
                finished.append(hypothesis)
                continue
            dt = t[index] - hypothesis.time
            predicted, uncertainty = _transition(
                hypothesis.state, hypothesis.covariance, dt, cfg.noise_sigma_hz
            )
            candidates.append(
                _Hypothesis(
                    predicted,
                    uncertainty,
                    t[index],
                    hypothesis.last_observed,
                    hypothesis.indices,
                    hypothesis.lifted,
                    hypothesis.score - 0.08 * dt,
                )
            )
            variance = float(uncertainty[0, 0] + sigma2)
            gate = min(
                cfg.association_sigma * np.sqrt(variance),
                6 * cfg.noise_sigma_hz + 300 * (t[index] - hypothesis.last_observed),
            )
            nearest = int(np.rint((predicted[0] - y[index]) / cfg.alias_spacing_hz))
            for alias in range(nearest - 1, nearest + 2):
                lifted = y[index] + alias * cfg.alias_spacing_hz
                innovation = lifted - predicted[0]
                if abs(innovation) > gate:
                    continue
                gain = uncertainty[:, 0] / variance
                updated = predicted + gain * innovation
                if abs(updated[1]) > cfg.max_slope_hz_s:
                    continue
                posterior = uncertainty - np.outer(gain, uncertainty[0])
                reward = (
                    np.log(cfg.alias_spacing_hz / np.sqrt(2 * np.pi * variance))
                    - 0.5 * innovation**2 / variance
                )
                candidates.append(
                    _Hypothesis(
                        updated,
                        (posterior + posterior.T) / 2,
                        t[index],
                        t[index],
                        (*hypothesis.indices, index),
                        (*hypothesis.lifted, float(lifted)),
                        hypothesis.score + reward,
                    )
                )
                branches += 1
        if not candidates:
            break
        candidates.sort(key=lambda item: item.score, reverse=True)
        beam, signatures = [], set()
        for candidate in candidates:
            signature = candidate.indices[-5:]
            if signature not in signatures:
                beam.append(candidate)
                signatures.add(signature)
            if len(beam) == beam_width:
                break
    finished.extend(beam)
    finished.sort(key=lambda item: item.score, reverse=True)
    return finished[:2], branches


def _compress(t, y, indices, lifted, cfg, depth=0):
    """Fit supported degrees jointly; split large innovations or bad model fit."""
    order = np.argsort(indices)
    indices, lifted = np.asarray(indices, int)[order], np.asarray(lifted)[order]
    if len(indices) < cfg.min_points or np.ptp(t[indices]) < cfg.min_span_s:
        return []
    gaps = np.flatnonzero(np.diff(t[indices]) > cfg.max_gap_s)
    if len(gaps):
        models = []
        for part in np.split(np.arange(len(indices)), gaps + 1):
            models.extend(_compress(t, y, indices[part], lifted[part], cfg, depth))
        return models
    model = _best_piece(t, y, indices, lifted, cfg)
    if model is not None:
        residual = _wrap(y[indices] - _predict(model, t[indices]), cfg.alias_spacing_hz)
        good = np.abs(residual) <= cfg.association_sigma * cfg.noise_sigma_hz
        if np.all(good):
            return [model]
        if np.count_nonzero(good) >= max(cfg.min_points, 0.8 * len(indices)):
            fitted = _best_piece(t, y, indices[good], _predict(model, t[indices[good]]), cfg)
            if fitted is not None:
                rr = _wrap(
                    y[indices[good]] - _predict(fitted, t[indices[good]]), cfg.alias_spacing_hz
                )
                if np.all(np.abs(rr) <= cfg.association_sigma * cfg.noise_sigma_hz):
                    return [fitted]
    if depth >= 5 or len(indices) < 2 * cfg.min_points:
        return []
    # Binary subdivision is deliberately conservative; final model competition
    # penalizes any resulting extra tracks instead of silently accepting steps.
    middle = len(indices) // 2
    return _compress(t, y, indices[:middle], lifted[:middle], cfg, depth + 1) + _compress(
        t, y, indices[middle:], lifted[middle:], cfg, depth + 1
    )


def fit_lane(time_s, cfo_hz, config: TrackConfig | None = None) -> dict:
    """Discover one irregularly sampled lane and retain unique original indices."""
    from leo.analysis.tracklet_fitting import finish_lane, prepare_lane

    cfg = config or TrackConfig()
    t, y, order, original_count = prepare_lane(time_s, cfo_hz)
    models, branches, seed_count = [], 0, 0
    fingerprints = set()
    if len(t) >= cfg.min_points and np.ptp(t) >= cfg.min_span_s:
        for backward in (False, True):
            work_t, work_y = (-t[::-1], y[::-1]) if backward else (t, y)
            seeds = _seeds(work_t, work_y, cfg, min(128, cfg.max_proposals))
            seed_count += len(seeds)
            for seed in seeds:
                hypotheses, expanded = _grow(work_t, work_y, seed, cfg)
                branches += expanded
                for hypothesis in hypotheses:
                    ix = np.asarray(hypothesis.indices)
                    lifted = np.asarray(hypothesis.lifted)
                    if backward:
                        ix = len(t) - 1 - ix
                    for model in _compress(t, y, ix, lifted, cfg):
                        signature = tuple(model["indices"])
                        if signature not in fingerprints:
                            models.append(model)
                            fingerprints.add(signature)
    # Hypothesis trees deliberately overlap. Select track births by their net
    # explanatory gain before common ownership arbitration; letting thousands of
    # near-identical histories each steal their smallest residual fragments all.
    grown, unique = [], set()
    for model in models:
        ix = model["indices"]
        refined = _refine(t, y, ix, _predict(model, t[ix]), cfg, grow=True)
        if refined is not None and tuple(refined["indices"]) not in unique:
            unique.add(tuple(refined["indices"]))
            grown.append(refined)
    selected, available = [], np.ones(len(t), bool)
    while grown and len(selected) < cfg.max_tracks:
        utilities = []
        for model in grown:
            ix = model["indices"][available[model["indices"]]]
            residual = _wrap(y[ix] - _predict(model, t[ix]), cfg.alias_spacing_hz)
            gain = np.sum(
                cfg.association_sigma**2 - (residual / cfg.noise_sigma_hz) ** 2
            ) - _penalty(model, cfg)
            utilities.append(float(gain))
        winner = int(np.argmax(utilities))
        if utilities[winner] <= 0:
            break
        model = grown.pop(winner)
        ix = model["indices"][available[model["indices"]]]
        refined = _refine(t, y, ix, _predict(model, t[ix]), cfg, grow=False)
        if refined is not None:
            selected.append(refined)
            available[refined["indices"]] = False
    return finish_lane(
        t,
        y,
        order,
        original_count,
        selected,
        cfg,
        method="mht",
        diagnostics={
            "seed_count": seed_count,
            "measurement_branches": branches,
            "beam_width": 3,
            "directions": ["forward", "backward"],
            "seed_budget_per_direction": min(128, cfg.max_proposals),
            "horizon_s": 120,
            "seed_pair_elapsed_range_s": [1, 5],
            "initial_curvature_standard_deviation_hz_s2": 60,
            "state": ["frequency_hz", "slope_hz_s", "curvature_hz_s2"],
            "jerk_process_spectral_amplitude_hz_s_neg_2point5": max(0.5, cfg.noise_sigma_hz / 150),
            "process_covariance": "exact continuous integrated-white-jerk covariance Q(dt)",
            "search": "bidirectional_Kalman_measurement_alias_miss_beams",
            "discovery_gate": "3 innovation standard deviations, capped at "
            "6 noise sigma +300Hz/s since last measurement; final gate=3 noise sigma",
            "limitations": [
                "Bounded per-seed beam; not exact global MHT inference",
                "State-space discovery becomes polynomial only at final fit",
                "Final ownership does not retain global association histories",
            ],
        },
    )
