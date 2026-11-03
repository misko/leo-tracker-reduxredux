"""Plot audited pilot accuracy and total runtime with failures explicit."""
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE/'marginal-position-v1-evaluation.json').read_text())
    baseline = {r['unit']: r for r in json.loads(
        (HERE/'regression-v1-evaluation-64.json').read_text())['rows']}
    units = list(dict.fromkeys(r['unit'] for r in data['rows']))
    rows = {(r['unit'], r['arm']): r for r in data['rows']}
    colors = ['#5c7080', '#cc8432', '#247c91']
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    x = np.arange(len(units))
    for index, (arm, label) in enumerate([
        ('baseline', 'Robust baseline'), ('profile', 'Gaussian profile'),
        ('marginal', 'Gaussian integrated'),
    ]):
        selected = [baseline[u] if arm == 'baseline' else rows[(u, arm)] for u in units]
        for axis, key in zip(axes, ['error_m', 'runtime_s'], strict=True):
            values = [r.get(key) if r['accepted'] else 0. for r in selected]
            bars = axis.bar(x+(index-1)*.25, values, width=.24, label=label, color=colors[index])
            for bar, value, row in zip(bars, values, selected, strict=True):
                text = f'{value:,.0f}' if row['accepted'] else 'FAILED'
                axis.annotate(text, (bar.get_x()+bar.get_width()/2, bar.get_height()),
                              xytext=(0, 3), textcoords='offset points', ha='center', fontsize=8)
    for axis in axes:
        axis.set_xticks(x, units)
        axis.spines[['top', 'right']].set_visible(False)
        axis.grid(axis='y', alpha=.2)
        axis.set_axisbelow(True)
        axis.margins(y=.16)
    axes[0].set_ylabel('Horizontal error (m)')
    axes[0].set_title('Three exposed development scans')
    axes[0].legend(fontsize=8)
    axes[1].set_ylabel('Total runtime including acquisition (s)')
    axes[1].axhline(90, color='#bb4444', linestyle='--', linewidth=1)
    axes[1].set_title('Same scan prior and height; hard limit 90 s')
    fig.suptitle('Shared nuisance integration pilot — no held-out accuracy claim')
    fig.savefig(HERE/'marginal-position-v1.png', dpi=170)


if __name__ == '__main__':
    main()
