"""Render paired detector measurements without implying an end-to-end gain."""

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    rows = [json.loads((ROOT / 'receipts' / (name + '-paired.json')).read_text())
            for name in ('schedule', 'unroll')]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for j, (key, label, color) in enumerate([
            ('baseline', 'Deployed detector', '#536579'),
            ('candidate', 'Research probe', '#bd8542')]):
        values = [r['totals'][key] for r in rows]
        bars = ax.bar([i+(j-.5)*.34 for i in range(2)], values, width=.34,
                      color=color, label=label)
        ax.bar_label(bars, labels=[f'{v:.3f} s' for v in values], padding=4)
    ax.set(xticks=[0, 1], xticklabels=['Arrow Lake scheduling', 'Scheduling + unrolling'],
           ylabel='Detector wall seconds · 16 paired windows', ylim=(0, 17))
    ax.spines[['top', 'right']].set_visible(False)
    ax.legend()
    ax.yaxis.grid(alpha=.2)
    ax.set_axisbelow(True)
    fig.suptitle('Compiler scheduling: no material measured gain')
    fig.text(.5, .025, 'All receiver outputs exactly equal. Separate alternating trials, '
             'CPU 0, shared host.\nNeither probe deployed; '
             '1.1% gain is not established as repeatable.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .11, 1, .94))
    fig.savefig(ROOT / 'scheduling.png', dpi=160)


if __name__ == '__main__':
    main()
