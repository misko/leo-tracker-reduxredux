"""Endpoint replays and scientific figures; GPS is used only after inference."""

from pathlib import Path
import numpy as np

from ds23_same_probe_covariance import residual_pair
from probe_ds23_frequency_events import cached, summary
from probe_ds23_shared_probe_position import OUT, CASES, METHODS, RF, prepare_inputs, make
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha


def replay(case):
    saved = read(OUT/(case+'.json'))
    if saved['status'] != 'complete':
        raise ValueError('position trial incomplete')
    d = prepare_inputs(case)
    for field in ('covariance', 'updates', 'skips'):
        if d[field] != saved[field]:
            raise ValueError('RF evidence changed')
    np.testing.assert_array_equal(d['mask'], saved['original_mask'])
    original_ids = {oid for t in d['scan'].tracks for oid in t['observation_ids']}
    added_ids = [oid for e in saved['extra_entries'] for oid in e['observation_ids']]
    if len(added_ids) != len(set(added_ids)) or original_ids.intersection(added_ids):
        raise ValueError('added peak duplicates original evidence')
    branches = dict(incumbent=dict(arms=saved['incumbent_arms'], paired_valid=True, policy_arms=saved['incumbent_arms']),
                    refined_control=saved['refined_control'], **saved['results'])
    rows = []
    for method, branch in branches.items():
        pair = {}
        for arm, record in branch['arms'].items():
            baseline = method in ('incumbent', 'refined_control')
            scan = d['scan'] if method == 'incumbent' else d['changed'] if baseline else d['enriched']
            entries = d['original_entries'] if baseline else saved['entries']
            anchors = {} if baseline else d['anchors']
            p = make(scan, d['node'], d['mask'], arm, np.asarray(record['phase_reference']), d['powers'], d['means'],
                     d['hyper'], entries, anchors, d['covariance'], method == 'shared_probe_secondary')
            x = np.asarray(record['endpoint_east_north_km'])
            fresh = summary(p, x, entries)
            delta = fresh['negative_twice_elbo']-record['negative_twice_elbo']
            if abs(delta) > 1e-6 or fresh['linear_calibration_max_difference'] != 0:
                raise ValueError('objective or curved-only calibration failed replay')
            for key in ('gates', 'linear_gates'):
                one = fresh[key]['tracks'] if key == 'gates' else fresh[key]
                two = record[key]['tracks'] if key == 'gates' else record[key]
                if [(r['component'], r['compatible']) for r in one] != [(r['component'], r['compatible']) for r in two]:
                    raise ValueError('original compatibility gates failed replay')
            fresh['final_phase_change_s'] = record.get('final_phase_change_s', 0.)
            pair[arm] = fresh
            rows.append(dict(case=case, method=method, arm=arm, paired_valid=branch['paired_valid'],
                             trial_latlon=record['endpoint_latlon'], policy_latlon=branch['policy_arms'][arm]['endpoint_latlon'],
                             objective_replay_difference=float(delta), frequency_RMS_hz=record['RMS_hz'],
                             original_curved_points=record['active_points'], predictive_points=record.get('predictive_points'),
                             linear_calibration_max_difference=fresh['linear_calibration_max_difference']))
        if valid(pair) != branch['paired_valid']:
            raise ValueError('paired acceptance failed replay')
        expected = branch['arms'] if branch['paired_valid'] else saved['incumbent_arms']
        if branch['policy_arms'] != expected:
            raise ValueError('incumbent fallback changed')
    return rows


def main():
    protocol = read(OUT/'protocol.json')
    for name, expected in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name) != expected:
            raise ValueError('position source changed')
    rows = [r for case in CASES for r in replay(case)]
    # Evaluation truth is imported only after all likelihood/gate replays.
    from report_algo02_ds23 import position_error
    for row in rows:
        row['trial_position_error_km'] = position_error(row['trial_latlon'])
        row['policy_position_error_km'] = position_error(row['policy_latlon'])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    rf = read(RF/'evaluation.json')
    diagnostics = {}
    for case, axis in zip(CASES, axes, strict=True):
        points = sorted([r for r in rf['rows'] if r['case'] == case and r['two_components_qualified']], key=lambda r: r['time_s'])
        times = np.array([r['time_s'] for r in points])
        first = np.array([r['refined_first_value'] for r in points])
        second = np.array([r['refined_second_value'] for r in points])
        degree = rf['summary'][case]['RF_qualified']['degree']
        fresh = residual_pair(times, first, second, degree)
        for k in ('first_sigma_hz', 'second_sigma_hz', 'covariance_hz2', 'difference_sigma_hz'):
            np.testing.assert_allclose(fresh[k], rf['summary'][case]['RF_qualified'][k], rtol=0, atol=1e-7)
        diagnostics[case] = {k: fresh[k] for k in ('first_sigma_hz', 'second_sigma_hz', 'correlation', 'difference_sigma_hz')}
        axis[0].plot(times, first/1000, '.-', ms=3, label='First received component')
        axis[0].plot(times, second/1000, '.-', ms=3, label='Second received component')
        axis[0].set(title=case+' · refined pilot CFO', xlabel='Scan time (s)', ylabel='Lifted CFO (kHz)')
        axis[0].legend(fontsize=8)
        axis[1].plot(times, fresh['first_residual_hz'], '.-', lw=.7, label='First')
        axis[1].plot(times, fresh['second_residual_hz'], '.-', lw=.7, label='Second')
        axis[1].plot(times, np.array(fresh['second_residual_hz'])-fresh['first_residual_hz'], '.-', lw=.7, label='Difference')
        axis[1].set(title=f"Same degree-{degree} projection · correlation {fresh['correlation']:.3f}", xlabel='Scan time (s)', ylabel='Residual (Hz)')
        axis[1].axhline(0, color='k', lw=.5); axis[1].legend(fontsize=8)
        axis[2].scatter(fresh['first_residual_hz'], fresh['second_residual_hz'], s=12)
        bounds = np.array([-350, 350]); axis[2].plot(bounds, bounds, 'k--', lw=.6)
        axis[2].set(title=f"Difference scatter {fresh['difference_sigma_hz']:.1f} Hz", xlabel='First residual (Hz)', ylabel='Second residual (Hz)')
        for a in axis:
            a.grid(alpha=.2)
    fig.suptitle('Real saved IQ: shared CFO errors in simultaneous distinct pilot components\nSelected by simultaneous coverage; polynomial residuals do not identify the hardware cause')
    fig.savefig(OUT/'shared_frequency_evidence.png', dpi=160); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    methods = ['incumbent', 'refined_control', *METHODS]
    names = ['Incumbent', 'RF refinement', 'Independent\nextra peaks', 'Shared-error\nextra peaks']
    for case, ax in zip(CASES, axes, strict=True):
        for arm, shift in zip(ARMS, [-.18, .18], strict=True):
            values = [next(r['policy_position_error_km'] for r in rows if (r['case'], r['method'], r['arm']) == (case, m, arm)) for m in methods]
            bars = ax.bar(np.arange(4)+shift, values, width=.34, label=arm)
            ax.bar_label(bars, fmt='%.3f', fontsize=8)
        ax.set(xticks=np.arange(4), xticklabels=names, ylabel='Position error (km)', title=case)
        ax.set_ylim(0, ax.get_ylim()[1]*1.3); ax.grid(axis='y', alpha=.2); ax.legend(ncol=2, fontsize=8)
    fig.suptitle('Two development scans: actual regional position fits, unchanged original gates\nOriginal data preserved; new peaks predictive only; conditional Gaussian is a modular approximation')
    fig.savefig(OUT/'position_comparison.png', dpi=160); plt.close(fig)
    receipt = dict(rows=rows, RF_diagnostics=diagnostics, independently_replayed_position_endpoints=len(rows),
                   all_original_gates_replayed=True, original_observations_preserved=True,
                   c0_fitted_c_matched=True, GPS_used_only_in_reporting=True,
                   two_development_scans_not_generalization=True, full_DS23_accuracy_goal_achieved=False,
                   protocol_sha256=sha(OUT/'protocol.json'),
                   evidence={c: sha(OUT/(c+'.json')) for c in CASES})
    write(OUT/'independent_replay_audit.json', receipt)
    print('SHARED_PROBE_AUDIT', [(r['case'], r['method'], r['arm'], round(r['policy_position_error_km'], 6)) for r in rows], flush=True)


if __name__ == '__main__':
    main()
