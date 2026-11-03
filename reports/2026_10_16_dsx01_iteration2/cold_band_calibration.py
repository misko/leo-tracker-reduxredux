"""Training-only free receiver/band calibration followed by exact shared freeze.

No saved fit, target window, station position or held CFO supplies a seed. The
original eligible bank and actual RF are used at neutral geography and timing.
"""
from dataclasses import replace
import time
from types import SimpleNamespace

import numpy as np
from scipy.ndimage import gaussian_filter1d

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import ALIAS_HZ, circular


def _training_observations(obs, mask):
    rows = np.flatnonzero(mask)
    return replace(obs, window_ids=tuple(obs.window_ids[i] for i in rows),
        **{key: getattr(obs, key)[rows] for key in
           ('times_s', 'measured_hz', 'rf_hz', 'receiver', 'channel', 'margin')})


def _histogram_peak(values, weights, *, bins=1024):
    """Circular offset vote; one total vote per row, not per visible candidate."""
    width = ALIAS_HZ / bins
    values = circular(np.asarray(values, float))
    weights = np.broadcast_to(weights, values.shape)
    index = np.floor((values + ALIAS_HZ / 2) / width).astype(int) % bins
    histogram = np.bincount(index.ravel(), weights=weights.ravel(), minlength=bins)
    smooth = gaussian_filter1d(histogram, 1.5, mode='wrap')
    winner = int(np.argmax(smooth))
    center = (winner + .5) * width - ALIAS_HZ / 2
    residual = circular(values - center)
    selected = abs(residual) <= 2 * width
    mass = float(weights[selected].sum())
    offset = center + (float(np.sum(weights[selected] * residual[selected])) / mass if mass else 0.)
    return float(circular(offset)), float(smooth[winner]), mass


def histogram_seed(joint, obs, mask, bank, prior, *, deadline=float('inf')):
    """Per-RX low/high intercept votes and a shared slope in the declared bounds."""
    training = _training_observations(obs, np.asarray(mask, bool))
    prediction, visible, _, _ = predict_orbits(bank, training, prior,
        np.zeros(2), np.zeros(len(bank.numbers)), derivatives=False)
    residual = circular(training.measured_hz[:, None] - prediction)
    weights = visible / np.maximum(visible.sum(axis=1, keepdims=True), 1)
    centered_time = training.times_s - obs.time_center_s
    vector = np.zeros(joint.size)
    nuisance = np.asarray(joint.initial_nuisance, float).copy()
    diagnostics = []
    for rx, fraction in zip(joint.frame.receivers, joint.frame.high_fractions, strict=True):
        bands = [(training.receiver == rx) & (training.channel < 5),
                 (training.receiver == rx) & (training.channel >= 5)]
        if any(not use.any() for use in bands):
            raise ValueError('Each fitted receiver band requires training support')
        if any(not np.any(weights[use] > 0) for use in bands):
            raise ValueError('Each receiver band requires an eligible visible training prediction')
        best = None
        # This grid supplies only an initializer. Final slopes stay in +/-60 Hz/s.
        for slope in (0., -30., 30., -60., 60.):
            if best is not None and time.monotonic() >= deadline:
                break
            peaks = [_histogram_peak(circular(residual[use] - slope * centered_time[use, None]),
                weights[use]) for use in bands]
            score = sum(peak[1] / max(1, int(use.sum())) for peak, use in zip(peaks, bands))
            if best is None or score > best[0]:
                best = (score, slope, peaks)
        _, slope, peaks = best
        low, high = peaks[0][0], peaks[1][0]
        delta = float(circular(high - low))
        vector[2 + 2 * rx] = low + fraction * delta
        vector[3 + 2 * rx] = slope
        group = joint.frame.receivers.index(rx)
        nuisance[joint.clock_count + group] = delta
        diagnostics.append(dict(receiver=int(rx), low_offset_hz=low,
            high_offset_hz=high, high_minus_low_hz=delta,
            shared_slope_hz_s=slope, training_high_fraction=float(fraction),
            low_vote_mass=peaks[0][2], high_vote_mass=peaks[1][2]))
    return vector, nuisance, dict(receivers=diagnostics, orbit_projection_calls=1,
        training_rows=int(len(training.times_s)), bins=1024,
        candidate_policy='unchanged eligible bank; neutral point and zero satellite timing')


def bootstrap(context, max_evaluations=400, max_seconds=60):
    """Learn both physical contrasts on train rows; return a frozen shared context.

    The budget counts initialization, optimization and both closure evaluations.
    A better feasible nonstationary iterate is explicitly labeled as such.
    """
    from common import refit
    from leo.application.channel_group_refinement import objective
    from leo.analysis.channel_group_calibration import GroupCalibrationObjective, group_frame
    from leo.analysis.shared_scan_model import SmoothVisibilityModel, SharedScanObjective, donor_state

    if max_evaluations < 4 or not np.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError('At least four evaluations and positive finite seconds required')
    begun = time.monotonic()
    deadline = min(begun + max_seconds, context.deadline)
    obs, mask = context.observations, np.asarray(context.train_mask, bool)
    if mask.shape != obs.times_s.shape or not mask.any():
        raise ValueError('Nonempty full-observation training mask required')
    ordinary = objective(SimpleNamespace(observations=obs), context.bank, context.prior, context.nodes)
    frame = group_frame(obs.receiver[mask], obs.channel[mask] >= 5)
    if set(frame.receivers) != set(obs.receiver):
        raise ValueError('Every receiver needs both bands in the training half')
    joint = GroupCalibrationObjective(ordinary.base, obs.channel >= 5, frame=frame)
    joint.score = context.model.score
    free = SmoothVisibilityModel(joint, mask)
    vector, base_nuisance, seed_diagnostics = histogram_seed(joint, obs, mask,
        context.bank, context.prior, deadline=begun + .2 * max_seconds)
    nuisance = np.r_[base_nuisance, np.zeros(free.observation_parameter_count)]
    # c=0 and fitted-c use exactly the same neutral c seed and bootstrap policy.
    vector[6] = 0.
    initial_objective = float(free.evaluate_joint(vector, nuisance)[0])
    allowance = max_evaluations - 3
    # Leave time for the two counted closure evaluations and construction.
    fit_deadline = deadline - min(2., .1 * max_seconds)
    temporary = replace(context, model=free, full_model=free, vector=vector,
        nuisance=nuisance, deadline=fit_deadline)
    remaining_seconds = fit_deadline - time.monotonic()
    if remaining_seconds > 0:
        fitted = refit(temporary, vector, nuisance, max_evaluations=allowance,
            max_seconds=remaining_seconds, fixed_c=context.fixed_c)
    else:
        fitted = dict(vector=vector, nuisance=nuisance, diagnostics=dict(evaluations=0,
            accepted=False, reason='bootstrap seed exhausted wall allowance',
            objective=initial_objective, stationarity=None))
    vv, nn = np.asarray(fitted['vector']), np.asarray(fitted['nuisance'])
    raw, shift, final_vector, clock, transport = donor_state(joint,
        dict(vector=vv, nuisance=nn[:free.base_nuisance_count]))
    # donor_state uses the original raw score; transport the exact declared score.
    raw.score = free.score
    shared = SharedScanObjective(raw, shift, mask=mask)
    full = SharedScanObjective(raw, shift)
    final_nuisance = np.r_[clock, nn[free.base_nuisance_count:]]
    before = free.evaluate_details(vv, nn)[0]
    after = shared.evaluate_details(final_vector, final_nuisance)[0]
    error = max(abs(float(before[0] - after[0])),
        abs(float(before[3].nll - after[3].nll)),
        float(np.max(abs(before[3].residual_hz - after[3].residual_hz), initial=0)))
    if transport >= 1e-7 or error >= 1e-7:
        raise ValueError(f'Band freeze failed exact physical/likelihood closure: {transport}, {error}')
    trained = replace(context, model=shared, full_model=full, vector=final_vector,
        nuisance=final_nuisance)
    common_design = np.column_stack([joint.design[mask], joint.clock_design[mask]])
    augmented_design = np.column_stack([common_design, joint.group_design[mask]])
    diagnostics = dict(seed=seed_diagnostics, fit=fitted['diagnostics'],
        evaluations=3 + int(fitted['diagnostics']['evaluations']),
        max_evaluations=int(max_evaluations), max_seconds=float(max_seconds),
        elapsed_seconds=float(time.monotonic() - begun),
        initial_objective=initial_objective, trained_objective=float(after[0]),
        physical_band_column_count=int(joint.offset_count),
        training_group_design_rank=int(np.linalg.matrix_rank(joint.group_design[mask])),
        training_common_design_rank=int(np.linalg.matrix_rank(common_design)),
        training_augmented_design_rank=int(np.linalg.matrix_rank(augmented_design)),
        physical_free_nuisance_count=int(free.base_nuisance_count),
        q_parameter_count=int(free.observation_parameter_count),
        receivers=[int(rx) for rx in shift.receivers],
        learned_offsets_hz=np.asarray(shift.offsets_hz).tolist(),
        correction_transport_max_hz=float(transport),
        masked_objective_likelihood_residual_max_error=float(error),
        fixed_contrast_prior_penalty=float(shared.fixed_contrast_prior_penalty),
        fixed_c=bool(context.fixed_c),
        accepted=bool(fitted['diagnostics'].get('accepted', False)),
        qualification='Training-only band learning; original bank conditioned on prior discovery; closure is not convergence or identity truth.')
    return trained, diagnostics
