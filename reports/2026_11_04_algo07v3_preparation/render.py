"""Render the preparation-only ABBA measurement after checking exact comparisons."""
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def render():
    root = Path(__file__).resolve().parent
    result = json.loads((root/'benchmark.json').read_text())
    rows = result['rows']
    for row in rows:
        check = json.loads((root/f"comparison{row['trial']}.json").read_text())
        assert check['exact'] and not check['full_localization_parity']
    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(8, 4.8))
    values = [r['wall_seconds'] for r in rows]
    bars = ax.bar(x, values, color=['#8c9bac' if not r['cached'] else '#287c8e' for r in rows])
    ax.bar_label(bars, labels=[f'{v:.2f} s' for v in values], padding=5)
    ax.set_xticks(x, ['Uncached A1', 'Cached B1', 'Cached B2', 'Uncached A2'])
    ax.set_ylabel('Preparation subprocess wall time (seconds)')
    ax.set_ylim(0, max(values)*1.22)
    ax.grid(axis='y', alpha=.2)
    ax.set_axisbelow(True)
    uncached = np.mean([r['wall_seconds'] for r in rows if not r['cached']])
    cached = np.mean([r['wall_seconds'] for r in rows if r['cached']])
    ax.set_title(f'DS26-0084: exact standalone preparation, {uncached/cached:.2f}× faster\n'
                 'Same scientific outputs in all four runs; shared host')
    fig.text(.5, .025, 'Native GLRT → saved preparation. '
             'Excludes position fitting, recovery and Web UI publication.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, 1))
    fig.savefig(root/'preparation-timing.png', dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    render()
