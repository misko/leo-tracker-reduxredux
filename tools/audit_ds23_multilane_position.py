"""Replay conditional multi-lane fits before report-side position evaluation."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

import probe_ds23_multilane_position as predictive
import probe_ds23_joint_multilane_position as joint
from probe_ds23_joint_probe_position import endpoint as joint_endpoint
from probe_ds23_frequency_events import summary
from probe_ds23_sign_carrier_position import SIGNED_AUDIT
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha


def replay(case, bulk):
    bulk = Path(bulk); predictive.BULK, predictive.OUT = bulk, bulk/'position'
    joint.PREVIOUS, joint.OUT = bulk/'position', bulk/'joint_position'
    cut, coupled = read(predictive.OUT/(case+'.json')), read(joint.OUT/(case+'.json'))
    binding = read(SIGNED_AUDIT)['evidence'][case]; signed_path = ROOT/binding['path']
    if sha(signed_path) != binding['sha256']:
        raise ValueError('original signed incumbent changed')
    incumbent = read(signed_path)['policy_arms']; rows = []
    methods = ['incumbent', 'RF_refined_control', *predictive.METHODS, *joint.METHODS]
    if cut['status'] != 'complete':
        for method in methods:
            rows += [dict(case=case, method=method, arm=a, policy_latlon=r['endpoint_latlon'], trial_latlon=None,
                          paired_valid=method == 'incumbent', reason='no eligible supported conditional evidence', exact_incumbent_fallback=True)
                     for a, r in incumbent.items()]
        return dict(case=case, rows=rows, status='no_offer')
    d = predictive.prepare_inputs(case)
    if d['updates'] != cut['updates'] or d['covariance'] != cut['covariance'] or d['anchors'] != cut['anchors']:
        raise ValueError('RF refinement, conditional covariance or physical ownership changed')
    np.testing.assert_array_equal(d['mask'], cut['original_mask'])
    source_ids = {o for t in d['scan'].tracks for o in t['observation_ids']}
    new_ids = [o for e in cut['extra_entries'] for o in e['observation_ids']]
    if len(new_ids) != len(set(new_ids)) or source_ids.intersection(new_ids):
        raise ValueError('additional multi-lane evidence duplicates original physical point')
    branches = dict(incumbent=dict(arms=incumbent, paired_valid=True, policy_arms=incumbent),
                    RF_refined_control=cut['RF_refined_control'], **cut['results'])
    if coupled['status'] == 'complete':
        branches.update(coupled['results'])
    for method, branch in branches.items():
        pair = {}
        for arm, record in branch['arms'].items():
            if method.startswith('joint_'):
                p = joint.make(d, arm, np.asarray(record['phase_reference']), coupled['extra_entries'], method == 'joint_shared_all_lanes')
                fresh = joint_endpoint(p, np.asarray(record['endpoint_east_north_km']))
            else:
                entries = branch.get('entries', d['original_entries'])
                data = dict(d, enriched=d['scan']) if method == 'incumbent' else d
                p = predictive.make(data, arm, np.asarray(record['phase_reference']), entries, method.startswith('shared_'))
                fresh = summary(p, np.asarray(record['endpoint_east_north_km']), entries)
            delta = fresh['negative_twice_elbo']-record['negative_twice_elbo']
            if abs(delta) > 1e-6 or fresh['linear_calibration_max_difference'] != 0:
                raise ValueError('multi-lane likelihood or no-linear-calibration failed exact replay')
            for key in ('gates', 'linear_gates'):
                first = fresh[key]['tracks'] if key == 'gates' else fresh[key]
                second = record[key]['tracks'] if key == 'gates' else record[key]
                if [(r['component'], r['compatible']) for r in first] != [(r['component'], r['compatible']) for r in second]:
                    raise ValueError('unchanged multi-lane compatibility gates failed replay')
            fresh['final_phase_change_s'] = record.get('final_phase_change_s', 0.)
            pair[arm] = fresh
            rows.append(dict(case=case, method=method, arm=arm, paired_valid=branch['paired_valid'],
                policy_latlon=branch['policy_arms'][arm]['endpoint_latlon'], trial_latlon=record['endpoint_latlon'],
                objective_replay_difference=float(delta), frequency_RMS_hz=record['RMS_hz'],
                original_curved_points=record['active_points'], additional_curved_points=record.get('additional_curved_points', 0),
                failed_curved=[r['component'] for r in fresh['gates']['tracks'] if not r['compatible']],
                failed_linear=[r['component'] for r in fresh['linear_gates'] if not r['compatible']]))
        if valid(pair) != branch['paired_valid']:
            raise ValueError('paired multi-lane policy acceptance changed')
        if branch['policy_arms'] != (branch['arms'] if branch['paired_valid'] else incumbent):
            raise ValueError('multi-lane exact fallback changed')
    if coupled['status'] != 'complete':
        for method in joint.METHODS:
            rows += [dict(case=case, method=method, arm=a, policy_latlon=r['endpoint_latlon'], trial_latlon=None,
                          paired_valid=False, reason='joint trial unavailable', exact_incumbent_fallback=True) for a, r in incumbent.items()]
    return dict(case=case, rows=rows, status='complete', extra_entries=cut['extra_entries'], diagnostics=cut['diagnostics'],
                predictive_sha256=sha(predictive.OUT/(case+'.json')), joint_sha256=sha(joint.OUT/(case+'.json')))


def report(bulk=None, output=None):
    bulk = predictive.BULK if bulk is None else Path(bulk)
    output = ROOT/'reports/2026_10_20_ds23_multilane_position' if output is None else Path(output)
    output.mkdir(exist_ok=True)
    if (bulk/'position/protocol.json').exists():
        for folder in ('position', 'joint_position'):
            protocol = read(bulk/folder/'protocol.json')
            for name, expected in protocol['source_sha256'].items():
                if sha(ROOT/'tools'/name) != expected:
                    raise ValueError('multi-lane inference source changed')
    cases = read(bulk/'protocol.json')['cases']
    with ProcessPoolExecutor(max_workers=min(10, len(cases))) as pool:
        audit = [f.result() for f in as_completed([pool.submit(replay, c, str(bulk)) for c in cases])]
    rows = [r for case in audit for r in case['rows']]
    from report_algo02_ds23 import position_error
    for r in rows:
        r['policy_position_error_km'] = position_error(r['policy_latlon'])
        r['trial_position_error_km'] = None if r['trial_latlon'] is None else position_error(r['trial_latlon'])
    statistics = {}
    for method in ['incumbent', 'RF_refined_control', *predictive.METHODS, *joint.METHODS]:
        statistics[method] = {}
        for arm in ARMS:
            group = [r for r in rows if (r['method'], r['arm']) == (method, arm)]
            values = [r['policy_position_error_km'] for r in group]
            baseline = {r['case']: r['policy_position_error_km'] for r in rows if (r['method'], r['arm']) == ('incumbent', arm)}
            changes = [r['policy_position_error_km']-baseline[r['case']] for r in group]
            statistics[method][arm] = dict(count=len(values), mean_km=float(np.mean(values)), median_km=float(np.median(values)),
                paired_valid=sum(r['paired_valid'] for r in group), improved=sum(v < -1e-6 for v in changes),
                regressed=sum(v > 1e-6 for v in changes), unchanged=sum(abs(v) <= 1e-6 for v in changes))
    write(output/'independent_replay_audit.json', dict(rows=rows, cases=audit, statistics=statistics,
        no_GPS_inference=True, matched_c0_fitted_c=True, original_observations_and_gates_replayed=True,
        predictive_data_do_not_calibrate=True, full_DS23_goal_achieved=False))
    print('MULTILANE_POSITION_AUDIT', statistics, flush=True)


if __name__ == '__main__':
    report()
