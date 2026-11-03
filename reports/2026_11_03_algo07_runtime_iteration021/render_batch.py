"""Show direct incremental detector improvement separately from rescoring speed."""

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    cases = ['DS26-0046', 'DS27-0004', 'DS28-0002']
    pairs = json.loads((ROOT/'receipts/incremental/summary.json').read_text())
    native = []
    for case in cases:
        calls = json.loads((ROOT/'receipts'/f'{case}.json').read_text())['calls']
        ds = [c['selection_diagnostics'][0] for c in calls]
        native.append((sum(d['single_column_control_seconds'] for d in ds),
                       sum(d['native_rescore_seconds'] for d in ds)))
    detector = [(p['totals']['baseline'], p['totals']['candidate']) for p in pairs]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.3))
    for ax, values, title in zip(axes, (native, detector),
                                 ('Exact rescoring only', 'Complete integer-screened detector'),
                                 strict=True):
        for j, (label, color) in enumerate((('Single-column calls', '#536579'),
                                          ('Batched columns', '#208774'))):
            bars = ax.bar([i+(j-.5)*.36 for i in range(3)], [v[j] for v in values],
                          width=.36, color=color, label=label)
            ax.bar_label(bars, labels=[f'{v[j]:.3f}' for v in values], padding=3)
        ax.set(xticks=range(3), xticklabels=['DS26', 'DS27', 'DS28'],
               ylabel='Wall seconds · 16 frozen windows', title=title,
               ylim=(0, max(v[0] for v in values)*1.23))
        ax.spines[['top', 'right']].set_visible(False)
        ax.yaxis.grid(alpha=.2)
        ax.set_axisbelow(True)
        for i, (b, a) in enumerate(values):
            ax.text(i, b*1.12, f'{b/a:.2f}×', ha='center')
    fig.legend(*axes[0].get_legend_handles_labels(), loc='upper center',
               bbox_to_anchor=(.5, .94), ncols=2)
    fig.suptitle('Batching exact rescoring adds 9.7–12.3% detector speed')
    fig.text(.5, .02, 'Direct alternating comparisons; shared host. All complete detector outputs '
             'match exactly.\nResearch runtime; not deployed. '
             'Component gains are not overall gains.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .1, 1, .88))
    fig.savefig(ROOT/'batching.png', dpi=160)


if __name__ == '__main__':
    main()
