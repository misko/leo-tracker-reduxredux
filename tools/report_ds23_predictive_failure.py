"""Report-side RF mean/covariance decomposition and geographic consequences."""

import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from probe_ds23_multifamily_projection import OUT
from run_algo01_ds23_sample import read, write


def main():
    execution = read(OUT / 'mean_covariance_execution.json')
    if not execution['all_terminal'] or execution['errors']:
        raise ValueError('all dense Gaussian decomposition checks must finish first')
    with (OUT / 'position_comparison.csv').open() as handle:
        positions = {(r['case'], r['arm']): r for r in csv.DictReader(handle)}
    cases = sorted(r['case'] for r in execution['receipts'])
    rows = []
    figure, axes = plt.subplots(2, 2, figsize=(15, 9), sharex='col')
    for column, arm in enumerate(('c0', 'fitted_c')):
        means, covariances, errors = [], [], []
        for case in cases:
            d = read(OUT / 'mean_covariance_decomposition' / (case+'.json'))['arms'][arm]
            r = positions[case, arm]
            change = float(r['projected_error_km'])-float(r['incumbent_error_km'])
            rows.append(dict(case=case, arm=arm, cohort=r['cohort'], position_error_change_km=change,
                predictive_mean_gain=-d['mean_Shapley_change'], predictive_covariance_gain=-d['covariance_Shapley_change'],
                total_predictive_gain=-d['total_change'], fixed_old_covariance_mean_gain=-d['mean_only_change_at_old_covariance']))
            means.append(-d['mean_Shapley_change'])
            covariances.append(-d['covariance_Shapley_change'])
            errors.append(change)
        x = np.arange(len(cases))
        axes[0, column].bar(x, means, label='Mean contribution', color='#3886a6')
        axes[0, column].bar(x, covariances, bottom=means, label='Covariance contribution', color='#be8b4a')
        axes[0, column].set(title=arm, ylabel='Cross-family predictive score gain\n(positive is a better RF score)')
        axes[0, column].legend(fontsize=8)
        axes[1, column].bar(x, errors, color=['#bd5260' if e > 0 else '#448770' for e in errors])
        axes[1, column].axhline(0, color='black', lw=.8)
        axes[1, column].set(xticks=x, xticklabels=[c.split('-')[-1] for c in cases],
            xlabel='DS23 scan · every changed policy position', ylabel='Position error change (km)\n(positive is worse)')
        for ax in axes[:, column]:
            ax.grid(axis='y', alpha=.15)
    figure.suptitle('DS23 · better held-family RF prediction can still select a worse location\n'
        'Every changed position passes original gates · symmetric mean/covariance decomposition · GPS used only below')
    figure.tight_layout(rect=(0, 0, 1, .92))
    figure.savefig(OUT / 'RF_prediction_vs_position_failure.png', dpi=175)
    plt.close(figure)
    with (OUT / 'RF_prediction_vs_position_failure.csv').open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    summary = {}
    for arm in ('c0', 'fitted_c'):
        group = [r for r in rows if r['arm'] == arm]
        summary[arm] = dict(changed_positions=len(group),
            worsened=sum(r['position_error_change_km'] > 0 for r in group),
            improved=sum(r['position_error_change_km'] < 0 for r in group),
            total_mean_contribution=sum(r['predictive_mean_gain'] for r in group),
            total_covariance_contribution=sum(r['predictive_covariance_gain'] for r in group),
            worsened_despite_fixed_old_covariance_gain_above_threshold=sum(
                r['position_error_change_km'] > 0 and r['fixed_old_covariance_mean_gain'] > 2*np.log(7) for r in group))
    write(OUT / 'RF_prediction_failure_summary.json', dict(summary=summary,
        inference_unchanged=True, geographic_reference_used_only_by_reporter=True,
        interpretation='Covariance feedback accounts for substantial gains, but several worse locations also improve means at frozen incumbent covariance. Fixing covariance alone is not established as a localization solution.'))
    print(summary, flush=True)


if __name__ == '__main__':
    main()
