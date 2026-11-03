"""Matched position pilot using every eligible saved simultaneous-component lane."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_frequency_events import make_event_problem
from ds23_multilane_prediction import attach_multilane_prediction
from ds23_probe_conditioned_prediction import symmetrized_RF_covariance
from ds23_same_probe_covariance import residual_pair
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import cached, summary, refit as original_refit
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_shared_probe_position import refine_original, added_evidence, freeze_aliases
from probe_ds23_all_lane_components import BULK, OUT as RF_REPORT
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

OUT = BULK/'position'
METHODS = ('independent_all_lanes', 'shared_single_lane', 'shared_all_lanes')


def RF_guard(rows, degree):
    t = np.array([r['time_s'] for r in rows])
    a = np.array([r['refined_first_value'] for r in rows]); b = np.array([r['refined_second_value'] for r in rows])
    stats = residual_pair(t, a, b, degree)
    split = [residual_pair(t[k::2], a[k::2], b[k::2], degree)['correlation'] for k in (0, 1)]
    noise = [bool(batch_noise_screen(np.asarray(stats[name])[None], t)['noise_screen_pass'][0])
             for name in ('first_residual_hz', 'second_residual_hz')]
    checks = dict(correlation_at_least_point6=stats['correlation'] >= .6,
                  both_interleaved_at_least_point4=min(split) >= .4, both_residual_noise_screens=all(noise))
    return dict(eligible=all(checks.values()), checks=checks, interleaved=split, correlation=stats['correlation'])


def prepare_inputs(case):
    scan, node, mask, powers, means, hyper, original_entries, signed, signed_path = context_signed(case)
    rf, protocol = read(BULK/'evaluation.json'), read(BULK/'protocol.json')
    lookup = {j['probe']: j for j in protocol['jobs'] if j['case'] == case}
    rows = sorted([r for r in rf['rows'] if r['case'] == case and r['status'] == 'complete' and r['two_components_qualified']], key=lambda r: r['time_s'])
    jobs = [lookup[r['probe']] for r in rows]
    changed, updates = refine_original(scan, jobs, rows)
    enriched = changed
    extra, anchors, covariance, group_info, diagnostics = [], {}, {}, {}, []
    for selected in [s for s in protocol['selected'] if s['case'] == case]:
        group = selected['group']
        subset = [r for r in rows if lookup[r['probe']]['group'] == group]
        stat = next(s for s in rf['summary'] if s['group'] == group).get('RF_qualified_statistics')
        record = dict(group=group, lane=selected['lane'], RF_qualified_points=len(subset), new_components=[])
        if stat is None:
            diagnostics.append(dict(record, reason='fewer_than16_RF_qualified_points')); continue
        guard = RF_guard(subset, stat['degree']); record['RF_guard'] = guard
        if not guard['eligible']:
            diagnostics.append(dict(record, reason='common_error_guard_failed')); continue
        nominated = read(BULK/'catalogue'/(group+'.json'))
        if nominated['status'] != 'complete':
            diagnostics.append(dict(record, reason='catalogue_unavailable')); continue
        first = nominated['results']['regional_centre']['candidates']
        second = nominated['results']['current_scan_RF_mode']['candidates']
        if not first or not second or any(first[0][k] != second[0][k] for k in ('first_index', 'second_index')):
            diagnostics.append(dict(record, reason='top_nomination_unstable')); continue
        nomination = first[0]; record['nomination'] = nomination
        cov = symmetrized_RF_covariance(stat['first_sigma_hz'], stat['second_sigma_hz'], stat['covariance_hz2'])
        group_jobs = [lookup[r['probe']] for r in subset]
        try:
            proposal, entries, local_anchors, skips = added_evidence(case, enriched, node, mask, powers, means, hyper,
                group_jobs, subset, nomination, cov)
        except ValueError as exc:
            if str(exc) != 'predictive satellite must already have original curved support':
                raise
            diagnostics.append(dict(record, reason='secondary_family_missing_original_phase_coordinate')); continue
        for entry in entries:
            old = entry['component']; key = group+'-'+old.split('-same_probe_')[-1]
            entry['component'] = key; entry['lane_group'] = group
            proposal.tracks[entry['track_index']] = dict(proposal.tracks[entry['track_index']], key=key)
            anchors[key] = local_anchors[old]; covariance[key] = cov
        enriched = proposal
        record.update(new_components=[e['component'] for e in entries], skips=skips, added_measurements=sum(e['points'] for e in entries))
        diagnostics.append(record)
        if entries:
            group_info[group] = dict(native_pair_points=len(selected['pair']['probes']), covariance=cov,
                                     added_measurements=record['added_measurements'])
        extra.extend(entries)
    original_ids = {o for t in scan.tracks for o in t['observation_ids']}
    new_ids = [o for e in extra for o in e['observation_ids']]
    if len(new_ids) != len(set(new_ids)) or original_ids.intersection(new_ids):
        raise ValueError('duplicate original or added physical peak across lane groups')
    all_anchors = [a for v in anchors.values() for a in v]
    if len(all_anchors) != len(set(all_anchors)):
        raise ValueError('multiple conditional additions reuse one original probe')
    return dict(scan=scan, changed=changed, enriched=enriched, node=node, mask=mask, powers=powers, means=means,
        hyper=hyper, original_entries=original_entries, signed=signed, signed_path=signed_path, extra=extra,
        anchors=anchors, covariance=covariance, groups=group_info, diagnostics=diagnostics, updates=updates)


def make(d, arm, reference, entries, correlated):
    p = make_event_problem(d['enriched'], d['node'], d['mask'], arm, reference, d['powers'], d['means'], d['hyper'], [])
    attach_multilane_prediction(p, entries, d['powers'], d['anchors'], d['covariance'], correlated)
    return cached(p)


def refit(d, arm, entries, correlated):
    x, reference, history = np.zeros(2), np.zeros(len(d['means'])), []
    for _ in range(5):
        p = make(d, arm, reference, entries, correlated)
        result = fit(p, x, iterations=48); x = np.asarray(result['parameters'])
        phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        history.append(dict(fit=result, phase_change_s=float(np.max(abs(phase-reference)))))
        reference = phase
    record = summary(p, x, entries)
    record.update(history=history, final_phase_change_s=history[-1]['phase_change_s'])
    return record


def run(case):
    path = OUT/(case+'.json')
    if path.exists():
        return read(path)
    started = time.monotonic()
    def timeout(*_):
        raise TimeoutError('300 second all-lane position pilot budget exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(300)
    try:
        d = prepare_inputs(case); incumbent = d['signed']['policy_arms']
        controls = {a: original_refit(d['changed'], d['node'], d['mask'], a, d['powers'], d['means'], d['hyper'], [], d['original_entries']) for a in ARMS}
        valid_control = valid(controls)
        extra = freeze_aliases(d['enriched'], d['node'], d['mask'], d['powers'], d['means'], d['hyper'], d['extra'], controls['c0']) if d['extra'] else []
        largest = max(d['groups'], key=lambda g: (d['groups'][g]['native_pair_points'], g)) if d['groups'] else None
        methods = {}
        for method in METHODS:
            additions = [e for e in extra if method != 'shared_single_lane' or e['lane_group'] == largest]
            entries = d['original_entries']+additions
            pair = {a: refit(d, a, entries, method != 'independent_all_lanes') for a in ARMS}
            accepted = valid(pair)
            methods[method] = dict(arms=pair, paired_valid=accepted, entries=entries,
                policy_arms=pair if accepted else incumbent, added_measurements=sum(e['points'] for e in additions))
            print(case, method, 'valid', accepted, 'added', methods[method]['added_measurements'],
                  {a: r['endpoint_east_north_km'] for a, r in pair.items()}, flush=True)
        result = dict(case=case, status='complete', results=methods, diagnostics=d['diagnostics'], extra_entries=extra,
            original_mask=d['mask'], covariance=d['covariance'], anchors=d['anchors'], groups=d['groups'],
            updates=d['updates'], means=d['means'], powers=d['powers'], hyper=d['hyper'], incumbent_arms=incumbent,
            RF_refined_control=dict(arms=controls, paired_valid=valid_control, policy_arms=controls if valid_control else incumbent),
            signed_incumbent_path=str(d['signed_path'].relative_to(ROOT)), signed_incumbent_sha256=sha(d['signed_path']),
            original_observations_and_gates_preserved=True, linear_points_never_calibrate=True,
            no_GPS_inference=True, no_new_RF=True, existing_phase_coordinates_only_for_this_controlled_pilot=True,
            conditional_Gaussian_is_modular_approximation=True, three_development_scans_not_generalization=True)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = dict(case=case, status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    result['seconds'] = time.monotonic()-started
    write(path, result)
    return result


def main():
    OUT.mkdir(exist_ok=True)
    cases = read(BULK/'protocol.json')['cases']
    protocol = dict(cases=cases, methods=list(METHODS), workers=3, per_case_seconds=300,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_multilane_prediction.py']},
        RF_evaluation_sha256=sha(BULK/'evaluation.json'), catalogue_execution_sha256=sha(BULK/'catalogue/execution.json'),
        cold_start=[0, 0], regional_box_km=25, phase_rounds=5, position_iterations=48,
        matched_c0_fitted_c=True, no_GPS_used=True, all_original_observations_and_priors_retained=True,
        RF_guard='rho>=.6, both interleaved>=.4, both original residual-noise screens',
        all_lanes_same_added_data_for_independent_and_shared=True, old_predictive_and_all_added_data_in_one_covariance_block=True)
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('all-lane position protocol changed')
    if not path.exists():
        write(path, protocol)
    with ProcessPoolExecutor(max_workers=3) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, c) for c in cases])]
    write(OUT/'execution.json', dict(rows=rows, all_terminal=True))


if __name__ == '__main__':
    main()
