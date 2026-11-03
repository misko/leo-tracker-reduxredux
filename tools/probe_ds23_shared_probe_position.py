"""Matched regional position trials of independently received same-probe peaks.

Inference reads causal catalogue nominations and RF-only component tests. No
evaluation coordinates enter this module. Original curved calibration and its
accepted observations are preserved; new peaks enter prediction only.
"""

import copy
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time

import numpy as np

from ds23_frame_peak_recovery import measurement_id
from ds23_frequency_events import make_event_problem
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry
from ds23_probe_conditioned_prediction import attach_probe_prediction, symmetrized_RF_covariance
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import cached, refit as original_refit, summary
from probe_ds23_sign_carrier_position import context_signed, SIGNED_AUDIT
from probe_ds23_same_probe_IQ import OUT as RF
from probe_ds23_differential_catalogue import OUT as CATALOGUE
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.retained_track_likelihood import PERIOD, projected_receiver_basis, whitening

OUT = ROOT/'reports/2026_10_20_ds23_shared_probe_position'
CASES = ('DS23-0202', 'DS23-0274')
METHODS = ('independent_secondary', 'shared_probe_secondary')


def peak_role(value, job, tolerance=300.):
    distances = [abs((value-job[k]['cfo_hz']+PERIOD/2) % PERIOD-PERIOD/2)
                 for k in ('first', 'second')]
    passing = [k for k, d in zip(('first', 'second'), distances, strict=True) if d < tolerance]
    return passing[0] if len(passing) == 1 else None


def refine_original(scan, jobs, rows):
    """Only refine the actual original winning component, never replace it."""
    changed = copy.copy(scan)
    changed.tracks = [dict(t, values=np.asarray(t['values']).copy()) for t in scan.tracks]
    by_probe = {j['first']['probe_observation_id']: (j, r) for j, r in zip(jobs, rows, strict=True)}
    updates = {}
    for track in changed.tracks:
        for k, oid in enumerate(track['observation_ids']):
            if oid not in by_probe:
                continue
            job, row = by_probe[oid]
            role = peak_role(track['values'][k], job)
            if role is None:
                continue
            delta = float(row[role+'_fit']['CFO_hz']-job[role]['cfo_hz'])
            if oid in updates and updates[oid]['role'] != role:
                raise ValueError('original physical probe has conflicting component ownership')
            track['values'][k] += delta
            updates[oid] = dict(role=role, CFO_delta_hz=delta)
    return changed, updates


def added_evidence(case, scan, node, mask, powers, means, hyper, jobs, rows, nomination, covariance):
    p = make_event_problem(scan, node, mask, 'c0', np.zeros(len(means)), powers, means, hyper, [])
    owners = {}
    for row, index, sl in zip(p.rows, p.members, p.slices, strict=True):
        track = scan.tracks[index]
        for k, oid in enumerate(track['observation_ids']):
            flat = sl.start+k
            if not mask[flat]:
                continue
            if oid in owners:
                raise ValueError('original active curved physical point duplicated')
            owners[oid] = (flat, row['candidate_index'], float(track['values'][k]))
    grouped = defaultdict(list)
    skips = defaultdict(int)
    original_ids = {oid for t in scan.tracks for oid in t['observation_ids']}
    for job, rf in zip(jobs, rows, strict=True):
        oid = job['first']['probe_observation_id']
        if oid not in owners:
            skips['no_original_active_curved_anchor'] += 1
            continue
        flat, label, value = owners[oid]
        role = peak_role(value, job)
        if role is None or label != nomination[role+'_index']:
            skips['curved_owner_not_same_nominated_component'] += 1
            continue
        other = 'second' if role == 'first' else 'first'
        candidate = nomination[other+'_index']
        if candidate not in p.labels:
            raise ValueError('predictive satellite must already have original curved support')
        rx, channel, frequency = job['lane']
        new_id = measurement_id(case, rx, channel, frequency, job['time_s'],
                                dict(epoch=job[other]['epoch'], cfo=rf[other+'_fit']['CFO_hz']))
        if new_id in original_ids:
            raise ValueError('new secondary identity duplicates original point')
        grouped[other].append(dict(time_s=job['time_s'], value=rf['refined_'+other+'_value'],
                                  observation_id=new_id, anchor_flat_index=flat, probe=job['probe']))
    changed = copy.copy(scan)
    changed.tracks = list(scan.tracks)
    changed.rx_basis, changed.white, changed.index = list(scan.rx_basis), list(scan.white), list(scan.index)
    changed.fixed_window_noise = copy.deepcopy(scan.fixed_window_noise)
    # Preserve the effective original sigma even if its strength model was off.
    meta = changed.fixed_window_noise
    if meta['extra_parameter_BIC_gain'] <= 0:
        meta['per_observation_noise_sigma_hz'] = {o: scan.radio_sigma_hz for o in original_ids}
        meta['extra_parameter_BIC_gain'] = 1.
    entries, anchors = [], {}
    for role, group in sorted(grouped.items()):
        group.sort(key=lambda r: r['time_s'])
        if len(group) < 8:
            skips['fewer_than_eight_secondary_points'] += len(group)
            continue
        rx, channel, frequency = jobs[0]['lane']
        key = f'{case}-same_probe_{role}'
        times = np.array([r['time_s'] for r in group])
        ids = [r['observation_id'] for r in group]
        track = dict(key=key, receiver=rx, channel=channel, rf_hz=frequency,
                     times=times, values=np.array([r['value'] for r in group]), observation_ids=ids,
                     pieces=[], indices=[], start_s=float(times[0]), end_s=float(times[-1]),
                     quality_status='research_predictive_only', bank='research')
        index = len(changed.tracks)
        changed.tracks.append(track)
        changed.rx_basis.append(projected_receiver_basis(times))
        changed.white.append(whitening(times))
        positions = np.searchsorted(scan.times, times)
        if np.any(positions >= len(scan.times)) or np.max(abs(scan.times[positions]-times)) > 1e-6:
            raise ValueError('new component times differ from original receiver probe grid')
        changed.index.append(positions)
        meta['per_observation_noise_sigma_hz'].update({o: covariance['marginal_sigma_hz'] for o in ids})
        entries.append(dict(track_index=index, component=key, candidate_index=nomination[role+'_index'],
                            norad=nomination[role+'_norad'], alias=0, points=len(group), observation_ids=ids))
        anchors[key] = [r['anchor_flat_index'] for r in group]
    return changed, entries, anchors, dict(skips)


def freeze_aliases(scan, node, mask, powers, means, hyper, entries, reference_record):
    p = make_event_problem(scan, node, mask, 'c0', np.asarray(reference_record['phase_reference']), powers, means, hyper, [])
    position = np.asarray(reference_record['endpoint_east_north_km'])
    c = p.calculate(position)
    view, values, _, _, slices = linear_geometry(p, entries)
    geometry = geometry_features(view, position, 0.)
    prediction = view.q*geometry['intercept']+geometry['features']@c['coefficient']
    frozen = copy.deepcopy(entries)
    for entry, sl in zip(frozen, slices, strict=True):
        alias = int(np.rint(np.median(prediction[sl]-values[sl])/PERIOD))
        if np.max(abs(values[sl]+alias*PERIOD-prediction[sl])) >= PERIOD/4:
            raise ValueError('new peak lacks one stable CFO alias branch')
        entry['alias'] = alias
    return frozen


def make(scan, node, mask, arm, reference, powers, means, hyper, entries, anchors, covariance, correlated):
    p = make_event_problem(scan, node, mask, arm, reference, powers, means, hyper, [])
    attach_probe_prediction(p, entries, powers, anchors, covariance, correlated)
    return cached(p)


def refit(scan, node, mask, arm, powers, means, hyper, entries, anchors, covariance, correlated):
    position, reference, history = np.zeros(2), np.zeros(len(means)), []
    for _ in range(5):
        p = make(scan, node, mask, arm, reference, powers, means, hyper, entries, anchors, covariance, correlated)
        fitted = fit(p, position, iterations=48)
        position = np.asarray(fitted['parameters'])
        phase = np.clip(p.state(position)['phases'][p.labels], -15, 15)
        history.append(dict(fit=fitted, phase_change_s=float(np.max(abs(phase-reference)))))
        reference = phase
    record = summary(p, position, entries)
    record.update(history=history, final_phase_change_s=history[-1]['phase_change_s'])
    c = p.calculate(position)
    record['shared_probe_kappa'] = c['shared_probe_kappa']
    record['conditional_measurements'] = c['conditional_measurements']
    return record


def prepare_inputs(case):
    scan, node, mask, powers, means, hyper, original_entries, signed, signed_path = context_signed(case)
    rf = read(RF/'evaluation.json')
    rows = sorted([r for r in rf['rows'] if r['case'] == case and r['two_components_qualified']], key=lambda r: r['time_s'])
    lookup = {j['probe']: j for j in read(RF/'protocol.json')['jobs'] if j['case'] == case}
    jobs = [lookup[r['probe']] for r in rows]
    stats = rf['summary'][case]['RF_qualified']
    covariance = symmetrized_RF_covariance(stats['first_sigma_hz'], stats['second_sigma_hz'], stats['covariance_hz2'])
    nominated = read(CATALOGUE/(case+'.json'))['results']
    first = nominated['regional_centre']['candidates'][0]
    second = nominated['current_scan_RF_mode']['candidates'][0]
    if any(first[k] != second[k] for k in ('first_index', 'second_index')):
        raise ValueError('differential nomination unstable between regional centre and RF mode')
    changed, updates = refine_original(scan, jobs, rows)
    enriched, extra, anchors, skips = added_evidence(case, changed, node, mask, powers, means, hyper, jobs, rows, first, covariance)
    return dict(scan=scan, changed=changed, enriched=enriched, node=node, mask=mask, powers=powers, means=means,
                hyper=hyper, original_entries=original_entries, signed=signed, signed_path=signed_path,
                extra=extra, anchors=anchors, covariance=covariance, updates=updates, skips=skips,
                nomination=first, qualified_RF_points=len(rows))


def run(case):
    path = OUT/(case+'.json')
    if path.exists():
        return read(path)
    started = time.monotonic()
    def timeout(*_):
        raise TimeoutError('240 second per-case shared-probe position budget exhausted')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(240)
    try:
        d = prepare_inputs(case)
        node, mask, powers, means, hyper = (d[k] for k in ('node', 'mask', 'powers', 'means', 'hyper'))
        incumbent = d['signed']['policy_arms']
        null = {}
        for arm, old in incumbent.items():
            p = make(d['scan'], node, mask, arm, np.asarray(old['phase_reference']), powers, means, hyper,
                     d['original_entries'], {}, d['covariance'], False)
            difference = p.calculate(old['endpoint_east_north_km'])['negative_twice_elbo']-old['negative_twice_elbo']
            if abs(difference) > 1e-6:
                raise ValueError('original signed likelihood fails unchanged replay')
            null[arm] = float(difference)
        controls = {a: original_refit(d['changed'], node, mask, a, powers, means, hyper, [], d['original_entries']) for a in ARMS}
        control_valid = valid(controls)
        extra = freeze_aliases(d['enriched'], node, mask, powers, means, hyper, d['extra'], controls['c0'])
        entries = d['original_entries']+extra
        write(OUT/(case+'_evidence.json'), dict(extra_entries=extra, anchors=d['anchors'], covariance=d['covariance'],
              updates=d['updates'], skips=d['skips'], nomination=d['nomination'], qualified_RF_points=d['qualified_RF_points']))
        results = {}
        for method in METHODS:
            arms = {a: refit(d['enriched'], node, mask, a, powers, means, hyper, entries, d['anchors'],
                             d['covariance'], method == 'shared_probe_secondary') for a in ARMS}
            accepted = valid(arms)
            results[method] = dict(arms=arms, paired_valid=accepted, policy_arms=arms if accepted else incumbent)
            print(case, method, 'paired_valid', accepted, 'endpoint',
                  {a: r['endpoint_east_north_km'] for a, r in arms.items()}, flush=True)
        record = dict(case=case, status='complete', results=results, incumbent_arms=incumbent,
                      refined_control=dict(arms=controls, paired_valid=control_valid, policy_arms=controls if control_valid else incumbent),
                      original_signed_objective_replay_differences=null, extra_entries=extra,
                      anchors=d['anchors'], covariance=d['covariance'], entries=entries, means_s=means, powers=powers,
                      original_mask=mask, hyper=hyper, updates=d['updates'], skips=d['skips'],
                      signed_incumbent_path=str(d['signed_path'].relative_to(ROOT)), signed_incumbent_sha256=sha(d['signed_path']),
                      added_measurements=sum(e['points'] for e in extra), qualified_RF_probes=d['qualified_RF_points'],
                      original_observations_never_removed=True, no_GPS_or_future_TLE_used=True,
                      linear_points_never_calibrate=True, conditional_score_is_modular_Gaussian_approximation=True,
                      two_development_scans_not_generalization=True)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        record = dict(case=case, status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    record['seconds'] = time.monotonic()-started
    write(path, record)
    return record


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    protocol = dict(cases=CASES, methods=METHODS, workers=2, per_case_seconds=240,
                    phase_rounds=5, position_iterations=48, matched_c0_fitted_c=True,
                    cold_start_km=[0, 0], regional_centre=[37.906, -122.545], regional_box_km=25,
                    RF_evaluation_sha256=sha(RF/'evaluation.json'), RF_protocol_sha256=sha(RF/'protocol.json'),
                    signed_audit_sha256=sha(SIGNED_AUDIT),
                    catalogue_bindings={c: sha(CATALOGUE/(c+'.json')) for c in CASES},
                    source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_probe_conditioned_prediction.py']},
                    original_gates_unchanged=True, new_peaks_predictive_only=True, original_observations_preserved=True,
                    covariance_from_RF_only_polynomial_residuals=True, independent_comparator_same_added_data=True,
                    one_independent_300Hz_bias_per_added_fragment=True, unknown_Gamma_variance_factor=2,
                    same_probe_conditional_Gaussian_is_modular_approximation=True, no_GPS_used=True)
    path = OUT/'protocol.json'
    if path.exists():
        # JSON converts tuples to lists.
        import json
        if read(path) != json.loads(json.dumps(protocol)):
            raise ValueError('shared-probe trial changed after protocol freeze')
    else:
        write(path, protocol)
    with ProcessPoolExecutor(max_workers=2) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, c) for c in CASES])]
    write(OUT/'execution.json', dict(rows=rows, all_terminal=True, errors=[r for r in rows if r['status'] != 'complete']))


if __name__ == '__main__':
    main()
