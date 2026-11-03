"""Plot direct paired coarse-kernel timings, without a whole-detector claim."""

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

root = Path(__file__).resolve().parent
names = ['DS26', 'DS27', 'DS28']
rows = [json.loads((root/'receipts'/f'{name}.json').read_text()) for name in names]
x = np.arange(3)
fig, ax = plt.subplots(figsize=(8, 4), layout='constrained')
for offset, side, label in [(-.18, 'baseline', 'Original integer screen'),
                            (.18, 'candidate', 'Two-epoch reuse')]:
    bars = ax.bar(x+offset, [r['totals'][side] for r in rows], .36, label=label)
    ax.bar_label(bars, fmt='%.3f s', fontsize=9)
ax.set(xticks=x, xticklabels=names, ylabel='Coarse-grid seconds', ylim=(0, 1.4),
       title='Research probe: four frozen windows per cohort\n'
             'Alternating grid calls; not whole-detector timing')
ax.legend(loc='upper left', fontsize=9)
fig.savefig(root/'timing.png', dpi=160)
