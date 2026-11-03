"""Paired accuracy plot for the audited scale expansion."""
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE/'student-scale-expansion-v1-evaluation-12.json').read_text())
    assert data['finished'] == data['planned'] == 12
    rows = sorted(data['rows'], key=lambda r: r['unit'])
    valid = [r for r in rows if r['accepted']]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    colors = {'DS9': '#4376a2', 'DS10': '#cf853e', 'DS11': '#508f78'}
    maximum = max(max(r['baseline_error_m'], r['error_m']) for r in valid)*1.1
    for dataset, color in colors.items():
        group = [r for r in valid if r['unit'].startswith(dataset+'-')]
        axes[0].scatter([r['baseline_error_m'] for r in group],
                        [r['error_m'] for r in group], label=dataset, color=color, s=50)
    axes[0].plot([0, maximum], [0, maximum], '--', color='gray', linewidth=1)
    axes[0].set(xlim=(0, maximum), ylim=(0, maximum),
                xlabel='Baseline error (m)', ylabel='Larger-scale Student-t error (m)',
                title='Below diagonal = improvement')
    axes[0].legend()
    x = np.arange(len(rows))
    axes[1].barh(x, [r.get('change_m', 0.) for r in rows],
                 color=[colors[r['unit'].split('-')[0]] for r in rows])
    axes[1].set_yticks(x, [r['unit']+(' FAILED' if not r['accepted'] else '') for r in rows])
    axes[1].axvline(0, color='gray', linewidth=1)
    axes[1].set(xlabel='Change in error (m); negative = better',
                title=f"{data['improved']}/12 improved; {data['accepted']}/12 accepted")
    for axis in axes:
        axis.spines[['top', 'right']].set_visible(False)
        axis.grid(alpha=.15)
        axis.set_axisbelow(True)
    fig.suptitle('Fixed Student-t scale expansion: 12 additional development scans')
    fig.savefig(HERE/'student-scale-expansion-v1.png', dpi=160)


if __name__ == '__main__':
    main()
