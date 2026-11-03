"""Causal donor-band seed, current training-only joint calibration and freeze.

Only donor band differences are carried. Geography, timing, RF coefficient,
clocks and q start neutral; common receiver intercepts/slopes use current train
rows. Donor and no-donor arms retain the same free physical columns and priors.
"""
from dataclasses import replace
import time
from types import SimpleNamespace

import numpy as np
from scipy.ndimage import gaussian_filter1d

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import ALIAS_HZ, circular


def subset(obs, mask):
    rows = np.flatnonzero(mask)
    return replace(obs, window_ids=tuple(obs.window_ids[i] for i in rows),
        **{key: getattr(obs, key)[rows] for key in
        ('times_s', 'measured_hz', 'rf_hz', 'receiver', 'channel', 'margin')})


def histogram(values, weights, bins=1024):
    index = np.floor((circular(values) + ALIAS_HZ/2) * bins/ALIAS_HZ).astype(int) % bins
    counts = np.bincount(index.ravel(), weights=np.broadcast_to(weights, values.shape).ravel(),
        minlength=bins)
    return gaussian_filter1d(counts, 1.5, mode='wrap')


def paired_band_seed(obs, residual, visible, receivers):
    """No-donor fallback: a single shared delta votes over near-time band pairs.

    Both residuals use the SAME eligible satellite column and their actual RF.
    This avoids subtracting independently selected low/high histogram modes.
    It is proposal evidence, not satellite truth or an added fitted frequency.
    """
    offsets, diagnostics = [], []
    for rx in receivers:
        low = np.flatnonzero((obs.receiver == rx) & (obs.channel < 5))
        high = np.flatnonzero((obs.receiver == rx) & (obs.channel >= 5))
        low = low[np.argsort(obs.times_s[low], kind='stable')]
        if not len(low) or not len(high):
            raise ValueError('Both bands need current training support')
        where = np.searchsorted(obs.times_s[low], obs.times_s[high])
        a, b = low[np.clip(where-1, 0, len(low)-1)], low[np.clip(where, 0, len(low)-1)]
        use_a = abs(obs.times_s[high]-obs.times_s[a]) <= abs(obs.times_s[high]-obs.times_s[b])
        partner = np.where(use_a, a, b)
        keep = abs(obs.times_s[high]-obs.times_s[partner]) <= 2.
        h, l = high[keep], partner[keep]
        if not len(h):
            raise ValueError('No <=2 second training low/high pairs for fallback')
        visibility = visible[h] & visible[l]
        weights = visibility / np.maximum(visibility.sum(axis=1, keepdims=True), 1)
        hist = histogram(circular(residual[h]-residual[l]), weights)
        peak = int(np.argmax(hist))
        delta = float(circular((peak+.5)*ALIAS_HZ/len(hist)-ALIAS_HZ/2))
        offsets.append(delta)
        diagnostics.append(dict(receiver=int(rx), pairs=int(len(h)),
            inferred_delta_hz=delta, peak_vote=float(hist[peak])))
    return np.asarray(offsets), diagnostics


def current_seed(joint, obs, mask, bank, prior, *, donor=None, use_donor=True,
                 maximum_partial_scores=50, deadline=float('inf'), point_km=None):
    train = subset(obs, mask)
    point = np.zeros(2) if point_km is None else np.asarray(point_km, float)
    if point.shape != (2,) or not np.isfinite(point).all() or np.linalg.norm(point) > prior.radius_km:
        raise ValueError('Initializer point must be finite and inside the declared regional prior')
    predicted, visible, _, _ = predict_orbits(bank, train, prior,
        point, np.zeros(len(bank.numbers)), derivatives=False)
    residual = circular(train.measured_hz[:, None]-predicted)
    weights = visible / np.maximum(visible.sum(axis=1, keepdims=True), 1)
    available = bool(donor and donor.get('available'))
    if use_donor and available:
        band = donor['donor']['band']
        lookup = dict(zip(band['receivers'], band['offsets_hz'], strict=True))
        offsets = np.array([lookup[rx] for rx in joint.frame.receivers])
        delta_diagnostics = []
        policy = 'causally completed same-hardware/stream-family/actual-RF donor band differences only'
    else:
        offsets, delta_diagnostics = paired_band_seed(train, residual, visible, joint.frame.receivers)
        policy = 'training-only same-candidate near-time low/high paired-residual histogram'
    vector = np.zeros(joint.size)
    vector[:2] = point
    nuisance = np.asarray(joint.initial_nuisance).copy()
    centered = train.times_s-obs.time_center_s
    q = joint.score.detection_budget/len(bank.numbers)
    clutter = joint.score.clutter_rate/ALIAS_HZ
    score_count = 0
    receivers = []
    per_rx = max(1, maximum_partial_scores//max(1, len(joint.frame.receivers)))
    slopes = (0., -30., 30., -60., 60.)[:max(1, min(5, per_rx//2))]
    peaks_per_slope = max(1, min(2, per_rx//len(slopes)))
    for index, (rx, fraction) in enumerate(zip(joint.frame.receivers, joint.frame.high_fractions, strict=True)):
        delta = float(circular(offsets[index]))
        lane = train.receiver == rx
        high = train.channel >= 5
        adjusted = circular(residual - delta*high[:, None])
        best = None
        for slope in slopes:
            if best is not None and time.monotonic() >= deadline:
                break
            slope_adjusted = circular(adjusted-slope*centered[:, None])
            low_hist = histogram(slope_adjusted[lane & ~high], weights[lane & ~high]) / max(1, int(np.sum(lane & ~high)))
            high_hist = histogram(slope_adjusted[lane & high], weights[lane & high]) / max(1, int(np.sum(lane & high)))
            # One intercept must have support in both bands at the shared delta.
            profile = np.sqrt(low_hist*high_hist)
            for _ in range(peaks_per_slope):
                peak = int(np.argmax(profile))
                offset = float((peak+.5)*ALIAS_HZ/len(profile)-ALIAS_HZ/2)
                rr = circular(slope_adjusted[lane]-offset)
                signal = np.exp(-.5*(rr/125.)**2)*visible[lane]
                density = clutter + q/(1-q)*signal.sum(axis=1)/(125.*np.sqrt(2*np.pi))
                score = -float(np.log(density).sum())
                score_count += 1
                if best is None or score < best[0]:
                    best = (score, offset, slope)
                profile[(peak+np.arange(-4, 5)) % len(profile)] = -1.
        if best is None:
            raise ValueError('No training receiver seed evaluated')
        score, low_offset, slope = best
        vector[2+2*rx] = low_offset+fraction*delta
        vector[3+2*rx] = slope
        nuisance[joint.clock_count+index] = delta
        receivers.append(dict(receiver=int(rx), low_offset_hz=low_offset,
            band_delta_seed_hz=delta, centered_intercept_hz=float(vector[2+2*rx]),
            slope_seed_hz_s=slope, partial_training_nll=score,
            training_high_fraction=float(fraction)))
    return vector, nuisance, dict(policy=policy, donor_available=available,
        donor_used=bool(use_donor and available), receivers=receivers,
        fallback_paired_delta=delta_diagnostics, partial_density_evaluations=score_count,
        orbit_projection_calls=1, training_rows=int(mask.sum()),
        accounting='Each partial RX density score conservatively charged as one full objective evaluation')


def bootstrap(context, donor=None, *, use_donor=True, max_evaluations=400, max_seconds=60):
    from common import refit
    from leo.application.channel_group_refinement import objective
    from leo.analysis.channel_group_calibration import GroupCalibrationObjective, group_frame
    from leo.analysis.shared_scan_model import SmoothVisibilityModel, SharedScanObjective, donor_state

    if max_evaluations < 8 or max_seconds <= 0:
        raise ValueError('Positive wall allowance and >=8 total score evaluations required')
    begun = time.monotonic()
    deadline = min(begun+max_seconds, context.deadline)
    obs, mask = context.observations, np.asarray(context.train_mask, bool)
    if mask.shape != obs.times_s.shape or not mask.any():
        raise ValueError('Nonempty full-domain training mask required')
    ordinary = objective(SimpleNamespace(observations=obs), context.bank, context.prior, context.nodes)
    frame = group_frame(obs.receiver[mask], obs.channel[mask] >= 5)
    if set(frame.receivers) != set(obs.receiver):
        raise ValueError('Every receiver needs training observations in both bands')
    joint = GroupCalibrationObjective(ordinary.base, obs.channel >= 5, frame=frame)
    joint.score = context.model.score
    free = SmoothVisibilityModel(joint, mask)
    vector, base_nuisance, seed = current_seed(joint, obs, mask, context.bank,
        context.prior, donor=donor, use_donor=use_donor,
        maximum_partial_scores=max(2, max_evaluations//8), deadline=begun+.2*max_seconds)
    nuisance = np.r_[base_nuisance, np.zeros(free.observation_parameter_count)]
    initial_objective = float(free.evaluate_joint(vector, nuisance)[0])
    charged = seed['partial_density_evaluations']+3
    fit_deadline = deadline-min(2., .1*max_seconds)
    temporary = replace(context, model=free, full_model=free, vector=vector,
        nuisance=nuisance, deadline=fit_deadline)
    if time.monotonic() < fit_deadline:
        fitted = refit(temporary, vector, nuisance, max_evaluations=max_evaluations-charged,
            max_seconds=fit_deadline-time.monotonic(), fixed_c=context.fixed_c)
    else:
        fitted = dict(vector=vector, nuisance=nuisance, diagnostics=dict(evaluations=0,
            accepted=False, stationarity=None, objective=initial_objective,
            reason='Seed consumed wall allowance'))
    vv, nn = fitted['vector'], fitted['nuisance']
    raw, shift, v, clock, closure = donor_state(joint,
        dict(vector=vv, nuisance=nn[:free.base_nuisance_count]))
    raw.score = free.score
    shared, full = SharedScanObjective(raw, shift, mask=mask), SharedScanObjective(raw, shift)
    n = np.r_[clock, nn[free.base_nuisance_count:]]
    before, after = free.evaluate_details(vv, nn)[0], shared.evaluate_details(v, n)[0]
    error = max(abs(before[0]-after[0]), abs(before[3].nll-after[3].nll),
        np.max(abs(before[3].residual_hz-after[3].residual_hz), initial=0))
    if max(closure, error) >= 1e-7:
        raise ValueError('Free-to-fixed band rebase failed physical/likelihood closure')
    trained = replace(context, model=shared, full_model=full, vector=v, nuisance=n)
    diagnostics = dict(seed=seed, donor=donor if use_donor else None,
        fit=fitted['diagnostics'], evaluations=int(charged+fitted['diagnostics']['evaluations']),
        full_objective_evaluations=int(3+fitted['diagnostics']['evaluations']),
        partial_density_evaluations=int(seed['partial_density_evaluations']),
        max_evaluations=int(max_evaluations), max_seconds=float(max_seconds),
        elapsed_seconds=float(time.monotonic()-begun), initial_objective=initial_objective,
        trained_objective=float(after[0]), accepted=bool(fitted['diagnostics'].get('accepted', False)),
        learned_offsets_hz=np.asarray(shift.offsets_hz).tolist(),
        receiver_slopes_hz_s=[float(v[3]), float(v[5])],
        correction_transport_max_hz=float(closure), masked_objective_closure_error=float(error),
        physical_band_columns=int(joint.offset_count), fixed_c=bool(context.fixed_c),
        prior_policy='Existing zero-mean 50kHz band prior unchanged; donor is initializer only',
        qualification='Training-only current calibration; no donor position/timing/identity transported; stationary local optimum is not predictive validation.')
    return trained, diagnostics
