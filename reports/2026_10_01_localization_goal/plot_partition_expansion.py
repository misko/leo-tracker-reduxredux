"""Paired independent-scan error and runtime for the frozen12-scan pilot."""
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    result = json.loads((HERE/'partition-expansion-v1-evaluation.json').read_text())
    rows = result['rows']
    fig, (left, right) = plt.subplots(1, 2, figsize=(12, 6), layout='constrained')
    for i, row in enumerate(rows):
        if row['accepted']:
            a, b = row['baseline_error_m'], row['error_m']
            left.plot([a, b], [i, i], color='#999999', zorder=1)
            left.scatter(a, i, color='#666666', marker='o', label='Baseline' if i == 0 else None)
            left.scatter(b, i, color='#007c91', marker='D',
                         label='Detector-margin selection' if i == 0 else None)
        else:
            left.text(0, i, 'Failed', color='red')
        right.barh(i, row['runtime_s'], color='#007c91')
    left.set_yticks(range(len(rows)), [r['unit'] for r in rows])
    left.set_xlabel('Horizontal error (m)')
    left.axvline(1000, color='green', ls=':', label='1,000 m target')
    left.legend(loc='best', fontsize=8)
    right.set_yticks(range(len(rows)), [r['unit'] for r in rows])
    right.set_xlabel('Total wall time including acquisition (s)')
    right.axvline(90, color='red', ls=':', label='Hard 90 s limit')
    right.legend(fontsize=8)
    for ax in (left, right):
        ax.invert_yaxis()
        ax.grid(axis='x', alpha=.2)
    fig.suptitle('Unchanged track-selection heuristic: 12 development scans\n'
                 'Independent Sacramento prior; 100 ft MSL; no held-out claim')
    fig.savefig(HERE/'partition-expansion-v1.png', dpi=160)


if __name__ == '__main__':
    main()
