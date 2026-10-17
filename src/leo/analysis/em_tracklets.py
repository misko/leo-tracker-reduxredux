"""Independent, bounded wrapped Gaussian-mixture EM tracklet discovery.

Random local line/quadratic hypotheses initialize a mixture with a uniform
clutter component. Every E step sums neighboring integer alias branches; every
M step uses their soft responsibilities in weighted Legendre regression.
Noise scale and mixture amplitudes are fixed, so a component cannot absorb
clutter by increasing its variance. Structure changes are penalized separately.
"""

import numpy as np
from numpy.polynomial import legendre as leg

from leo.analysis.polynomial_tracklets import (
    TrackConfig,
    _best_piece,
    _bounded_slope,
    _predict,
    _refine,
    _supported,
    _wrap,
)

_TRACK_MASS = 0.15
_CLUTTER_MASS = 1.0


def _penalty(model, cfg):
    return cfg.track_penalty + (model["degree"] + 1) * np.log(max(len(model["indices"]), 2))


def _expectation(models, t, y, cfg):
    """Return observed likelihood, track weights and expected lifted CFOs."""
    n, k = len(t), len(models)
    density = np.zeros((k, n))
    target = np.zeros((k, n))
    active = np.zeros((k, n), bool)
    normalizer = np.sqrt(2 * np.pi) * cfg.noise_sigma_hz
    for j, model in enumerate(models):
        indices = model["indices"]
        active[j] = (t >= t[indices].min()) & (t <= t[indices].max())
        prediction = _predict(model, t)
        nearest = np.rint((prediction - y) / cfg.alias_spacing_hz)
        lifted = y[None, :] + (nearest[None, :] + np.arange(-1, 2)[:, None]) * (
            cfg.alias_spacing_hz
        )
        probability = np.exp(-0.5 * ((lifted - prediction) / cfg.noise_sigma_hz) ** 2)
        total = probability.sum(axis=0)
        density[j] = _TRACK_MASS * total / normalizer * active[j]
        target[j] = np.divide(
            (probability * lifted).sum(axis=0),
            total,
            out=prediction.copy(),
            where=total > 0,
        )
    numerator = _CLUTTER_MASS / cfg.alias_spacing_hz + density.sum(axis=0)
    denominator = _CLUTTER_MASS + _TRACK_MASS * active.sum(axis=0)
    likelihood = float(np.log(numerator / denominator).sum())
    responsibility = density / numerator
    return likelihood, responsibility, target


def _objective(models, t, y, cfg):
    return -2 * _expectation(models, t, y, cfg)[0] + sum(_penalty(p, cfg) for p in models)


def _weighted_step(model, weights, target, t, y, cfg):
    eligible = np.flatnonzero(weights > 0.02)
    core = np.flatnonzero(
        (weights > 0.25)
        & (
            np.abs(_wrap(y - _predict(model, t), cfg.alias_spacing_hz))
            < cfg.association_sigma * cfg.noise_sigma_hz
        )
    )
    best, cost = None, float("inf")
    if not len(eligible):
        return model
    reference, scale = model["reference_time_s"], model["time_scale_s"]
    x = (t[eligible] - reference) / scale
    for degree in range(cfg.max_degree + 1):
        if not _supported(t, core, degree, cfg):
            continue
        if weights.sum() < cfg.points_per_coefficient * (degree + 1):
            continue
        coefficients = leg.legfit(x, target[eligible], degree, w=np.sqrt(weights[eligible]))
        candidate = dict(
            indices=model["indices"].copy(),
            degree=degree,
            reference_time_s=reference,
            time_scale_s=scale,
            coefficients_hz=coefficients,
        )
        if not _bounded_slope(candidate, t, cfg):
            continue
        error = target[eligible] - _predict(candidate, t[eligible])
        value = float(
            np.sum(weights[eligible] * (error / cfg.noise_sigma_hz) ** 2)
            + (degree + 1) * np.log(max(weights.sum(), 2))
        )
        if value < cost:
            best, cost = candidate, value
    return best if best is not None else model


def _em(models, t, y, cfg, diagnostics, phase):
    """Generalized EM: accept only penalized observed-objective improvements."""
    for iteration in range(8):
        likelihood, weights, target = _expectation(models, t, y, cfg)
        before = -2 * likelihood + sum(_penalty(p, cfg) for p in models)
        candidates = [
            _weighted_step(p, weights[j], target[j], t, y, cfg) for j, p in enumerate(models)
        ]
        after = _objective(candidates, t, y, cfg)
        accepted = after <= before + 1e-8
        diagnostics["likelihood_trace"].append(
            dict(
                phase=phase,
                iteration=iteration,
                before_log_likelihood=likelihood,
                after_log_likelihood=_expectation(candidates, t, y, cfg)[0],
                before_objective=before,
                proposed_objective=after,
                accepted=accepted,
            )
        )
        if accepted:
            models = candidates
        if not accepted or before - after < 1e-4:
            break
    return models


def _seeds(t, y, cfg, available=None, seed_offset=0):
    """Discover independently of the baseline's proposal generator or fitter."""
    rng = np.random.default_rng(cfg.random_seed + seed_offset)
    available = np.ones(len(t), bool) if available is None else available
    proposals, fingerprints = [], set()
    for width in (12.0, 16.0, 24.0, 32.0, 48.0, 64.0, 96.0):
        for left in np.arange(t[0], t[-1] + 0.001, width / 2):
            local = np.flatnonzero(available & (t >= left) & (t <= left + width))
            if len(local) < cfg.min_points or np.ptp(t[local]) < cfg.min_span_s:
                continue
            seeds = []
            trials = min(cfg.seed_trials, 96)
            for trial in range(trials):
                count = 3 if trial % 3 == 0 and cfg.max_degree >= 2 else 2
                sample = np.sort(rng.choice(local, count, replace=False))
                ts = t[sample]
                if np.min(np.diff(ts)) < 0.4 or np.ptp(ts) < 2:
                    continue
                delta = _wrap(y[sample[1]] - y[sample[0]], cfg.alias_spacing_hz)
                max_branch = int(
                    np.ceil(cfg.max_slope_hz_s * (ts[1] - ts[0]) / cfg.alias_spacing_hz)
                )
                for branch in range(-max_branch, max_branch + 1):
                    slope = (delta + branch * cfg.alias_spacing_hz) / (ts[1] - ts[0])
                    if abs(slope) > cfg.max_slope_hz_s:
                        continue
                    prediction = y[sample[0]] + slope * (t[local] - ts[0])
                    if count == 3:
                        initial = y[sample[0]] + slope * (ts - ts[0])
                        lifted = initial + _wrap(y[sample] - initial, cfg.alias_spacing_hz)
                        coefficients = np.polynomial.polynomial.polyfit(ts - ts[0], lifted, 2)
                        prediction = np.polynomial.polynomial.polyval(
                            t[local] - ts[0], coefficients
                        )
                    residual = _wrap(y[local] - prediction, cfg.alias_spacing_hz)
                    keep = np.abs(residual) < cfg.association_sigma * cfg.noise_sigma_hz
                    if keep.sum() >= cfg.min_points:
                        seeds.append((int(keep.sum()), local[keep], prediction[keep]))
            for _, indices, prediction in sorted(seeds, key=lambda s: -s[0])[:5]:
                model = _refine(t, y, indices, prediction, cfg)
                if model is None:
                    continue
                key = tuple(model["indices"])
                if key not in fingerprints:
                    proposals.append(model)
                    fingerprints.add(key)

    def score(model):
        indices = model["indices"]
        residual = _wrap(y[indices] - _predict(model, t[indices]), cfg.alias_spacing_hz)
        return float(
            np.sum(cfg.association_sigma**2 - (residual / cfg.noise_sigma_hz) ** 2)
            - _penalty(model, cfg)
        )

    proposals.sort(key=lambda p: -score(p))
    return proposals[: cfg.max_proposals]


def _initial_mixture(proposals, t, y, cfg):
    """Fast penalized coverage initialization before observed-likelihood EM."""
    models = []
    cost = np.full(len(t), cfg.association_sigma**2)
    for proposal in proposals:
        indices = proposal["indices"]
        residual = _wrap(y[indices] - _predict(proposal, t[indices]), cfg.alias_spacing_hz)
        candidate = np.minimum((residual / cfg.noise_sigma_hz) ** 2, cfg.association_sigma**2)
        gain = float(np.maximum(cost[indices] - candidate, 0).sum() - _penalty(proposal, cfg))
        if gain > 0:
            models.append(proposal)
            cost[indices] = np.minimum(cost[indices], candidate)
        if len(models) >= cfg.max_tracks:
            break
    return models


def _prune(models, t, y, cfg, diagnostics):
    index = 0
    while index < len(models):
        current = _objective(models, t, y, cfg)
        candidate = models[:index] + models[index + 1 :]
        value = _objective(candidate, t, y, cfg)
        if value <= current:
            diagnostics["structure_changes"].append(
                dict(
                    operation="delete",
                    before_objective=current,
                    after_objective=value,
                )
            )
            models = candidate
        else:
            index += 1
    return models


def _merge(models, t, y, cfg, diagnostics):
    """Consolidate duplicate soft components with an observed-MDL comparison."""
    for _ in range(2):
        changed = False
        current = _objective(models, t, y, cfg)
        attempts = 0
        for i, left in enumerate(models):
            for j in range(i + 1, len(models)):
                right = models[j]
                low = max(t[left["indices"]].min(), t[right["indices"]].min())
                high = min(t[left["indices"]].max(), t[right["indices"]].max())
                if high - low < cfg.min_span_s:
                    continue
                sample = np.linspace(low, high, 5)
                difference = np.abs(
                    _wrap(
                        _predict(left, sample) - _predict(right, sample),
                        cfg.alias_spacing_hz,
                    )
                )
                if np.max(difference) > 2 * cfg.association_sigma * cfg.noise_sigma_hz:
                    continue
                attempts += 1
                if attempts > 32:
                    break
                indices = np.union1d(left["indices"], right["indices"])
                if np.max(np.diff(t[indices])) > cfg.max_gap_s:
                    continue
                prediction = _predict(left, t[indices])
                use_right = np.isin(indices, right["indices"])
                offset = (
                    np.round(
                        (
                            _predict(left, np.array([(low + high) / 2]))[0]
                            - _predict(right, np.array([(low + high) / 2]))[0]
                        )
                        / cfg.alias_spacing_hz
                    )
                    * cfg.alias_spacing_hz
                )
                prediction[use_right] = _predict(right, t[indices[use_right]]) + offset
                merged = _best_piece(t, y, indices, prediction, cfg)
                if merged is None:
                    continue
                merged = _refine(t, y, indices, _predict(merged, t[indices]), cfg, grow=False)
                if merged is None or len(merged["indices"]) < 0.9 * len(indices):
                    continue
                candidate = [p for k, p in enumerate(models) if k not in (i, j)] + [merged]
                value = _objective(candidate, t, y, cfg)
                if value < current:
                    diagnostics["structure_changes"].append(
                        dict(
                            operation="merge",
                            before_objective=current,
                            after_objective=value,
                        )
                    )
                    models, changed = candidate, True
                    break
            if changed or attempts > 32:
                break
        if not changed:
            break
    return models


def fit_lane(time_s, cfo_hz, config: TrackConfig | None = None):
    """Discover a time-gated wrapped mixture; retain every input row in output."""
    from leo.analysis.tracklet_fitting import finish_lane, prepare_lane

    cfg = config or TrackConfig()
    t, y, order, n_original = prepare_lane(time_s, cfo_hz)
    diagnostics = dict(
        likelihood_trace=[],
        structure_changes=[],
        fixed_noise_sigma_hz=cfg.noise_sigma_hz,
        fixed_track_mass=_TRACK_MASS,
        fixed_clutter_mass=_CLUTTER_MASS,
        alias_branches_per_observation=3,
        initialization="independent_random_line_quadratic",
        limitations=[
            "local generalized EM optimum",
            "fixed mixture amplitudes",
            "birth search and final shared hard refit are outside conditional EM",
        ],
    )
    if len(t) < cfg.min_points or np.ptp(t) < cfg.min_span_s:
        return finish_lane(t, y, order, n_original, [], cfg, "wrapped_em", diagnostics)
    proposals = _seeds(t, y, cfg)
    diagnostics["initial_proposals"] = len(proposals)
    models = _initial_mixture(proposals, t, y, cfg)
    models = _em(models, t, y, cfg, diagnostics, "initial")
    models = _prune(models, t, y, cfg, diagnostics)
    # Unexplained-data births are independent new hypotheses. All accepted
    # births improve the penalized observed likelihood on the full lane.
    _, weights, _ = _expectation(models, t, y, cfg)
    uncovered = weights.max(axis=0) < 0.5 if len(models) else np.ones(len(t), bool)
    extra = _seeds(t, y, cfg, uncovered, 107) if uncovered.sum() >= cfg.min_points else []
    diagnostics["uncovered_proposals"] = len(extra)
    candidates = proposals + extra
    for proposal in candidates:
        if len(models) >= cfg.max_tracks:
            break
        current = _objective(models, t, y, cfg)
        value = _objective(models + [proposal], t, y, cfg)
        if value < current:
            diagnostics["structure_changes"].append(
                dict(
                    operation="birth",
                    before_objective=current,
                    after_objective=value,
                )
            )
            models.append(proposal)
    models = _em(models, t, y, cfg, diagnostics, "after_births")
    models = _prune(models, t, y, cfg, diagnostics)
    models = _merge(models, t, y, cfg, diagnostics)
    models = _em(models, t, y, cfg, diagnostics, "after_merges")
    diagnostics["conditional_updates_monotonic"] = all(
        row["proposed_objective"] <= row["before_objective"] + 1e-8
        for row in diagnostics["likelihood_trace"]
        if row["accepted"]
    )
    diagnostics["monotonicity_metric"] = "negative_twice_observed_log_likelihood_plus_MDL"
    diagnostics["conditional_log_likelihood_monotonic"] = all(
        row["after_log_likelihood"] >= row["before_log_likelihood"] - 1e-8
        for row in diagnostics["likelihood_trace"]
        if row["accepted"]
    )
    diagnostics["pre_finalization_penalized_objective"] = _objective(models, t, y, cfg)
    diagnostics["pre_finalization_components"] = len(models)
    # Convert the soft mixture to disjoint candidate memberships under the
    # common residual gate. This hard reporting step is separate from EM's
    # likelihood trace; the shared finalizer applies support and noise checks.
    if models:
        distance = np.full((len(models), len(t)), np.inf)
        for j, model in enumerate(models):
            indices = model["indices"]
            active = (t >= t[indices].min()) & (t <= t[indices].max())
            distance[j, active] = np.abs(
                _wrap(y[active] - _predict(model, t[active]), cfg.alias_spacing_hz)
            )
        owner = np.argmin(distance, axis=0)
        owner[
            distance[owner, np.arange(len(t))] >= (cfg.association_sigma * cfg.noise_sigma_hz)
        ] = -1
        models = [dict(model, indices=np.flatnonzero(owner == j)) for j, model in enumerate(models)]
    return finish_lane(t, y, order, n_original, models, cfg, "wrapped_em", diagnostics)
