"""One-source pilot display, retaining rejected baseline endpoints."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
from matplotlib import pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE/'pilot_evaluation.json').read_text())
    rows = {(r['family'], r['arm'], r['method']): r for r in data['rows']}
    conditions = [('fitted-c', 'continuation'), ('fitted-c', 'profile'),
                  ('zero-c', 'continuation'), ('zero-c', 'profile')]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for offset, (family, color) in enumerate((('scalar2', '#3979b2'), ('age', '#df8c33'))):
        x = np.arange(4)+(offset-.5)*.32
        selected = [rows[family, arm, method] for arm, method in conditions]
        panels = [(axes[0, 0], [r['full']['associated'] for r in selected],
                   'All associated / 3988', 'observations'),
                  (axes[0, 1], [r['challenge']['associated'] for r in selected],
                   'Diagnostic associated / 138', 'observations'),
                  (axes[1, 0], [r['full']['configured_reference_distance_km'] for r in selected],
                   'Configured-reference distance (evaluation only)', 'km'),
                  (axes[1, 1], [r['full']['relative_timing_rms_s'] for r in selected],
                   'Relative timing RMS', 'seconds')]
        for ax, values, title, unit in panels:
            bars = ax.bar(x, values, width=.3, color=color, label=family)
            for bar, row in zip(bars, selected, strict=True):
                if not row['audit']['accepted']:
                    bar.set_hatch('///')
                    bar.set_alpha(.45)
            ax.set_title(title, fontsize=10)
            ax.set_ylabel(unit)
    for ax in axes.flat:
        ax.set_xticks(np.arange(4), ['fitted-c\ncontinue', 'fitted-c\nprofile',
                                    'c=0\ncontinue', 'c=0\nprofile'])
        ax.grid(axis='y', alpha=.2)
    axes[0, 0].legend()
    fig.suptitle('S03 conservative age-prior sensitivity: matched warm starts\n'
                 'Common clock3s unchanged; hatching = strict KKT rejection; no promotion')
    fig.savefig(HERE/'pilot_comparison.png', dpi=160)
    fig.savefig(HERE/'pilot_comparison.pdf')


if __name__ == '__main__':
    main()
