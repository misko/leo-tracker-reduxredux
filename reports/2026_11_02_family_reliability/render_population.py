"""Plot sealed population outcomes; no model selection or fitting."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent


def main():
    rows = list(csv.DictReader((ROOT/'population/positions.csv').open()))
    assert len(rows) == 410 and len({r['case'] for r in rows}) == 205
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    for column, arm in enumerate(('c0', 'fitted_c')):
        selected = [r for r in rows if r['arm'] == arm]
        ax = axes[0, column]
        for key, label, color in [('baseline_error_m', 'ALGO07', '#555555'),
                                  ('selected_error_m', 'Guarded SD ×4 + damping', '#287ba5')]:
            values = np.sort([float(r[key])/1000 for r in selected])
            ax.step(values, 100*np.arange(1, len(values)+1)/len(values), where='post', label=label, color=color)
        ax.set(title=arm, xlabel='Position error (km)', ylabel='Scans at or below error (%)', ylim=(0, 101))
        ax.grid(alpha=.2); ax.legend(fontsize=9)
        ax = axes[1, column]
        changed = sorted([r for r in selected if r['accepted'] == 'True'],
                         key=lambda r: float(r['selected_minus_baseline_m']))
        delta = np.array([float(r['selected_minus_baseline_m'])/1000 for r in changed])
        colors = ['#287ba5' if x <= 0 else '#c25a46' for x in delta]
        ax.bar(range(len(changed)), delta, color=colors)
        for i, row in enumerate(changed):
            if row['development'] == 'True':
                ax.scatter(i, delta[i], marker='*', s=110, color='black', zorder=3)
        ax.axhline(0, color='black', lw=.8)
        ax.set(title=f'{len(changed)} accepted changes; stars mark development scans',
               xlabel='Changed scans ordered by error change', ylabel='Candidate − ALGO07 error (km)')
        ax.grid(alpha=.2, axis='y')
    fig.suptitle('All 205 recent scans: RF decisions sealed before geographic comparison\n'
                 'Negative changes improve accuracy; unchanged fallbacks remain in the CDF', fontsize=12)
    fig.savefig(ROOT/'population_error_distributions.png', dpi=170)
    plt.close(fig)


if __name__ == '__main__':
    main()
