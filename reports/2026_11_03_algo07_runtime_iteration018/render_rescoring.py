"""Show the measured component costs of screening plus actual native rescoring."""

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    names = ['DS26', 'DS27', 'DS28']
    trials = [json.loads((ROOT / 'receipts' / (name + '.json')).read_text()) for name in names]
    baseline, screen, bound, selection, native = [], [], [], [], []
    for trial in trials:
        calls = trial['calls']
        diagnostics = [c['selection_diagnostics'][0] for c in calls]
        baseline.append(sum(c['seconds']['baseline']+c['baseline_selection_seconds']
                            for c in calls))
        screen.append(sum(c['seconds']['screen'] for c in calls))
        bound.append(sum(d['bound_seconds']+d['setup_seconds'] for d in diagnostics))
        native.append(sum(d['native_rescore_seconds'] for d in diagnostics))
        selection.append(sum(d['selector_seconds']-d['native_rescore_seconds']
                             for d in diagnostics))
    fig, ax = plt.subplots(figsize=(10, 5.4))
    bars = ax.bar([i-.2 for i in range(3)], baseline, width=.36,
                  color='#536579', label='Deployed grid + selection')
    ax.bar_label(bars, labels=[f'{x:.3f} s' for x in baseline], padding=4)
    bottom = [0., 0., 0.]
    for values, label, color in [
            (screen, 'Approximate screen', '#208774'),
            (bound, 'Bound and preparation', '#8bb5a5'),
            (selection, 'Interval selection', '#d4ae6c'),
            (native, 'Native exact rescoring', '#c96d46')]:
        bars = ax.bar([i+.2 for i in range(3)], values, bottom=bottom,
                      width=.36, color=color, label=label)
        bottom = [x+y for x, y in zip(bottom, values, strict=True)]
    ax.bar_label(bars, labels=[f'{x:.3f} s' for x in bottom], padding=4)
    ax.set(xticks=range(3), xticklabels=names, ylabel='Summed measured component wall seconds',
           ylim=(0, max(baseline)*1.35))
    ax.spines[['top', 'right']].set_visible(False)
    ax.yaxis.grid(alpha=.2)
    ax.set_axisbelow(True)
    ax.legend(ncols=2, fontsize=9, loc='upper right')
    fig.suptitle('Actual native rescoring preserves the screening opportunity')
    fig.text(.5, .025, 'Sixteen frozen windows per cohort. Requested scores bit-exact. '
             'Full detector integration remains pending.\n'
             'Bound is a research candidate; no production or end-to-end speedup claim.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .11, 1, .94))
    fig.savefig(ROOT / 'rescoring.png', dpi=160)


if __name__ == '__main__':
    main()
