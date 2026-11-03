"""Show ranking changes against the original all-data reference algorithm."""
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    doc = json.loads((HERE/'checking-expansion-v1-evaluation.json').read_text())
    rows = doc['rows']
    fig, (left, right) = plt.subplots(1, 2, figsize=(13, 7), layout='constrained')
    for i, r in enumerate(rows):
        left.scatter(r['all_data_baseline_error_m'], i, color='#777777', marker='o',
                     label='Original all-data baseline' if i == 0 else None)
        if not r['accepted']:
            left.text(0, i, 'Failed', color='red')
            continue
        a, b = r['training_error_m'], r['checking_error_m']
        left.plot([a, b], [i, i], color='#007c91', alpha=.7)
        left.scatter(a, i, facecolors='none', edgecolors='#007c91', marker='s',
                     label='Split: training-selected' if i == 0 else None)
        left.scatter(b, i, color='#e58121', marker='D',
                     label='Split: checking-selected' if i == 0 else None)
        fit, score = r['training_fit_runtime_s'], r['scoring_seconds']
        pre = r['preprocessing_seconds']
        right.barh(i, fit, color='#007c91', label='Localization' if i == 0 else None)
        right.barh(i, score, left=fit, color='#e58121', label='Checking score' if i == 0 else None)
        right.barh(i, pre, left=fit+score, color='#cccccc',
                   label='Track preprocessing' if i == 0 else None)
    for ax in (left, right):
        ax.set_yticks(range(len(rows)), [r['unit'] for r in rows])
        ax.invert_yaxis()
        ax.grid(axis='x', alpha=.2)
        ax.legend(fontsize=8)
    left.axvline(1000, color='green', ls=':', alpha=.6)
    left.set_xlabel('Horizontal error (m)')
    right.set_xlabel('Separately measured phase times (s); sum is not an integrated run')
    right.axvline(90, color='red', ls=':')
    fig.suptitle('Candidate-set ranking on 12 fixed development scans\n'
                 'Checking visits excluded before track construction; no held-out recording claim')
    fig.savefig(HERE/'checking-expansion-v1.png', dpi=160)


if __name__ == '__main__':
    main()
