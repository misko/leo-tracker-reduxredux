"""Replay joint curved calibration, unchanged gates and report-side accuracy."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

import probe_ds23_joint_probe_position as joint
import probe_ds23_shared_probe_position as previous
from probe_ds23_sign_carrier_position import SIGNED_AUDIT
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha


def replay(case, directory=None, bulk=None):
    if bulk is not None:
        joint.BULK = Path(bulk)
    directory = joint.OUT if directory is None else Path(directory)
    source = joint.configure(case)
    saved = read(directory/(case+'.json'))
    binding = read(SIGNED_AUDIT)['evidence'][case]
    incumbent_path = ROOT/binding['path']
    if sha(incumbent_path) != binding['sha256']:
        raise ValueError('audited incumbent changed')
    incumbent = read(incumbent_path)['policy_arms']
    rows = [dict(case=case, method='incumbent', arm=arm, policy_latlon=r['endpoint_latlon'],
                 trial_latlon=r['endpoint_latlon'], paired_valid=True) for arm, r in incumbent.items()]
    if saved['status'] != 'complete':
        for method in joint.METHODS:
            rows += [dict(case=case, method=method, arm=arm, policy_latlon=r['endpoint_latlon'],
                          trial_latlon=None, paired_valid=False, reason=saved.get('reason', saved.get('error')),
                          exact_incumbent_fallback=True) for arm, r in incumbent.items()]
        return dict(case=case, status=saved['status'], rows=rows, result_sha256=sha(directory/(case+'.json')))
    d = previous.prepare_inputs(case)
    extra = saved['extra_entries']
    if d['covariance'] != saved['covariance']:
        raise ValueError('RF covariance changed')
    original_ids = {o for t in d['scan'].tracks for o in t['observation_ids']}
    added_ids = [o for entry in extra for o in entry['observation_ids']]
    if original_ids.intersection(added_ids) or len(added_ids) != len(set(added_ids)):
        raise ValueError('added conditional data duplicate original evidence')
    for method, branch in saved['results'].items():
        pair = {}
        for arm, record in branch['arms'].items():
            p = joint.make(d, arm, np.asarray(record['phase_reference']), extra, method == 'joint_shared_curved')
            x = np.asarray(record['endpoint_east_north_km'])
            fresh = joint.endpoint(p, x)
            delta = fresh['negative_twice_elbo']-record['negative_twice_elbo']
            if abs(delta) > 1e-6 or fresh['linear_calibration_max_difference'] != 0:
                raise ValueError('joint position objective or predictive-only calibration failed replay')
            for key in ('gates', 'linear_gates'):
                first = fresh[key]['tracks'] if key == 'gates' else fresh[key]
                second = record[key]['tracks'] if key == 'gates' else record[key]
                if [(r['component'], r['compatible']) for r in first] != [(r['component'], r['compatible']) for r in second]:
                    raise ValueError('joint paired gate changed')
            if p.joint_conditional_powers != record['conditional_powers']:
                raise ValueError('original/additional replication power changed')
            np.testing.assert_array_equal(p.keep, d['mask'])
            fresh['final_phase_change_s'] = record['final_phase_change_s']
            pair[arm] = fresh
            rows.append(dict(case=case, method=method, arm=arm, policy_latlon=branch['policy_arms'][arm]['endpoint_latlon'],
                             trial_latlon=record['endpoint_latlon'], paired_valid=branch['paired_valid'],
                             objective_replay_difference=float(delta), frequency_RMS_hz=record['RMS_hz'],
                             original_curved_points=record['active_points'],
                             additional_curved_points=record['additional_curved_points'],
                             failed_curved=[r['component'] for r in fresh['gates']['tracks'] if not r['compatible']],
                             failed_linear=[r['component'] for r in fresh['linear_gates'] if not r['compatible']]))
        if valid(pair) != branch['paired_valid']:
            raise ValueError('joint paired acceptance changed')
        expected = branch['arms'] if branch['paired_valid'] else incumbent
        if branch['policy_arms'] != expected:
            raise ValueError('joint fallback differs from incumbent')
    return dict(case=case, status=saved['status'], rows=rows, result_sha256=sha(directory/(case+'.json')))


def report(directory=None, bulk=None, cases=None):
    directory = joint.OUT if directory is None else Path(directory)
    protocol = read(directory/'protocol.json') if (directory/'protocol.json').exists() else None
    if protocol:
        for name, expected in protocol['source_sha256'].items():
            if sha(ROOT/'tools'/name) != expected:
                raise ValueError('joint scientific source changed')
    cases = read(directory/'execution.json')['rows'] if cases is None else cases
    cases = [r['case'] if isinstance(r, dict) else r for r in cases]
    with ProcessPoolExecutor(max_workers=8) as pool:
        audited = [f.result() for f in as_completed([pool.submit(replay, c, str(directory), bulk) for c in cases])]
    rows = [r for case in audited for r in case['rows']]
    from report_algo02_ds23 import position_error
    for row in rows:
        row['policy_position_error_km'] = position_error(row['policy_latlon'])
        row['trial_position_error_km'] = None if row['trial_latlon'] is None else position_error(row['trial_latlon'])
    statistics = {}
    for subset, chosen in [('all', set(cases)), ('previous_random20', set(cases)-set(previous.CASES))]:
        statistics[subset] = {}
        for method in ('incumbent', *joint.METHODS):
            statistics[subset][method] = {}
            for arm in ARMS:
                group = [r for r in rows if r['case'] in chosen and (r['method'], r['arm']) == (method, arm)]
                if not group:
                    continue
                errors = [r['policy_position_error_km'] for r in group]
                baseline = {r['case']: r['policy_position_error_km'] for r in rows if (r['method'], r['arm']) == ('incumbent', arm)}
                changes = [r['policy_position_error_km']-baseline[r['case']] for r in group]
                statistics[subset][method][arm] = dict(count=len(group), mean_km=float(np.mean(errors)), median_km=float(np.median(errors)),
                    paired_valid=sum(r['paired_valid'] for r in group), improved=sum(v < -1e-6 for v in changes),
                    regressed=sum(v > 1e-6 for v in changes), unchanged=sum(abs(v) <= 1e-6 for v in changes))
    write(directory/'independent_replay_audit.json', dict(statistics=statistics, rows=rows, cases=audited,
          original_observations_and_gates_replayed=True, linear_observations_never_calibrate=True,
          all_no_offer_cases_in_denominator=True, matched_c0_fitted_c=True, GPS_only_reporting=True,
          full_DS23_goal_achieved=False))
    print('JOINT_CALIBRATION_REPLAY', statistics, flush=True)


if __name__ == '__main__':
    report()
