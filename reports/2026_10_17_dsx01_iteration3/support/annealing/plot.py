"""Plot the single all-five raw policy, without selecting per-source methods."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
from matplotlib import pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE/'uniform_evaluation.json').read_text())
    rows = {(r['source_id'], r['arm'], r['method']): r for r in data['rows']}
    labels = ('S01', 'S02', 'S03', 'S04', 'S05')
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for offset, (arm, color) in enumerate((('fitted-c', '#2765ae'), ('zero-c', '#cc6b25'))):
        x = np.arange(5)+(offset-.5)*.32
        control = [rows[label, arm, 'continuation'] for label in labels]
        anneal = [rows[label, arm, 'annealing'] for label in labels]
        for ax, key, title in ((axes[0, 0], 'full', 'All-observation association change'),
                               (axes[0, 1], 'challenge', 'Diagnostic-window association change')):
            delta = [a[key]['associated']-b[key]['associated']
                     for a, b in zip(anneal, control, strict=True)]
            ax.bar(x, delta, width=.3, color=color, label=arm)
            ax.axhline(0, color='#555555', linewidth=.7)
            ax.set_title(title)
            ax.set_ylabel('Annealing minus matched continuation')
        for ax, metric, title, ylabel in (
            (axes[1, 0], 'associated_rms_hz', 'Associated frequency RMS', 'Hz'),
            (axes[1, 1], 'configured_reference_distance_km',
             'Configured-reference distance (evaluation only)', 'km')):
            for point, a, b in zip(x, anneal, control, strict=True):
                ya, yb = a['full'][metric], b['full'][metric]
                ax.plot([point, point], [yb, ya], color=color, linewidth=1.2)
                ax.scatter(point, yb, marker='_', color=color, s=70)
                ax.scatter(point, ya, marker='o', edgecolors=color,
                    facecolors=color if a['audit']['accepted'] else 'none', s=42)
            ax.set_title(title)
            ax.set_ylabel(ylabel)
    for ax in axes.flat:
        ax.set_xticks(np.arange(5), labels)
        ax.grid(axis='y', alpha=.2)
    axes[0, 0].legend()
    fig.suptitle('Fixed-width annealing vs 125 Hz continuation: all-five RAW policy\n'
        'Same fixed banks; final125 objective only; '
        'open circles = nonstationary annealing endpoints')
    fig.savefig(HERE/'uniform_comparison.png', dpi=160)
    fig.savefig(HERE/'uniform_comparison.pdf')


if __name__ == '__main__':
    main()
