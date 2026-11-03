"""Plot matched complete-detector window timings, separately from full-scan parity."""

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    rows = json.loads((ROOT / 'receipts/summary.json').read_text())
    fig, ax = plt.subplots(figsize=(9, 5))
    for j, (name, label, color) in enumerate([
            ('baseline', 'Deployed detector', '#536579'),
            ('candidate', 'Integrated screened detector', '#208774')]):
        values = [r['totals'][name] for r in rows]
        bars = ax.bar([i+(j-.5)*.36 for i in range(3)], values, width=.36,
                      color=color, label=label)
        ax.bar_label(bars, labels=[f'{v:.3f} s' for v in values], padding=4)
    ax.set(xticks=range(3),
           xticklabels=[r['fixture'].removeprefix('glrt-native-') for r in rows],
           ylabel='Complete detector wall seconds · 16 paired windows', ylim=(0, 19))
    ax.spines[['top', 'right']].set_visible(False)
    ax.legend()
    ax.yaxis.grid(alpha=.2)
    ax.set_axisbelow(True)
    fig.suptitle('Integrated screening · 1.16–1.17× detector improvement')
    fig.text(.5, .025, 'All 96 complete receiver outputs exactly equal, including unpublished '
             'hypotheses.\nAlternating trials, CPU 0, shared host. Research runtime; not deployed.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .11, 1, .94))
    fig.savefig(ROOT / 'detector.png', dpi=160)


if __name__ == '__main__':
    main()
