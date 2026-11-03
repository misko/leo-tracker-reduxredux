"""Introduce causal phase coordinates for strongly separated new RF families."""

import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_new_curved_family import make_new_family_problem
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_frame_peak_recovery import measurement_id, polynomial_screen
from ds23_predictive_linear import attach_predictive_linear
from ds23_causal_phase_location import adjust_means
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import cached, summary, refit as old_refit
from probe_ds23_joint_probe_position import endpoint
from probe_ds23_shared_probe_position import refine_original, freeze_aliases
from probe_ds23_sign_carrier_position import context_signed
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.retained_track_likelihood import whitening, projected_receiver_basis

OUT = ROOT/'reports/2026_10_21_ds23_new_curved_family'
BULK = Path('/srv/bulk/leo/research/ds23-new-curved-family-20261021')
INVENTORY = ROOT/'reports/2026_10_21_ds23_new_phase_inventory/evaluation.json'
RF = Path('/srv/bulk/leo/research/ds23-multilane-confirmation-20261020')


def cases():
    return sorted({r['case'] for r in read(INVENTORY)['rows']
                   if r['active_curvature_evidence'] is not None and r['strong_gap_at_both_positions']})


def prepare(case):
    base = context_signed(case); scan, node, mask, powers, means, hyper, entries, signed, source = base
    choices = [r for r in read(INVENTORY)['rows'] if r['case'] == case and r['active_curvature_evidence'] is not None
               and r['strong_gap_at_both_positions']]
    protocol, rf = read(RF/'protocol.json'), read(RF/'evaluation.json')
    lookup = {j['probe']:j for j in protocol['jobs'] if j['case'] == case}
    rows = sorted([r for r in rf['rows'] if r['case'] == case and r['status'] == 'complete' and r['two_components_qualified']], key=lambda r:r['time_s'])
    by_probe = {r['probe']:r for r in rows}
    refined, updates = refine_original(scan, [lookup[r['probe']] for r in rows], rows)
    old = make_event_problem(refined, node, mask, 'c0', np.zeros(len(means)), powers, means, hyper, [])
    augmented = copy.copy(refined); newnode = copy.deepcopy(node)
    for name in ['tracks', 'rx_basis', 'white', 'index', 'curved']:
        setattr(augmented, name, list(getattr(refined, name)))
    augmented.fixed_window_noise = copy.deepcopy(refined.fixed_window_noise)
    noise = augmented.fixed_window_noise
    if noise['extra_parameter_BIC_gain'] <= 0:
        noise['per_observation_noise_sigma_hz'] = {o:scan.radio_sigma_hz for t in scan.tracks for o in t['observation_ids']}
        noise['extra_parameter_BIC_gain'] = 1.
    extra, anchors, covariance, metadata = [], {}, {}, []
    for proposal in choices:
        group = proposal['group']; role = proposal['role']; candidate = proposal['candidate_index']
        if candidate in old.labels or sha(RF/'evaluation.json') != proposal['source_RF_sha256']:
            raise ValueError('new family or RF source differs from inventory')
        if sha(RF/'catalogue'/(group+'.json')) != proposal['source_catalogue_sha256']:
            raise ValueError('new-family catalogue proposal changed')
        points = proposal['points']; t = np.array([r['time_s'] for r in points]); y = np.array([r['value'] for r in points])
        cov = proposal['covariance']; evidence = polynomial_screen(t, y, np.full(len(t), cov['marginal_sigma_hz']))
        if evidence is None:
            raise ValueError('new family does not have independently active curvature')
        job = lookup[points[0]['probe']]; rx, channel, frequency = job['lane']; ids = []
        for point in points:
            j, row = lookup[point['probe']], by_probe[point['probe']]
            if abs(row['refined_'+role+'_value']-point['value']) > 1e-8:
                raise ValueError('new native RF point changed')
            ids.append(measurement_id(case, rx, channel, frequency, point['time_s'],
                       dict(epoch=j[role]['epoch'], cfo=row[role+'_fit']['CFO_hz'])))
        key = group+'-new_family_'+role; index = len(augmented.tracks)
        track = dict(key=key, receiver=rx, channel=channel, rf_hz=frequency, times=t, values=y, observation_ids=ids,
                     pieces=[], indices=[], start_s=float(t[0]), end_s=float(t[-1]), bank='research', quality_status='research_conditional_curved')
        augmented.tracks.append(track); augmented.rx_basis.append(projected_receiver_basis(t)); augmented.white.append(whitening(t))
        ix = np.searchsorted(scan.times, t)
        if np.any(ix >= len(scan.times)) or np.max(abs(scan.times[ix]-t)) > 1e-6:
            raise ValueError('new RF times differ from original probe grid')
        augmented.index.append(ix); augmented.curved.append(index)
        noise['per_observation_noise_sigma_hz'].update({o:cov['marginal_sigma_hz'] for o in ids})
        newnode['seed']['rows'].append(dict(component=key, active_curvature=True, candidate_index=candidate,
                                            candidate_norad=proposal['norad']))
        newnode['aliases'].append(0)
        entry = dict(track_index=index, component=key, candidate_index=candidate, norad=proposal['norad'], alias=0,
                     points=len(t), observation_ids=ids)
        extra.append(entry); anchors[key] = [p['anchor_flat_index'] for p in points]; covariance[key] = cov
        metadata.append(dict(group=group, candidate_index=candidate, norad=proposal['norad'], curvature=evidence,
                             catalogue_gaps=proposal['catalogue_score_gaps'], catalogue_search_penalty=proposal['conservative_all_pairs_search_penalty']))
    new_ids = [o for e in extra for o in e['observation_ids']]; old_ids = {o for t in scan.tracks for o in t['observation_ids']}
    if len(set(new_ids)) != len(new_ids) or old_ids.intersection(new_ids):
        raise ValueError('new RF components duplicate existing physical points')
    labels = sorted(set(old.labels)|{e['candidate_index'] for e in extra})
    _, receipts = phase_widths(augmented, labels)
    newmeans = forecast_phase_mean(receipts, hyper['shrinkage'])
    if signed['accepted']:
        newmeans = adjust_means(newmeans, receipts, hyper, signed['selection'])
    np.testing.assert_allclose([newmeans[labels.index(j)] for j in old.labels], means, atol=1e-12, rtol=0)
    owners = {j:{(augmented.tracks[e['track_index']]['receiver'], augmented.tracks[e['track_index']]['channel'])
                 for e in extra if e['candidate_index'] == j} for j in set(labels)-set(old.labels)}
    family_powers = {j:1. if len({rx for rx,ch in owner}) >= 2 else .6 if len(owner) >= 2 else .2 for j,owner in owners.items()}
    newpowers = np.r_[powers, [family_powers[e['candidate_index']] for e in extra]]
    newmask = np.r_[mask, np.zeros(sum(e['points'] for e in extra), bool)]
    return dict(case=case, enriched=augmented, refined=refined, original_scan=scan, node=newnode, original_node=node,
        mask=newmask, original_mask=mask, powers=newpowers, original_powers=powers, means=newmeans, original_means=means,
        hyper=hyper, original_entries=entries, extra=extra, anchors=anchors, covariance=covariance,
        new_family_powers=family_powers, metadata=metadata, original_labels=old.labels, labels=labels,
        original_flat_count=len(mask), updates=updates, signed=signed, signed_source=source)


def null_coordinate_audit(d):
    records = []
    for arm in ARMS:
        saved = d['signed']['policy_arms'][arm]; old_reference = np.array(saved['phase_reference'])
        reference = np.zeros(len(d['means']))
        for k, j in enumerate(d['original_labels']):
            reference[d['labels'].index(j)] = old_reference[k]
        old = make_event_problem(d['refined'], d['original_node'], d['original_mask'], arm, old_reference,
            d['original_powers'], d['original_means'], d['hyper'], [])
        attach_predictive_linear(old, d['original_entries'], d['original_powers'])
        new = make_new_family_problem(d, arm, reference, False); offsets = []
        for point in [np.zeros(2), np.array(saved['endpoint_east_north_km'])]:
            a, b = old.calculate(point), new.calculate(point)
            np.testing.assert_allclose(a['conditional_residual_hz'], b['conditional_residual_hz'][:d['original_flat_count']], atol=1e-6, rtol=0)
            for key in ['beta', 'smooth']:
                np.testing.assert_allclose(old.state(point)[key], new.state(point)[key], atol=1e-6, rtol=0)
            offsets.append(float(b['negative_twice_elbo']-a['negative_twice_elbo']))
        if abs(offsets[0]-offsets[1]) > 1e-6:
            raise ValueError('new inactive phase changes position-dependent objective')
        records.append(dict(arm=arm, position_independent_extra_prior_cost=offsets[0], cost_difference_between_positions=offsets[1]-offsets[0]))
    return records


def refit(d, arm, enable):
    x, reference, history = np.zeros(2), np.zeros(len(d['means'])), []
    for _ in range(5):
        p = cached(make_new_family_problem(d, arm, reference, enable))
        fitted = fit(p, x, iterations=48); x = np.asarray(fitted['parameters'])
        phase = np.clip(p.state(x)['phases'][p.labels], -15, 15); change = float(np.max(abs(phase-reference)))
        history.append(dict(fit=fitted, phase_change_s=change)); reference = phase
    record = endpoint(p, x); record.update(history=history, final_phase_change_s=change)
    return record


def run(case):
    path = BULK/(case+'.json')
    if path.exists():
        return read(path)
    began = time.monotonic()
    def timeout(*_):
        raise TimeoutError('300second new-curved-family budget exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(300)
    try:
        d = prepare(case); null = null_coordinate_audit(d)
        refined = {a:old_refit(d['refined'], d['original_node'], d['original_mask'], a, d['original_powers'],
            d['original_means'], d['hyper'], [], d['original_entries']) for a in ARMS}
        empty = {a:refit(d, a, False) for a in ARMS}
        d['extra'] = freeze_aliases(d['enriched'], d['node'], d['mask'], d['powers'], d['means'], d['hyper'], d['extra'], empty['c0'])
        pair = {a:refit(d, a, True) for a in ARMS}; accepted = valid(pair)
        record = dict(case=case, status='complete', arms=pair, paired_valid=accepted,
            policy_arms=pair if accepted else d['signed']['policy_arms'], incumbent_arms=d['signed']['policy_arms'],
            RF_refined_control=refined, augmented_inactive_control=empty, null_coordinate_audit=null,
            extra_entries=d['extra'], metadata=d['metadata'], original_observations_and_gates_preserved=True,
            new_family_power=d['new_family_powers'], new_means_s=d['means'], new_labels=d['labels'],
            original_phase_labels=d['original_labels'], incumbent_sha256=sha(d['signed_source']),
            no_new_RF_or_GPS_or_future_TLE=True, only_independently_curved_data_calibrate=True)
        print(case, 'new family paired valid', accepted, flush=True)
    except Exception as exc:
        import traceback
        traceback.print_exc(); record = dict(case=case, status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    record['seconds'] = time.monotonic()-began; write(path, record); return record


def main():
    OUT.mkdir(exist_ok=True); BULK.mkdir(exist_ok=True)
    protocol = dict(cases=cases(), engineering_selection='all inventory components with active curvature and both catalogue gaps >2log(all ordered pairs)',
        inventory_sha256=sha(INVENTORY), existing_saved_IQ_only=True, no_GPS_or_future_TLE=True,
        new_phase_means_and_widths_use_same_causal_history_and_rules_as_original_families=True,
        all_original_data_and_gates_preserved=True, no_double_counting=True, no_linear_calibration=True,
        new_family_support_powers=[.2, .6, 1.], new_curve_bias_sigma_hz=300,
        cold_start=[0, 0], regional_width_km=25, phase_rounds=5, iterations=48, matched_c0_fitted_c=True,
        per_case_seconds=300, workers=2, engineering_pilot_not_generalization=True,
        source_sha256={p.name:sha(p) for p in [Path(__file__), ROOT/'tools/ds23_new_curved_family.py']})
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('new curved family experiment changed')
    if not path.exists():
        write(path, protocol)
    with ProcessPoolExecutor(max_workers=2) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, c) for c in protocol['cases']])]
    write(OUT/'execution.json', dict(rows=rows, all_terminal=True))


if __name__ == '__main__':
    main()
