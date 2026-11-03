"""Replay causal-neighbor mean interventions before report-only GPS scoring."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_frequency_events import summary
import probe_ds23_neighbor_phase_position as inference
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha


def replay(case):
    saved = read(inference.OUT/(case+'.json'))
    data, prior, modified, design, counts = inference.prepare(case)
    scan, node, mask, powers, original, hyper, entries, signed, _ = data
    for actual, expected in [(modified, saved['modified_means_s']), (design, saved['neighbor_features']),
                             (counts, saved['effective_neighbor_counts']), (original, saved['original_means_s'])]:
        np.testing.assert_array_equal(actual, expected)
    if signed['policy_arms'] != saved['incumbent_arms'] or sha(inference.PRIORS/(case+'.json')) != saved['prior_sha256']:
        raise ValueError('incumbent or causal forecast changed')
    if not prior['selection']['qualified']:
        np.testing.assert_array_equal(original, modified)
        if saved['policy_arms'] != signed['policy_arms']:
            raise ValueError('unqualified forecast changed the incumbent')
        return [dict(case=case, method=m, arm=a, policy_latlon=r['endpoint_latlon'], trial_latlon=r['endpoint_latlon'],
                     prior_qualified=False, paired_valid=False, no_offer=True, frequency_RMS_hz=r['RMS_hz'])
                for m in ['incumbent', 'neighbor_prior'] for a, r in saved['policy_arms'].items()]
    pair = {}; rows = []
    for arm, old in saved['arms'].items():
        p = make_event_problem(scan, node, mask, arm, np.array(old['phase_reference']), powers, modified, hyper, [])
        attach_event_predictive(p, entries, powers)
        r = summary(p, np.array(old['endpoint_east_north_km']), entries)
        delta = r['negative_twice_elbo']-old['negative_twice_elbo']
        if abs(delta) > 1e-6 or r['linear_calibration_max_difference'] != 0:
            raise ValueError('neighbor objective or no-linear-calibration failed replay')
        for key in ['gates', 'linear_gates']:
            one = r[key]['tracks'] if key == 'gates' else r[key]
            two = old[key]['tracks'] if key == 'gates' else old[key]
            if [(v['component'], v['compatible']) for v in one] != [(v['component'], v['compatible']) for v in two]:
                raise ValueError('neighbor unchanged gates failed replay')
        r['final_phase_change_s'] = old['final_phase_change_s']; pair[arm] = r
        rows.append(dict(case=case, method='neighbor_prior', arm=arm,
            policy_latlon=saved['policy_arms'][arm]['endpoint_latlon'], trial_latlon=old['endpoint_latlon'],
            objective_replay_difference=delta, prior_qualified=True, paired_valid=saved['paired_valid'],
            frequency_RMS_hz=r['RMS_hz'], negative_twice_elbo=r['negative_twice_elbo'],
            maximum_prior_mean_change_s=float(np.max(abs(modified-original))),
            failed_curved=[v['component'] for v in r['gates']['tracks'] if not v['compatible']],
            failed_linear=[v['component'] for v in r['linear_gates'] if not v['compatible']]))
    if valid(pair) != saved['paired_valid'] or saved['policy_arms'] != (saved['arms'] if valid(pair) else signed['policy_arms']):
        raise ValueError('neighbor paired policy changed')
    rows += [dict(case=case, method='incumbent', arm=a, policy_latlon=r['endpoint_latlon'], trial_latlon=r['endpoint_latlon'],
                  prior_qualified=True, paired_valid=True, frequency_RMS_hz=r['RMS_hz']) for a, r in signed['policy_arms'].items()]
    return rows


def report():
    protocol = read(inference.OUT/'protocol.json')
    for name, digest in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name) != digest:
            raise ValueError('neighbor inference source changed')
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows = [r for future in as_completed([pool.submit(replay, c) for c in protocol['cases']]) for r in future.result()]
    from report_algo02_ds23 import position_error
    for r in rows:
        r['position_error_km'] = position_error(r['policy_latlon'])
        r['trial_error_km'] = position_error(r['trial_latlon'])
    statistics = {}
    for method in ['incumbent', 'neighbor_prior']:
        statistics[method] = {}
        for arm in ARMS:
            group = [r for r in rows if (r['method'], r['arm']) == (method, arm)]
            if len(group) != len(protocol['cases']):
                raise ValueError('missing comparison denominator')
            errors = [r['position_error_km'] for r in group]
            statistics[method][arm] = dict(count=len(group), mean_km=float(np.mean(errors)), median_km=float(np.median(errors)),
                p90_km=float(np.quantile(errors, .9)), qualified=sum(r['prior_qualified'] for r in group),
                paired_valid=sum(r['paired_valid'] for r in group))
    write(inference.OUT/'independent_replay_audit.json', dict(rows=rows, statistics=statistics,
        causal_forecast_and_endpoints_replayed=True, no_GPS_in_inference=True, matched_c0_fitted_c=True,
        unchanged_original_observations_and_gates=True, full_DS23_goal_achieved=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        baseline = {r['case']: r['position_error_km'] for r in rows if (r['method'], r['arm']) == ('incumbent', arm)}
        for r in [r for r in rows if (r['method'], r['arm']) == ('neighbor_prior', arm)]:
            ax.scatter(baseline[r['case']], r['position_error_km'], color='tab:blue' if r['paired_valid'] else '.6',
                       marker='o' if r['paired_valid'] else 'x')
            if len(protocol['cases']) <= 6:
                ax.annotate(r['case'].split('-')[-1], (baseline[r['case']], r['position_error_km']), fontsize=8)
        limit = max(ax.get_xlim()[1], ax.get_ylim()[1]); ax.plot([0, limit], [0, limit], 'k--', lw=.6)
        ax.set(title=arm, xlabel='Incumbent position error (km)', ylabel='Neighbor prior position error (km)'); ax.grid(alpha=.2)
    fig.suptitle('Phase means forecast solely from earlier TLE updates in neighboring orbital planes\nUnqualified forecast or paired-gate failure retains exact incumbent · GPS used for this plot only')
    fig.savefig(inference.OUT/'position_comparison.png', dpi=160); plt.close(fig)
    print('NEIGHBOR_POSITION', statistics, flush=True)


if __name__ == '__main__':
    report()
