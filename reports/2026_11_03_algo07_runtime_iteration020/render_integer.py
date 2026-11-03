"""Plot measured component and detector costs without extrapolating end-to-end gains."""

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    cases = ['DS26', 'DS27', 'DS28']
    trials = [json.loads((ROOT / 'receipts' / (c+'.json')).read_text()) for c in cases]
    paired = json.loads((ROOT / 'receipts/paired-summary.json').read_text())
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4))
    component, detector = [], []
    for trial, pair in zip(trials, paired, strict=True):
        calls = trial['calls']
        ds = [r['selection_diagnostics'][0] for r in calls]
        b = sum(r['seconds']['baseline']+r['baseline_selection_seconds'] for r in calls)
        a = sum(r['seconds']['screen'] for r in calls) + sum(
            d['bound_seconds']+d['setup_seconds']+d['selector_seconds'] for d in ds)
        component.append((b, a))
        detector.append((pair['totals']['baseline'], pair['totals']['candidate']))
    for ax, values, title in zip(axes, (component, detector),
                                 ('Coarse search components', 'Whole detector'), strict=True):
        for j, (label, color) in enumerate((('Deployed FP64', '#536579'),
                                          ('Integer screen + exact rescoring', '#208774'))):
            bars = ax.bar([i+(j-.5)*.36 for i in range(3)],
                          [v[j] for v in values], width=.36, label=label, color=color)
            ax.bar_label(bars, labels=[f'{v[j]:.2f}' for v in values], padding=3)
        ax.set(xticks=range(3), xticklabels=cases, ylabel='Wall seconds · 16 frozen windows',
               title=title, ylim=(0, max(v[0] for v in values)*1.25))
        ax.spines[['top', 'right']].set_visible(False)
        ax.yaxis.grid(alpha=.2)
        ax.set_axisbelow(True)
        for i, (b, a) in enumerate(values):
            ax.text(i, b*1.12, f'{b/a:.2f}×', ha='center')
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', ncols=2, bbox_to_anchor=(.5, .94))
    fig.suptitle('Integer dot products accelerate the complete screened detector')
    fig.text(.5, .015, 'Separate alternating trials on a shared host. All 96 complete detector '
             'outputs match exactly.\nResearch runtime; not deployed. '
             'These are not end-to-end timings.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .10, 1, .88))
    fig.savefig(ROOT / 'integer-screen.png', dpi=160)
    summary = [dict(case=c, component_baseline=b, component_candidate=a,
                    component_ratio=b/a, detector_baseline=db, detector_candidate=da,
                    detector_ratio=db/da)
               for c, (b, a), (db, da) in zip(cases, component, detector, strict=True)]
    (ROOT / 'receipts/timing-summary.json').write_text(json.dumps(summary, indent=2)+'\n')


if __name__ == '__main__':
    main()
