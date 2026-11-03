"""Replay new-family phase coordinates, controls, and physical measurement use."""

import numpy as np
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_new_curved_family import make_new_family_problem
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from probe_ds23_frequency_events import summary
from probe_ds23_joint_probe_position import endpoint
from probe_ds23_shared_probe_position import freeze_aliases
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha
import probe_ds23_new_curved_family as inference


def replay(case):
    path = inference.BULK/(case+'.json'); saved = read(path)
    if saved['status'] != 'complete':
        raise ValueError(f'{case}: new-family trial unavailable: {saved}')
    d = inference.prepare(case)
    if sha(d['signed_source']) != saved['incumbent_sha256'] or d['signed']['policy_arms'] != saved['incumbent_arms']:
        raise ValueError('new-family incumbent changed')
    np.testing.assert_array_equal(d['means'], saved['new_means_s'])
    if d['labels'] != saved['new_labels'] or d['original_labels'] != saved['original_phase_labels']:
        raise ValueError('new causal phase labels changed')
    null = inference.null_coordinate_audit(d)
    for one, two in zip(null, saved['null_coordinate_audit'], strict=True):
        np.testing.assert_allclose(one['position_independent_extra_prior_cost'], two['position_independent_extra_prior_cost'], atol=1e-7)
    d['extra'] = freeze_aliases(d['enriched'], d['node'], d['mask'], d['powers'], d['means'], d['hyper'],
                               d['extra'], saved['augmented_inactive_control']['c0'])
    if d['extra'] != saved['extra_entries']:
        raise ValueError('new-family physical IDs or frozen aliases changed')
    rows = []; details = {}; pairs = {}
    for method in ['incumbent', 'RF_refined_control', 'augmented_inactive_control', 'new_family']:
        records = saved['incumbent_arms'] if method == 'incumbent' else saved['arms'] if method == 'new_family' else saved[method]
        pair = {}
        for arm, old in records.items():
            if method in ('incumbent', 'RF_refined_control'):
                scan = d['original_scan'] if method == 'incumbent' else d['refined']
                p = make_event_problem(scan, d['original_node'], d['original_mask'], arm, np.array(old['phase_reference']),
                    d['original_powers'], d['original_means'], d['hyper'], [])
                attach_event_predictive(p, d['original_entries'], d['original_powers'])
                r = summary(p, np.array(old['endpoint_east_north_km']), d['original_entries'])
            else:
                p = make_new_family_problem(d, arm, np.array(old['phase_reference']), method == 'new_family')
                r = endpoint(p, np.array(old['endpoint_east_north_km']))
            difference = r['negative_twice_elbo']-old['negative_twice_elbo']
            if abs(difference) > 1e-6 or r['linear_calibration_max_difference'] != 0:
                raise ValueError('new-family objective or predictive separation failed replay')
            for key in ['gates', 'linear_gates']:
                first = r[key]['tracks'] if key == 'gates' else r[key]; second = old[key]['tracks'] if key == 'gates' else old[key]
                if [(v['component'], v['compatible']) for v in first] != [(v['component'], v['compatible']) for v in second]:
                    raise ValueError('new-family original or added gates changed')
            r['final_phase_change_s'] = old.get('final_phase_change_s', 0.); pair[arm] = r
            rows.append(dict(case=case, method=method, arm=arm, trial_latlon=r['endpoint_latlon'],
                objective_replay_difference=difference, frequency_RMS_hz=r['RMS_hz'],
                original_curved_points=int(d['original_mask'].sum()), additional_curved_points=r.get('additional_curved_points', 0),
                failed_curved=[v['component'] for v in r['gates']['tracks'] if not v['compatible']],
                failed_linear=[v['component'] for v in r['linear_gates'] if not v['compatible']]))
            if method == 'new_family':
                c = p.calculate(np.array(old['endpoint_east_north_km'])); view, values, _, _, slices = linear_geometry(p, d['extra'])
                active_ids = [o for index, sl in zip(p.members, p.slices, strict=True)
                              for o, keep in zip(p.scan.tracks[index]['observation_ids'], p.keep[sl], strict=True) if keep]
                added_ids = [o for e in d['extra'] for o in e['observation_ids']]
                if len(set(active_ids+added_ids)) != len(active_ids)+len(added_ids):
                    raise ValueError('new-family physical point counted twice')
                p0 = make_new_family_problem(d, arm, np.array(saved['augmented_inactive_control'][arm]['phase_reference']), False)
                x0 = np.array(saved['augmented_inactive_control'][arm]['endpoint_east_north_km']); c0 = p0.calculate(x0)
                lv, ly, _, _, _ = linear_geometry(p0, d['extra']); g0 = geometry_features(lv, x0, 0.)
                prior_prediction = lv.q*g0['intercept']+g0['features']@c0['coefficient']
                details[arm] = [dict(component=e['component'], norad=e['norad'], time_s=p.scan.tracks[e['track_index']]['times'],
                    values=values[sl], inactive_prior_prediction=prior_prediction[sl],
                    new_prediction=values[sl]-c['joint_secondary_marginal_raw_hz'][sl]+c['joint_secondary_bias_hz'][k],
                    raw_residual=c['joint_secondary_marginal_raw_hz'][sl]-c['joint_secondary_bias_hz'][k],
                    conditional_residual=c['joint_secondary_fitted_residual_hz'][sl],
                    phase_prior_mean_s=d['means'][p.labels.index(e['candidate_index'])],
                    phase_prior_sigma_s=p.phase_sigma[p.labels.index(e['candidate_index'])],
                    phase_posterior_s=r['state']['phases'][e['candidate_index']])
                    for k, (e, sl) in enumerate(zip(d['extra'], slices, strict=True))]
        pairs[method] = pair
        accepted = valid(pair)
        for r in rows:
            if r['method'] != method:
                continue
            r['paired_valid'] = accepted
            r['policy_latlon'] = r['trial_latlon'] if accepted else saved['incumbent_arms'][r['arm']]['endpoint_latlon']
    if valid(pairs['new_family']) != saved['paired_valid']:
        raise ValueError('new-family paired policy changed')
    expected = saved['arms'] if saved['paired_valid'] else saved['incumbent_arms']
    if saved['policy_arms'] != expected:
        raise ValueError('new-family exact fallback changed')
    return dict(case=case, rows=rows, details=details, null_coordinate_audit=null, result_sha256=sha(path))


def main():
    protocol = read(inference.OUT/'protocol.json')
    for name, digest in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name) != digest:
            raise ValueError('new-family source changed')
    receipts = [replay(c) for c in protocol['cases']]; rows = [r for receipt in receipts for r in receipt['rows']]
    from report_algo02_ds23 import position_error
    for r in rows:
        r['position_error_km'] = position_error(r['policy_latlon']); r['trial_error_km'] = position_error(r['trial_latlon'])
    statistics = {}
    for method in ['incumbent', 'RF_refined_control', 'augmented_inactive_control', 'new_family']:
        statistics[method] = {arm:dict(mean_km=float(np.mean([r['position_error_km'] for r in rows if (r['method'],r['arm'])==(method,arm)])),
            median_km=float(np.median([r['position_error_km'] for r in rows if (r['method'],r['arm'])==(method,arm)]))) for arm in ARMS}
    write(inference.OUT/'independent_replay_audit.json', dict(rows=rows, statistics=statistics, receipts=receipts,
        no_double_counting_replayed=True, original_gates_and_measurements_preserved=True,
        new_phase_prior_position_independent_null_verified=True, no_GPS_inference=True,
        engineering_cases_not_generalization=True, full_DS23_goal_achieved=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, len(receipts), figsize=(12, 10), constrained_layout=True, squeeze=False)
    for column, receipt in enumerate(receipts):
        detail = receipt['details']['fitted_c'][0]; t = np.array(detail['time_s'])
        axes[0,column].scatter(t, np.array(detail['values'])/1000, s=15, label='Additional native GLRT component')
        axes[0,column].plot(t, np.array(detail['inactive_prior_prediction'])/1000, '--', label='Causal prior + RF-only calibration')
        axes[0,column].plot(t, np.array(detail['new_prediction'])/1000, label='Joint orbit/radio prediction')
        axes[0,column].set(title=receipt['case']+f" · proposed NORAD{detail['norad']}", ylabel='Lifted CFO (kHz)'); axes[0,column].legend(fontsize=7)
        axes[1,column].plot(t, detail['raw_residual'], '.-', label='Raw orbit/radio residual')
        axes[1,column].plot(t, detail['conditional_residual'], '.-', label='Conditional residual after shared-probe term')
        axes[1,column].axhline(0, color='k', lw=.6); axes[1,column].set(xlabel='Scan time (s)', ylabel='Residual (Hz)'); axes[1,column].legend(fontsize=7)
        methods = ['incumbent','RF_refined_control','augmented_inactive_control','new_family']
        values = [next(r['position_error_km'] for r in rows if (r['case'],r['arm'],r['method'])==(receipt['case'],'fitted_c',m)) for m in methods]
        bars=axes[2,column].bar(range(4),values);axes[2,column].bar_label(bars,fmt='%.3f',fontsize=8)
        axes[2,column].set(xticks=range(4),xticklabels=['Incumbent','RF refinement','Inactive phase','New family'],ylabel='Policy position error (km)')
        for ax in axes[:,column]:ax.grid(alpha=.2)
    fig.suptitle('New phase coordinates for independently curved RF components · two engineering scans\nOriginal data/gates retained; rejected joint trials fall back exactly; new satellite nominations remain proposals')
    fig.savefig(inference.OUT/'new_family_evaluation.png',dpi=160);plt.close(fig)
    print('NEW_FAMILY_AUDIT',statistics,flush=True)
    print([(r['case'],r['method'],r['arm'],r['paired_valid'],r['position_error_km'],r['trial_error_km']) for r in rows],flush=True)


if __name__ == '__main__':
    main()
