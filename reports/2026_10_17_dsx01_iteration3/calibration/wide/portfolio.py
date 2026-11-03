"""Nine prior-scaled geography seeds, current training-only band calibration.

Every seed uses zero satellite timing, clocks, q coefficients and RF coefficient.
All selection is by the same masked training objective. Evaluation references
and held CFO are absent from this module's input access.
"""
from dataclasses import replace
import time
from types import SimpleNamespace

import numpy as np

from causal_calibration import current_seed


def prior_grid(prior):
    half = float(prior.radius_km)/2
    return np.asarray([(east, north) for east in (-half, 0., half)
        for north in (-half, 0., half)])


def fit(context, donor=None, *, use_donor=False, max_evaluations=1000, max_seconds=120):
    from common import refit
    from leo.application.channel_group_refinement import objective
    from leo.analysis.channel_group_calibration import GroupCalibrationObjective, group_frame
    from leo.analysis.shared_scan_model import SmoothVisibilityModel, SharedScanObjective, donor_state

    if max_evaluations < 40 or not np.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError('Prior-grid portfolio requires >=40 scores and positive finite seconds')
    begun = time.monotonic()
    deadline = min(begun+max_seconds, context.deadline)
    obs, mask = context.observations, np.asarray(context.train_mask, bool)
    ordinary = objective(SimpleNamespace(observations=obs), context.bank, context.prior, context.nodes)
    frame = group_frame(obs.receiver[mask], obs.channel[mask] >= 5)
    if set(frame.receivers) != set(obs.receiver):
        raise ValueError('Every receiver needs both bands in training rows')
    joint = GroupCalibrationObjective(ordinary.base, obs.channel >= 5, frame=frame)
    joint.score = context.model.score
    free = SmoothVisibilityModel(joint, mask)
    seeds = []
    full_calls = partial_calls = 0
    partial_allowance = max(2, min(20, (max_evaluations-20)//18))
    for index, point in enumerate(prior_grid(context.prior)):
        v, nbase, seed = current_seed(joint, obs, mask, context.bank, context.prior,
            donor=donor, use_donor=use_donor, maximum_partial_scores=partial_allowance,
            deadline=begun+.3*max_seconds, point_km=point)
        n = np.r_[nbase, np.zeros(free.observation_parameter_count)]
        ev = free.evaluate_joint(v, n)
        full_calls += 1
        partial_calls += seed['partial_density_evaluations']
        seeds.append(dict(index=index, point_km=point.tolist(), vector=v, nuisance=n,
            objective=float(ev[0]), seed=seed))
    ranked = sorted(seeds, key=lambda row: (row['objective'], row['index']))
    best = dict(vector=ranked[0]['vector'], nuisance=ranked[0]['nuisance'],
        diagnostics=dict(objective=ranked[0]['objective'], accepted=False, stationarity=None,
            reason='Best initial seed; no refinement yet', evaluations=0))
    selected_seed = ranked[0]['index']
    refinements = []
    # Preserve two evaluations for exact physical/objective freeze closure.
    available = max_evaluations-full_calls-partial_calls-2
    refinement_cap = min(200, max(1, available//4))
    fit_deadline = deadline-min(2., .1*max_seconds)
    for rank, seed in enumerate(ranked[:3]):
        if time.monotonic() >= fit_deadline:
            break
        temporary = replace(context, model=free, full_model=free,
            vector=seed['vector'], nuisance=seed['nuisance'], deadline=fit_deadline)
        seconds = max(.001, (fit_deadline-time.monotonic())/(4-rank))
        solved = refit(temporary, seed['vector'], seed['nuisance'],
            max_evaluations=refinement_cap, max_seconds=seconds, fixed_c=context.fixed_c)
        full_calls += int(solved['diagnostics']['evaluations'])
        refinements.append(dict(seed_index=seed['index'], diagnostics=solved['diagnostics']))
        if solved['diagnostics']['objective'] <= best['diagnostics']['objective']:
            best, selected_seed = solved, seed['index']
    remaining = max_evaluations-full_calls-partial_calls-2
    polish = None
    if remaining >= 1 and time.monotonic() < fit_deadline:
        temporary = replace(context, model=free, full_model=free,
            vector=best['vector'], nuisance=best['nuisance'], deadline=fit_deadline)
        polished = refit(temporary, best['vector'], best['nuisance'],
            max_evaluations=remaining, max_seconds=fit_deadline-time.monotonic(),
            fixed_c=context.fixed_c)
        full_calls += int(polished['diagnostics']['evaluations'])
        polish = polished['diagnostics']
        if polish['objective'] <= best['diagnostics']['objective']:
            best = polished
    vv, nn = best['vector'], best['nuisance']
    raw, shift, v, clock, closure = donor_state(joint,
        dict(vector=vv, nuisance=nn[:free.base_nuisance_count]))
    raw.score = free.score
    shared, full = SharedScanObjective(raw, shift, mask=mask), SharedScanObjective(raw, shift)
    n = np.r_[clock, nn[free.base_nuisance_count:]]
    before, after = free.evaluate_details(vv, nn)[0], shared.evaluate_details(v, n)[0]
    full_calls += 2
    error = max(abs(before[0]-after[0]), abs(before[3].nll-after[3].nll),
        np.max(abs(before[3].residual_hz-after[3].residual_hz), initial=0))
    if max(error, closure) >= 1e-7:
        raise ValueError('Nine-point portfolio freeze failed exact closure')
    trained = replace(context, model=shared, full_model=full, vector=v, nuisance=n)
    diag = dict(policy='nine deterministic prior-disk nodes; train-J selection only',
        donor_used=bool(use_donor and donor and donor.get('available')),
        donor_available=bool(donor and donor.get('available')),
        prior_radius_km=float(context.prior.radius_km), grid_points_km=prior_grid(context.prior).tolist(),
        seed_objectives=[dict(index=row['index'], point_km=row['point_km'],
            objective=row['objective'], seed=row['seed']) for row in seeds],
        ranked_seed_indices=[row['index'] for row in ranked], selected_seed_index=selected_seed,
        refinements=refinements, polish=polish, endpoint=best['diagnostics'],
        evaluations=full_calls+partial_calls, full_objective_evaluations=full_calls,
        partial_density_evaluations=partial_calls, seed_orbit_projection_calls=len(seeds),
        max_evaluations=int(max_evaluations), max_seconds=float(max_seconds),
        elapsed_seconds=float(time.monotonic()-begun),
        learned_offsets_hz=np.asarray(shift.offsets_hz).tolist(),
        receiver_slopes_hz_s=[float(v[3]), float(v[5])], fixed_c=bool(context.fixed_c),
        correction_transport_max_hz=float(closure), masked_objective_closure_error=float(error),
        accepted=bool(best['diagnostics'].get('accepted', False)),
        prior_policy='Original physical likelihood and 50kHz band prior; donor initializer only',
        qualification='Training-only candidate-conditioned inference; finite-grid local optimization; configured positions never read for initialization.')
    return trained, diag
