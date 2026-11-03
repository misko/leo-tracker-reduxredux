"""Compare two fixed modifications against the same twelve-scan baseline."""
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    shared = json.loads((HERE/'shared-scale-expansion-v1-evaluation-12.json').read_text())
    global_scale = json.loads((HERE/'student-scale-expansion-v1-evaluation-12.json').read_text())
    assert shared['finished'] == global_scale['finished'] == 12
    rows = sorted(shared['rows'], key=lambda r: r['unit'])
    controls = {r['unit']: r for r in global_scale['rows']}
    x = np.arange(len(rows))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4), constrained_layout=True)
    for offset, source, color, label in [
        (-.19, [controls[r['unit']] for r in rows], '#ae8a5c', 'Global scale ×2'),
        (.19, rows, '#347f8d', 'Shared scale by satellite'),
    ]:
        axes[0].barh(x+offset, [r.get('change_m', 0.) for r in source], height=.36,
                     color=color, label=label)
    axes[0].set_yticks(x, [r['unit']+(' FAILED' if not r['accepted'] else '') for r in rows])
    axes[0].axvline(0, color='gray', linewidth=1)
    axes[0].set(xlabel='Change from baseline error (m); negative = better',
                title='Exact same12 additional development scans')
    axes[0].legend(fontsize=8)
    labels = ['Baseline', 'Global ×2', 'Shared']
    median = [shared['paired_baseline_median_error_m'], global_scale['median_error_m'],
              shared['median_error_m']]
    p90 = [shared['paired_baseline_p90_error_m'], global_scale['p90_error_m'],
           shared['p90_error_m']]
    for offset, values, color, label in [(-.18, median, '#5b6e85', 'Median'),
                                       (.18, p90, '#b37262', 'p90')]:
        bars = axes[1].bar(np.arange(3)+offset, values, width=.35, color=color, label=label)
        axes[1].bar_label(bars, fmt='%.0f', padding=3, fontsize=9)
    axes[1].set_xticks(np.arange(3), labels)
    axes[1].set(ylabel='Horizontal error (m)',
                title=f"Shared: {shared['improved']}/12 improved; {shared['accepted']}/12 accepted")
    axes[1].legend()
    axes[1].margins(y=.17)
    for axis in axes:
        axis.spines[['top', 'right']].set_visible(False)
        axis.grid(alpha=.15)
        axis.set_axisbelow(True)
    fig.suptitle('Shared residual uncertainty — development comparison, not held-out validation')
    fig.savefig(HERE/'shared-scale-expansion-v1.png', dpi=160)


if __name__ == '__main__':
    main()
