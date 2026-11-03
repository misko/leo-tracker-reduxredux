"""Plot screening feasibility separately from unmeasured exact-rescoring cost."""

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    names = ['DS26', 'DS27', 'DS28']
    rows = [json.loads((ROOT / 'receipts' / (name + '.json')).read_text()) for name in names]
    fig, (left, right) = plt.subplots(1, 2, figsize=(12, 5))
    for j, (key, label, color) in enumerate([
            ('baseline', 'Deployed FP64 grid', '#536579'),
            ('screen', 'FP32 screen only', '#208774')]):
        values = [r['summary']['totals'][key] for r in rows]
        bars = left.bar([i+(j-.5)*.35 for i in range(3)], values, width=.35,
                        label=label, color=color)
        left.bar_label(bars, labels=[f'{v:.2f}' for v in values], padding=3)
    left.set(xticks=range(3), xticklabels=names, ylabel='Coarse-grid wall seconds', ylim=(0, 14))
    left.legend(fontsize=9)
    left.set_title('Measured kernel work · 16 windows per cohort')
    for j, (epsilon, color) in enumerate([(1e-5, '#508bbb'), (1e-4, '#c28c43')]):
        values = []
        for row in rows:
            diagnostics = [call['selection_diagnostics'][j] for call in row['calls']]
            values.append(100*sum(d['exact_columns'] for d in diagnostics) /
                          sum(d['total_columns'] for d in diagnostics))
        bars = right.bar([i+(j-.5)*.35 for i in range(3)], values, width=.35,
                         label=f'Assumed error ±{epsilon:g}', color=color)
        right.bar_label(bars, labels=[f'{v:.3f}%' for v in values], padding=3, fontsize=9)
    right.set(xticks=range(3), xticklabels=names,
              ylabel='Epoch columns requested for exact scores (%)')
    right.set_ylim(0, max(right.get_ylim()[1], .27))
    right.set_title('Conditional selector · exact scores supplied by baseline')
    right.legend(fontsize=9)
    for ax in (left, right):
        ax.spines[['top', 'right']].set_visible(False)
        ax.yaxis.grid(alpha=.2)
        ax.set_axisbelow(True)
    fig.suptitle('Coarse screening is promising; it is not qualified for inference')
    fig.text(.5, .025, 'All tested selections exact after oracle lookup. '
             'Native rescoring and general error bounds remain unimplemented.\n'
             'Alternating grid calls, CPU 0, shared host. '
             'No production or end-to-end speedup claim.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .12, 1, .93))
    fig.savefig(ROOT / 'screening.png', dpi=160)


if __name__ == '__main__':
    main()
