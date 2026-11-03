"""Replay the random confirmation and compare all selected cases, with fallbacks."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

from probe_ds23_shared_probe_cohort import OUT, BULK
from run_algo01_ds23_sample import ROOT, read, write, sha


def replay(case):
    import audit_ds23_shared_probe_position as audit
    import probe_ds23_shared_probe_position as position
    position.OUT = audit.OUT = BULK/'position'
    position.RF = BULK/'IQ'
    position.CATALOGUE = BULK/'catalogue'
    saved = read(position.OUT/(case+'.json'))
    binding = read(position.SIGNED_AUDIT)['evidence'][case]
    signed_path = ROOT/binding['path']
    if sha(signed_path) != binding['sha256']:
        raise ValueError('signed incumbent changed')
    incumbent = read(signed_path)['policy_arms']
    if saved['status'] == 'complete':
        rows = audit.replay(case)
    else:
        rows = []
        for method in ('incumbent', 'refined_control', *position.METHODS):
            for arm, r in incumbent.items():
                rows.append(dict(case=case, method=method, arm=arm, paired_valid=method == 'incumbent',
                                 trial_latlon=None, policy_latlon=r['endpoint_latlon'],
                                 unavailable_trial=True, reason=saved['error'],
                                 exact_incumbent_fallback=True))
    return dict(case=case, status=saved['status'], error=saved.get('error'), rows=rows,
                added_measurements=saved.get('added_measurements', 0),
                covariance=saved.get('covariance'), result_sha256=sha(position.OUT/(case+'.json')),
                failed_gates={method: {arm: dict(
                    curved=[r['component'] for r in record['gates']['tracks'] if not r['compatible']],
                    predictive=[r['component'] for r in record['linear_gates'] if not r['compatible']])
                    for arm, record in branch['arms'].items()}
                    for method, branch in saved.get('results', {}).items()})


def main():
    protocol = read(OUT/'position_protocol.json')
    for name, expected in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name) != expected:
            raise ValueError('confirmation inference source changed')
    if sha(BULK/'IQ/evaluation.json') != protocol['RF_evaluation_sha256']:
        raise ValueError('RF evidence changed')
    execution = read(BULK/'position/execution.json')
    if not execution['all_terminal'] or set(execution['cases']) != set(protocol['cases']):
        raise ValueError('confirmation not terminal on all selected cases')
    panel_bindings = {}
    for name in ('read_only_exports.json', 'late_arc_read_only_exports.json'):
        for r in read(OUT/name)['rows']:
            if r.get('sha256'):
                panel_bindings[r['case']] = r['sha256']
    for case in protocol['cases']:
        if sha(BULK/'panels'/(case+'.npz')) != panel_bindings[case]:
            raise ValueError('existing-IQ panel changed')
    with ProcessPoolExecutor(max_workers=8) as pool:
        cases = [f.result() for f in as_completed([pool.submit(replay, c) for c in protocol['cases']])]
    rows = [r for case in cases for r in case['rows']]
    from report_algo02_ds23 import position_error
    for r in rows:
        r['policy_position_error_km'] = position_error(r['policy_latlon'])
        r['trial_position_error_km'] = None if r['trial_latlon'] is None else position_error(r['trial_latlon'])
    methods = ('incumbent', 'refined_control', 'independent_secondary', 'shared_probe_secondary')
    statistics = {}
    for method in methods:
        statistics[method] = {}
        for arm in ('c0', 'fitted_c'):
            group = [r for r in rows if (r['method'], r['arm']) == (method, arm)]
            errors = np.array([r['policy_position_error_km'] for r in group])
            baseline = {r['case']: r['policy_position_error_km'] for r in rows if (r['method'], r['arm']) == ('incumbent', arm)}
            changes = errors-np.array([baseline[r['case']] for r in group])
            statistics[method][arm] = dict(count=len(group), mean_km=float(errors.mean()), median_km=float(np.median(errors)),
                                          paired_valid=sum(r['paired_valid'] for r in group),
                                          improved=int(sum(changes < -1e-6)), regressed=int(sum(changes > 1e-6)),
                                          unchanged=int(sum(abs(changes) <= 1e-6)),
                                          mean_change_km=float(changes.mean()))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    native = {r['case']: r for r in read(OUT/'native_summary.json')['rows']}
    RF = read(BULK/'IQ/evaluation.json')['summary']
    for case in protocol['cases']:
        before = native[case]['selected_pair']['correlation']
        after = RF[case]['RF_qualified']['correlation']
        rx = native[case]['selected_lane'][0]
        axes[0].scatter(before, after, c='tab:blue' if rx == 1 else 'tab:orange', s=35)
        axes[0].annotate(case.split('-')[1], (before, after), fontsize=7, xytext=(3, 2), textcoords='offset points')
    axes[0].plot([-.1, 1], [-.1, 1], 'k--', lw=.6)
    axes[0].set(xlabel='Native GLRT residual correlation', ylabel='Refined saved-IQ residual correlation',
                title='Random20: shared error survives RF refinement\nBlue RX1; orange RX2; selection by coverage')
    for arm, marker in [('c0', 'o'), ('fitted_c', 'x')]:
        before = {r['case']: r['policy_position_error_km'] for r in rows if (r['method'], r['arm']) == ('incumbent', arm)}
        after = {r['case']: r['policy_position_error_km'] for r in rows if (r['method'], r['arm']) == ('shared_probe_secondary', arm)}
        axes[1].scatter(list(before.values()), [after[c] for c in before], label=arm, marker=marker)
    limit = max(axes[1].get_xlim()[1], axes[1].get_ylim()[1])
    axes[1].plot([0, limit], [0, limit], 'k--', lw=.6)
    axes[1].set(xlabel='Incumbent position error (km)', ylabel='Shared-probe policy error (km)',
                title='All20 selected scans, including exact fallbacks\nBelow diagonal improves; all original gates retained')
    axes[1].legend()
    for ax in axes:
        ax.grid(alpha=.2)
    fig.savefig(OUT/'confirmation.png', dpi=160); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.5), constrained_layout=True)
    names = ['Incumbent', 'RF refinement', 'Independent extra peaks', 'Shared-error extra peaks']
    for ax, arm in zip(axes, ('c0', 'fitted_c'), strict=True):
        for statistic, shift in [('mean_km', -.18), ('median_km', .18)]:
            values = [statistics[m][arm][statistic] for m in methods]
            bars = ax.bar(np.arange(4)+shift, values, width=.34, label=statistic.replace('_km', ''))
            ax.bar_label(bars, fmt='%.3f', fontsize=8)
        ax.set(xticks=np.arange(4), xticklabels=names, ylabel='Position error (km)', title=arm)
        ax.tick_params(axis='x', labelrotation=12); ax.grid(axis='y', alpha=.2)
        ax.set_ylim(0, ax.get_ylim()[1]*1.25); ax.legend(ncol=2, fontsize=8)
    fig.suptitle('Seeded random20 confirmation · matched data and priors across c arms\nSame DS23 site; not a new-location evaluation')
    fig.savefig(OUT/'position_summary.png', dpi=160); plt.close(fig)
    write(OUT/'independent_replay_audit.json', dict(statistics=statistics, rows=rows, cases=cases,
          protocol_sha256=sha(OUT/'position_protocol.json'), all_selected_cases_in_denominator=True,
          GPS_used_only_in_reporting=True, original_gates_replayed=True,
          paired_c0_fitted_c=True, hypothesis_qualified_on_two_scans_before_random20=True,
          no_full_DS23_or_new_location_claim=True, goal_achieved=False))
    print('CONFIRMATION_STATISTICS', statistics, flush=True)


if __name__ == '__main__':
    main()
