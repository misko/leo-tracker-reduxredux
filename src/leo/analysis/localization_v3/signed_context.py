"""Build the original signed-prior incumbent from explicit owned scan evidence."""

import numpy as np

from leo.analysis.localization_v3.event_position import make_event_problem, refit
from leo.analysis.localization_v3.history_policy import ARMS, pair_passes, validate_history
from leo.analysis.localization_v3.history_position import forecast_phase_mean, problem
from leo.analysis.localization_v3.retained_position import phase_widths
from leo.analysis.localization_v3.signed_phase import adjust_means, qualify


def normalize_empty_predictive(pair, entries):
    if entries:
        return pair
    return {arm: dict(saved, linear_gates=saved.get('linear_gates', []))
            for arm, saved in pair.items()}


def signed_context(scan, original, old, raw, forecast, observations, *, case,
                   cutoff_utc_ns, history_sha256, signed=True):
    """Preserve qualification, both-arm acceptance and all-catalogue prior state.

    Inputs are numerical incumbents and causal evidence from this scan. No old
    workers, results on disk, or evaluation position are read by this function.
    """
    if old['status'] != 'accepted':
        raise ValueError('family policy has no qualified paired incumbent')
    node = original['final_node']
    keep = np.asarray(old['mask'], bool)
    base = problem(scan, node, 'c0', keep)
    model = old['hyperparameters_from_pre_RF_TLE_only']
    _, receipts = phase_widths(scan, base.labels)
    powers = np.asarray(old['weights'])
    means = forecast_phase_mean(receipts, model['shrinkage'])
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    validate_history(raw, forecast, case=case, origin_utc_ns=scan.origin_utc_ns,
                     cutoff_utc_ns=cutoff_utc_ns, raw_sha256=history_sha256)
    if any(r['validation_time_ns'] > cutoff_utc_ns for r in forecast['transitions']):
        raise ValueError('post-scan target in signed mean qualification')
    selection = qualify(forecast['transitions'], forecast['temporal_split_boundary_ns'],
                        forecast['prefix_distribution'], model)
    pair, accepted = old['policy_arms'], False
    if signed and selection['qualified']:
        _, receipts = phase_widths(scan, base.labels)
        adjusted = adjust_means(means, receipts, model, selection)
        candidate = {a: refit(scan, node, keep, a, powers, adjusted, model, [], entries)
                     for a in ARMS}
        accepted = pair_passes(candidate, include_linear=True,
                               half_width_km=scan.search_region.half_width_km)
        if accepted:
            means, pair = adjusted, candidate
    if not entries:
        pair = normalize_empty_predictive(pair, entries)
    _, receipts = phase_widths(scan, list(range(len(scan.norads))))
    all_means = forecast_phase_mean(receipts, model['shrinkage'])
    if accepted:
        all_means = adjust_means(all_means, receipts, model, selection)
    widths, _ = phase_widths(scan, list(range(len(scan.norads))))
    saved = pair['c0']
    reference = np.asarray(saved['phase_reference'])
    base = make_event_problem(scan, node, keep, 'c0', reference, powers, means, model, [])
    signed_record = dict(policy_arms=pair, accepted=accepted, selection=selection)
    return dict(case=case, scan=scan, node=node, keep=keep, powers=powers, means=means,
        model=model, entries=entries, arms=pair, signed=signed_record,
        base=base, x=np.asarray(saved['endpoint_east_north_km']), reference=reference,
        all_means=np.asarray(all_means), widths=widths*model['multiplier'],
        observations=observations,
        original_protected={r['candidate_index'] for r, sl in
            zip(base.rows, base.slices, strict=True) if keep[sl].any()} |
            {e['candidate_index'] for e in entries})
