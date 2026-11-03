"""Report the matched gate experiment; evaluation GPS never enters inference."""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_predictive_gate_cohort import OUT
from probe_ds23_gate_retention_cohort import OUT as PREVIOUS, ARMS
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import read, write


def main():
    protocol = read(OUT/'protocol.json')
    execution = read(OUT/'execution.json')
    failures = [r for r in execution['results'] if 'error' in r]
    rows = []
    for case in protocol['cases']:
        old = read(PREVIOUS/(case+'.json'))
        current = read(OUT/(case+'.json')) if (OUT/(case+'.json')).exists() else None
        for arm in ARMS:
            records = dict(baseline=old['baseline_arms'][arm],
                gate_retention=old['policy_arms'][arm],
                legacy_no_rescue=(current['legacy_policy_arms'][arm] if current else old['baseline_arms'][arm]),
                predictive_no_rescue=(current['policy_arms'][arm] if current else old['baseline_arms'][arm]))
            rows.append(dict(case=case, arm=arm,
                cohort='development' if case in protocol['development'] else 'additional',
                **{name+'_error_km':position_error(r['endpoint_latlon']) for name,r in records.items()},
                accepted=bool(current and current['accepted']),
                legacy_accepted=bool(current and current['legacy_unconstrained_accepted'])))
    methods = ('baseline', 'gate_retention', 'legacy_no_rescue', 'predictive_no_rescue')
    summary = {}
    for group in ('development', 'additional', 'combined'):
        summary[group] = {}
        for arm in ARMS:
            chosen = [r for r in rows if r['arm'] == arm and (group == 'combined' or r['cohort'] == group)]
            summary[group][arm] = {}
            for method in methods:
                error = np.array([r[method+'_error_km'] for r in chosen])
                summary[group][arm][method] = dict(count=len(error), mean_km=float(error.mean()),
                    median_km=float(np.median(error)), below_half_km=int(sum(error <= .5)), maximum_km=float(error.max()))
    write(OUT/'evaluation.json', dict(summary=summary, rows=rows, failures=failures,
        post_hoc_same_site_experiment_not_independent_validation=True,
        full_DS23_half_km_goal_not_achieved=True,
        predictive_gate_does_not_outperform_legacy_no_rescue_control=True,
        no_positive_generalization_report_published=True))
    with (OUT/'evaluation.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    names = dict(baseline='Original ALGO02', gate_retention='Gate-constrained retention',
                 legacy_no_rescue='Legacy gates, no forced rescue', predictive_no_rescue='Predictive linear gates, no forced rescue')
    for ax, arm in zip(axes, ARMS, strict=True):
        chosen = [r for r in rows if r['arm'] == arm]
        for method in methods:
            error = np.sort([r[method+'_error_km'] for r in chosen])
            stat = summary['combined'][arm][method]
            ax.step(np.r_[0, error], np.r_[0, np.arange(1, len(error)+1)/len(error)], where='post',
                label=f'{names[method]} ({stat["mean_km"]:.3f}/{stat["median_km"]:.3f} km)',
                linestyle='--' if method == 'gate_retention' else '-')
        ax.axvline(.5, color='gray', lw=.9, ls=':')
        maximum = max(r[method+'_error_km'] for r in chosen for method in methods)
        ax.set(xlabel='Position error (km)', ylabel='Fraction of recordings ≤ error', title=arm,
               ylim=(0, 1.03), xlim=(0, maximum*1.04))
        ax.grid(alpha=.15)
        ax.legend(fontsize=8, loc='lower right')
    fig.suptitle('DS23 · 40 matched recordings · legend: mean/median error\n'
                 'Predictive uncertainty fixes one failure; a simpler no-rescue control still performs better', fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, .90))
    fig.savefig(OUT/'gate_ablation_position.png', dpi=180, bbox_inches='tight')
    plt.close(fig)
    print(summary['combined'], flush=True)


if __name__ == '__main__':
    main()
