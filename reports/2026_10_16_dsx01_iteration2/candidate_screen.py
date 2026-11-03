"""Bounded, training-only omitted-candidate screen on the original regional bank.

This is a one-addition density/novelty surrogate, not a joint expanded fit or
verified identity classifier. There are no dataset-specific IDs or windows.
"""

import math
import time

import numpy as np

MAX_ROWS = 1024


def timing_penalty(tau, score):
    tau = np.asarray(tau, float)
    mean = tau.mean(axis=0)
    return .5*(mean/score.common_sigma_s)**2 + .5*np.sum(
        ((tau-mean)/score.relative_sigma_s)**2, axis=0)


def prediction_weight(bank, obs, prior, point, shifts, width):
    """Existing native orbital equations and exact compact-horizon weights."""
    from leo.analysis.hard60_score import predict_orbits
    from leo.analysis.regional_position_score import observer
    from leo.analysis.shared_scan_model import horizon_weight

    prediction = predict_orbits(bank, obs, prior, point, shifts, derivatives=False)[0]
    query = obs.times_s[:, None]+np.asarray(shifts)[None, :]
    frac = (query-bank.nodes_s[0])/(bank.nodes_s[1]-bank.nodes_s[0])
    lower = np.minimum(np.floor(frac).astype(int), len(bank.nodes_s)-2)
    satellite = np.arange(len(bank.numbers))[None, :]
    position = bank.position_km[satellite, lower]
    position = position+(frac-lower)[..., None]*(bank.position_km[satellite, lower+1]-position)
    site, up = observer(prior, point)
    delta = position-site
    sine = np.einsum('nki,i->nk', delta, up)/np.linalg.norm(delta, axis=2)
    return prediction, horizon_weight(sine, width)[0]


def greedy_select(rows, positive_gains, *, max_additions, scale=1.):
    """Choose novel positive per-row density improvements, deterministic ties."""
    covered = np.zeros(positive_gains.shape[1])
    chosen, remaining = [], set(range(len(rows)))
    for _ in range(max_additions):
        ranked = []
        for i in remaining:
            if rows[i]['gain'] <= 0:
                continue
            novel = float(np.maximum(positive_gains[i]-covered, 0).sum()*scale)
            marginal = novel-max(0., rows[i]['timing_prior_delta'])
            if marginal > 0 and novel > 0:
                ranked.append((-marginal, int(rows[i]['number']), i, novel))
        if not ranked:
            break
        negative, _, i, novel = min(ranked)
        chosen.append(dict(number=int(rows[i]['number']), marginal_gain=-negative,
                           new_positive_row_gain=novel))
        covered = np.maximum(covered, positive_gains[i])
        remaining.remove(i)
    return chosen


def screen(context, regional, max_additions=8, max_seconds=60):
    from leo.analysis.regional_position_bootstrap import observation_subset
    from leo.analysis.regional_position_score import ALIAS_HZ, circular

    if (type(max_additions) is not int or not 0 <= max_additions <= 8
            or not math.isfinite(max_seconds) or not 0 < max_seconds <= 60):
        raise ValueError('declared <=8 candidates and <=60-second screen required')
    if context.fixed_c:
        raise ValueError('screen once on fitted-c training, reuse the same IDs in both RF arms')
    begun = time.monotonic()
    deadline = min(begun+max_seconds, getattr(context, 'deadline', math.inf))
    model, v, n = context.model, np.asarray(context.vector), np.asarray(context.nuisance)
    mask = np.asarray(context.train_mask)
    if mask.dtype != bool or mask.shape != context.observations.times_s.shape or not mask.any():
        raise ValueError('nonempty explicit training mask required')
    np.testing.assert_array_equal(mask, model.mask)
    training = np.flatnonzero(mask)
    selected = training[np.linspace(0, len(training)-1, min(MAX_ROWS, len(training)), dtype=int)]
    obs = observation_subset(context.observations, selected)
    scale = len(training)/len(selected)
    existing = list(map(int, context.bank.numbers))
    lookup = {int(number): i for i, number in enumerate(regional.numbers)}
    if not set(existing) <= set(lookup):
        raise ValueError('original candidates missing from regional bank')
    for name in ('numbers', 'nodes_s', 'position_km', 'velocity_km_s'):
        old = regional.select([lookup[number] for number in existing])
        np.testing.assert_array_equal(getattr(old, name), getattr(context.bank, name))
    omitted = sorted(set(lookup)-set(existing))
    diagnostics = dict(schema='dsx-omitted-candidate-screen-v1', source_id=context.source_id,
        maximum_seconds=max_seconds, maximum_additions=max_additions,
        scope='fitted-c training-selected candidate inventory reused for both RF arms',
        row_policy='all training if <=1024, otherwise deterministic uniform original row indices',
        full_training_rows=len(training), scored_rows=len(selected), row_scale=scale,
        row_indices=selected.tolist(), window_ids=list(obs.window_ids),
        objective_calls=0, localization_fits=0, bounded_q_projections=0,
        surrogate='one-added conditional CFO density plus exact expanded timing prior; '
            'greedy positive per-row gain envelope, not a joint multi-addition fit',
        q_policy='old q*K/(K+1), new q=budget/(K+1), no bounded-logit projection during screening',
        existing_numbers=existing, omitted_count=len(omitted), predictor_calls=0,
        coarse_step_s=1., fine_step_s=.05, fine_half_width_s=1.)
    if not omitted or max_additions == 0 or time.monotonic() >= deadline:
        diagnostics.update(state='empty-or-expired', selected=[], candidates=[],
                           elapsed_seconds=time.monotonic()-begun)
        return [], diagnostics
    additions = regional.select([lookup[number] for number in omitted])
    correction = model.original.correction(v, n[:model.clock_count])[selected]
    tau = v[7]+model.basis@v[8:]
    old_prediction, old_weight = prediction_weight(context.bank, obs, context.prior,
        v[:2], tau, model.visibility_width)
    diagnostics['predictor_calls'] += 1
    residual = circular(obs.measured_hz[:, None]-correction[:, None]-old_prediction)
    gaussian = np.exp(-.5*(residual/model.score.sigma_hz)**2)/(
        model.score.sigma_hz*np.sqrt(2*np.pi))
    q = model.hyperparameters(n[model.base_nuisance_count:])[2]
    odds = q*old_weight/(1-q*old_weight)
    original_rows = np.log(model.score.clutter_rate+odds.sum(axis=1))-np.log(
        model.score.clutter_rate/ALIAS_HZ+(odds*gaussian).sum(axis=1))
    scaled = q*len(q)/(len(q)+1)
    old_odds = scaled*old_weight/(1-scaled*old_weight)
    denominator = model.score.clutter_rate/ALIAS_HZ+(old_odds*gaussian).sum(axis=1)
    normalizer = model.score.clutter_rate+old_odds.sum(axis=1)
    scaled_rows = np.log(normalizer)-np.log(denominator)
    old_maximum_signal = (old_odds*gaussian).max(axis=1)
    lower = max(-20., float(additions.nodes_s[0]-obs.times_s.min()))
    upper = min(20., float(additions.nodes_s[-1]-obs.times_s.max()))
    coarse = np.arange(math.ceil(lower), math.floor(upper)+.5, 1.)
    if not len(coarse):
        raise ValueError('no original feasible interpolation/timing grid')
    count = len(omitted)
    best = np.full(count, -np.inf)
    best_tau = np.zeros(count)
    best_data, best_prior = np.zeros(count), np.zeros(count)
    support, map_support = np.zeros(count, int), np.zeros(count, int)
    positive = np.zeros((count, len(selected)))
    coarse_profiles, fine_profiles = [], []
    original_penalty = float(timing_penalty(tau, model.score))

    def evaluate(shifts):
        prediction, weight = prediction_weight(additions, obs, context.prior,
            v[:2], shifts, model.visibility_width)
        diagnostics['predictor_calls'] += 1
        r = circular(obs.measured_hz[:, None]-correction[:, None]-prediction)
        added_q = model.score.detection_budget/(len(q)+1)
        added_odds = added_q*weight/(1-added_q*weight)
        signal = added_odds*np.exp(-.5*(r/model.score.sigma_hz)**2)/(
            model.score.sigma_hz*np.sqrt(2*np.pi))
        rows = np.log(normalizer[:, None]+added_odds)-np.log(denominator[:, None]+signal)
        data_gain = np.sum(original_rows[:, None]-rows, axis=0)*scale
        expanded_mean = (tau.sum()+shifts)/(len(tau)+1)
        relative_squares = (tau@tau+shifts**2)-(len(tau)+1)*expanded_mean**2
        penalty = .5*(expanded_mean/model.score.common_sigma_s)**2
        penalty += .5*relative_squares/model.score.relative_sigma_s**2
        prior_delta = penalty-original_penalty
        gain = data_gain-prior_delta
        improved = gain > best
        best[improved], best_tau[improved] = gain[improved], shifts[improved]
        best_data[improved], best_prior[improved] = data_gain[improved], prior_delta[improved]
        positive[improved] = np.maximum(scaled_rows[:, None]-rows, 0)[:, improved].T
        support[improved] = (signal[:, improved] > model.score.clutter_rate/ALIAS_HZ).sum(axis=0)
        map_support[improved] = (signal[:, improved] > np.maximum(
            old_maximum_signal[:, None], model.score.clutter_rate/ALIAS_HZ)).sum(axis=0)
        return gain

    for shift in coarse:
        if time.monotonic() >= deadline:
            break
        shifts = np.full(count, shift)
        coarse_profiles.append((shift, evaluate(shifts).tolist()))
    coarse_complete = len(coarse_profiles) == len(coarse)
    center = best_tau.copy()
    fine = np.arange(-1., 1.001, .05)
    if coarse_complete:
        for offset in fine:
            if time.monotonic() >= deadline:
                break
            # Endpoint repetitions are explicit bounded-grid points, not a
            # changed physical timing bound or an optimizer-state projection.
            shifts = np.minimum(upper, np.maximum(lower, center+offset))
            fine_profiles.append((float(offset), shifts.tolist(), evaluate(shifts).tolist()))
    rows = []
    for i, number in enumerate(omitted):
        rows.append(dict(number=number, best_timing_s=float(best_tau[i]),
            gain=float(best[i]) if np.isfinite(best[i]) else None,
            data_gain=float(best_data[i]), timing_prior_delta=float(best_prior[i]),
            new_signal_above_clutter_rows=int(support[i]), new_map_signal_rows=int(map_support[i]),
            coarse_profile=[[float(t), gains[i]] for t, gains in coarse_profiles],
            fine_profile=[[shifts[i], gains[i]] for _, shifts, gains in fine_profiles]))
    chosen = greedy_select(rows, positive, max_additions=max_additions, scale=scale) \
        if coarse_complete and time.monotonic() < deadline else []
    for row in chosen:
        i = omitted.index(row['number'])
        keep = positive[i] > 0
        row.update(positive_gain_original_rows=selected[keep].tolist(),
                   positive_gain_values=positive[i, keep].tolist())
    diagnostics.update(state='complete' if len(fine_profiles) == len(fine) else 'partial-deadline',
        coarse_complete=coarse_complete, coarse_points=len(coarse_profiles),
        fine_points=len(fine_profiles),
        candidate_timing_evaluations=count*(len(coarse_profiles)+len(fine_profiles)),
        selected=chosen, candidates=sorted(rows, key=lambda r: (
            -r['gain'] if r['gain'] is not None else math.inf, r['number'])),
        elapsed_seconds=time.monotonic()-begun)
    return [row['number'] for row in chosen], diagnostics
