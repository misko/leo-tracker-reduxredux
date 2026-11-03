"""Deterministic multiscale circular Hough discovery of polynomial tracklets.

Votes accumulate in frequency/slope space; supported peaks grow into penalized
polynomial supports. Candidate selection maximizes marginal explained residual
cost. This is a bounded voting search, not RANSAC or a global optimum.
"""

import numpy as np

from leo.analysis.polynomial_tracklets import TrackConfig, _penalty, _predict, _refine, _wrap
from leo.analysis.tracklet_fitting import finish_lane, prepare_lane


def _window_peaks(t, y, reference, width, cfg):
    gate = cfg.association_sigma * cfg.noise_sigma_hz
    bins = max(16, int(np.ceil(cfg.alias_spacing_hz / (gate / 2))))
    bin_width = cfg.alias_spacing_hz / bins
    spacing = gate / width
    count = min(4097, max(3, int(np.ceil(2 * cfg.max_slope_hz_s / spacing)) + 1))
    slopes = np.linspace(-cfg.max_slope_hz_s, cfg.max_slope_hz_s, count)
    candidates = []
    for left in range(0, count, 128):
        local_slopes = slopes[left : left + 128]
        intercepts = _wrap(
            y[None, :] - local_slopes[:, None] * (t - reference), cfg.alias_spacing_hz
        )
        locations = np.floor((intercepts + cfg.alias_spacing_hz / 2) / bin_width).astype(int)
        locations %= bins
        flat = (locations + np.arange(len(local_slopes))[:, None] * bins).ravel()
        accumulator = np.bincount(flat, minlength=len(local_slopes) * bins).reshape(-1, bins)
        smoothed = accumulator + np.roll(accumulator, 1, axis=1) + np.roll(accumulator, -1, axis=1)
        # Local nonmaximum suppression retains alternatives beyond the strongest ridge.
        for _ in range(5):
            slope_index, frequency_index = np.unravel_index(np.argmax(smoothed), smoothed.shape)
            votes = int(smoothed[slope_index, frequency_index])
            if votes < cfg.min_points:
                break
            center = (frequency_index + 0.5) * bin_width - cfg.alias_spacing_hz / 2
            candidates.append((votes, float(local_slopes[slope_index]), center))
            neighbors = (frequency_index + np.arange(-2, 3)) % bins
            smoothed[max(0, slope_index - 3) : slope_index + 4, neighbors[:, None]] = 0
    chosen = []
    for votes, slope, center in sorted(candidates, reverse=True):
        if any(
            max(
                abs(_wrap(center - c + (slope - s) * edge, cfg.alias_spacing_hz))
                for edge in (-width / 2, width / 2)
            )
            < gate
            for _, s, c in chosen
        ):
            continue
        chosen.append((votes, slope, center))
        if len(chosen) >= 10:
            break
    return chosen


def _discover(t, y, cfg):
    proposals, fingerprints, window_count = [], set(), 0
    gate = cfg.association_sigma * cfg.noise_sigma_hz
    for width in (12.0, 24.0, 48.0):
        for start in np.arange(t[0], t[-1] + 0.001, width / 2):
            ix = np.flatnonzero((t >= start) & (t <= start + width))
            if len(ix) < cfg.min_points or np.ptp(t[ix]) < cfg.min_span_s:
                continue
            window_count += 1
            reference = start + width / 2
            for _, slope, center in _window_peaks(t[ix], y[ix], reference, width, cfg):
                predicted = center + slope * (t[ix] - reference)
                keep = np.abs(_wrap(y[ix] - predicted, cfg.alias_spacing_hz)) < gate
                if keep.sum() < cfg.min_points:
                    continue
                model = _refine(t, y, ix[keep], predicted[keep], cfg, grow=True)
                if model is None:
                    continue
                fingerprint = tuple(model["indices"])
                if fingerprint not in fingerprints:
                    fingerprints.add(fingerprint)
                    proposals.append(model)
    return proposals, window_count


def _select(proposals, t, y, cfg):
    current = np.full(len(t), cfg.association_sigma**2)
    candidates = []
    for model in proposals:
        cost = np.full(len(t), cfg.association_sigma**2)
        ix = model["indices"]
        residual = _wrap(y[ix] - _predict(model, t[ix]), cfg.alias_spacing_hz)
        cost[ix] = np.minimum((residual / cfg.noise_sigma_hz) ** 2, cfg.association_sigma**2)
        candidates.append((model, cost))
    selected = []
    while candidates and len(selected) < cfg.max_tracks:
        gains = [
            float(np.maximum(current - cost, 0).sum() - _penalty(model, cfg))
            for model, cost in candidates
        ]
        best = int(np.argmax(gains))
        if gains[best] <= 0:
            break
        model, cost = candidates.pop(best)
        selected.append(model)
        current = np.minimum(current, cost)
    return selected


def fit_lane(time_s, cfo_hz, config=None):
    cfg = config or TrackConfig(max_slope_hz_s=8000.0)
    t, y, order, n = prepare_lane(time_s, cfo_hz)
    if len(t) < cfg.min_points or np.ptp(t) < cfg.min_span_s:
        return finish_lane(t, y, order, n, [], cfg, "multiscale_wrapped_hough")
    proposals, windows = _discover(t, y, cfg)
    selected = _select(proposals, t, y, cfg)
    result = finish_lane(t, y, order, n, selected, cfg, "multiscale_wrapped_hough")
    # A second vote pass gives weak, previously unexplained trajectories their
    # own accumulator rather than deleting or forcing individual outliers.
    unresolved = np.flatnonzero(result["assignment"][order] < 0)
    rescue_count = 0
    if len(unresolved) >= cfg.min_points and np.ptp(t[unresolved]) >= cfg.min_span_s:
        rescue, extra_windows = _discover(t[unresolved], y[unresolved], cfg)
        windows += extra_windows
        for model in rescue:
            model["indices"] = unresolved[model["indices"]]
        rescue_count = len(rescue)
        selected = _select(proposals + rescue, t, y, cfg)
    return finish_lane(
        t,
        y,
        order,
        n,
        selected,
        cfg,
        "multiscale_wrapped_hough",
        {
            "discovery_windows": windows,
            "proposals": len(proposals),
            "rescue_proposals": rescue_count,
            "selected_proposals": len(selected),
            "window_lengths_s": [12, 24, 48],
            "maximum_peaks_per_window": 10,
            "maximum_slope_bins": 4097,
            "frequency_bin_target_hz": cfg.association_sigma * cfg.noise_sigma_hz / 2,
            "search": "deterministic accumulator peaks and marginal-cost selection",
            "limitations": [
                "finite voting grid and local refinement",
                "heuristic proposal selection",
                "conditional residual diagnostics do not establish identity",
            ],
        },
    )
