"""Draw exact descent histories and the separately bounded ABBA timing."""
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def render():
    root = Path(__file__).resolve().parent
    data = json.loads((root/'descent-curves.json').read_text())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3))
    for ax, arm in zip(axes, ('c0', 'fitted_c'), strict=True):
        for side, style in (('reference', '-'), ('candidate', '--')):
            values = data[side][arm]
            ax.plot(values, style, label=side, linewidth=2)
        ax.axvline(8.5, color='gray', linestyle=':', label='phase refresh')
        ax.set_title(arm)
        ax.set_xlabel('Recorded optimizer states across two phase rounds')
        ax.set_ylabel('Frequency / prior objective')
        ax.grid(alpha=.2)
        ax.legend()
    fig.suptitle('DS26-0084: exact descent for one independently nominated test hypothesis')
    fig.text(.5, .015, 'Eight iterations per phase round. This is not the full production search.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, .95))
    fig.savefig(root/'descent-parity.png', dpi=160)
    plt.close(fig)
    bench = json.loads((root/'benchmark.json').read_text())
    fig, ax = plt.subplots(figsize=(8, 4.5))
    values = [r['wall_seconds'] for r in bench['rows']]
    bars = ax.bar(np.arange(4), values, color=['#8c9bac', '#287c8e', '#287c8e', '#8c9bac'])
    ax.bar_label(bars, labels=[f'{v:.2f} s' for v in values], padding=4)
    ax.set_xticks(range(4), ['Reference A1', 'V3 B1', 'V3 B2', 'Reference A2'])
    ax.set_ylim(0, max(values)*1.18)
    ax.set_ylabel('Subprocess wall time (seconds)')
    ax.set_title('DS26-0084 bounded position workload, same CPU, exact outputs')
    ax.grid(axis='y', alpha=.2)
    ax.set_axisbelow(True)
    fig.text(.5, .015, 'Both arms; one phase round × four iterations. '
             'Excludes full search/recovery/UI.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, 1))
    fig.savefig(root/'position-timing.png', dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    render()
