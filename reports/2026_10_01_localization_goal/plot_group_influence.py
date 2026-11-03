"""Audit largest-sensitivity checks and plot shifts without geographic truth."""
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from regression_batch import digest

HERE = Path(__file__).resolve().parent


def main():
    summary_path = HERE/'group-influence-v1-evaluation.json'
    summary = json.loads(summary_path.read_text())
    top = sorted(summary['rows'], key=lambda r: r['maximum_predicted_shift_m'], reverse=True)[:2]
    supplemental = []
    for row in top:
        path = HERE/('group-influence-worst-'+row['unit']+'.json')
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        data = json.loads(path.read_text())
        assert data['unit'] == row['unit']
        assert data['maximum_predicted_shift_m'] == row['maximum_predicted_shift_m']
        assert data['source_sha256'] == digest(HERE/'diagnose_group_influence.py')
        assert data['kernel_sha256'] == digest(
            HERE.parents[1]/'src/leo/analysis/localization_influence.py')
        parent = next((HERE/'regression-v1').glob('batch-*/'+row['unit']+'.json'))
        assert data['parent_sha256'] == digest(parent)
        supplemental.append(dict(
            unit=row['unit'], predicted_shift_m=row['maximum_predicted_shift_m'],
            receipt_sha256=digest(path),
            **{k: v for k, v in data['refit'].items() if k not in ('mean', 'objectives')}))
    output = dict(selection='Two largest predicted shifts across64, without reference access',
                  summary_sha256=digest(summary_path), source_sha256=digest(__file__),
                  checks=supplemental,
                  qualification='Warm deletion refits, not independent scan inference or errors.')
    with (HERE/'group-influence-worst-checks.json').open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), constrained_layout=True)
    colors = {'DS9': '#477fa5', 'DS10': '#c68849', 'DS11': '#508d73'}
    for dataset, color in colors.items():
        indexed = [(i, r) for i, r in enumerate(summary['rows'])
                   if r['unit'].startswith(dataset+'-')]
        axes[0].scatter([i+1 for i, r in indexed],
                        [r['maximum_predicted_shift_m']/1000 for i, r in indexed],
                        color=color, label=dataset, s=25)
    axes[0].axhline(1, linestyle='--', color='gray', linewidth=1)
    axes[0].set(xlabel='Frozen scan index', ylabel='Largest predicted deletion shift (km)',
                title='39/64 scans have predicted shifts above1km')
    axes[0].legend()
    checks = summary['nonlinear_checks']+supplemental
    limit = 1.15*max(r['observed_shift_m']/1000 for r in checks)
    axes[1].plot([0, limit], [0, limit], '--', color='gray', linewidth=1)
    for r in checks:
        x, y = r['predicted_shift_m']/1000, r['observed_shift_m']/1000
        axes[1].scatter(x, y, color=colors[r['unit'].split('-')[0]], s=40)
        axes[1].annotate(r['unit'], (x, y), xytext=(4, 4),
                         textcoords='offset points', fontsize=7)
    axes[1].set(xlim=(0, limit), ylim=(0, limit), xlabel='Predicted shift (km)',
                ylabel='Nonlinear refit shift (km)', title='Five bounded warm deletion checks')
    for axis in axes:
        axis.spines[['top', 'right']].set_visible(False)
        axis.grid(alpha=.15)
        axis.set_axisbelow(True)
    fig.suptitle('Satellite-group sensitivity: shifts, not geographic errors or confidence bounds')
    fig.savefig(HERE/'group-influence-v1.png', dpi=160)


if __name__ == '__main__':
    main()
