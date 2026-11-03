"""Static all-five raw-policy comparison; no numerical calls or selection."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
from matplotlib import pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE/'evaluation.json').read_text())
    lookup = {(r['source_id'], r['arm'], r['method']): r for r in data['rows']}
    labels = ('S01', 'S02', 'S03', 'S04', 'S05')
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for offset, (arm, color) in enumerate((('fitted-c', '#2765ae'), ('zero-c', '#cc6b25'))):
        x = np.arange(5)+(offset-.5)*.32
        c = [lookup[label, arm, 'continuation'] for label in labels]
        a = [lookup[label, arm, 'annealing'] for label in labels]
        for ax, key, title in ((axes[0, 0], 'full', 'All-observation association change'),
                               (axes[0, 1], 'challenge', 'Diagnostic-window association change')):
            ax.bar(x, [aa[key]['associated']-cc[key]['associated']
                for aa, cc in zip(a, c, strict=True)], width=.3, color=color, label=arm)
            ax.axhline(0, color='#555555', linewidth=.7)
            ax.set(title=title, ylabel='Annealing minus expanded-bank continuation')
        for ax, metric, title, ylabel in (
            (axes[1, 0], 'associated_rms_hz', 'Associated frequency RMS', 'Hz'),
            (axes[1, 1], 'configured_reference_distance_km',
                'Configured-reference distance\n(evaluation only)', 'km')):
            for point, aa, cc in zip(x, a, c, strict=True):
                ya, yc = aa['full'][metric], cc['full'][metric]
                ax.plot([point, point], [yc, ya], color=color, linewidth=1.2)
                ax.scatter(point, yc, marker='_', color=color, s=70)
                ax.scatter(point, ya, edgecolors=color,
                    facecolors=color if aa['audit']['accepted'] else 'none', s=42)
            ax.set(title=title, ylabel=ylabel)
    for ax in axes.flat:
        ax.set_xticks(np.arange(5), labels)
        ax.title.set_fontsize(11)
        ax.grid(axis='y', alpha=.2)
    axes[0, 0].legend()
    fig.suptitle('Expanded-bank annealing: uniform all-five RAW policy\n'
        'Same selected additions and final125 likelihood; open circles = rejected endpoints')
    fig.savefig(HERE/'comparison.png', dpi=160)
    fig.savefig(HERE/'comparison.pdf')


if __name__ == '__main__':
    main()
