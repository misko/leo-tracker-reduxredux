"""Render complete-detector paired timings."""

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

root = Path(__file__).resolve().parent
names = ['DS26', 'DS27', 'DS28']
rows = [json.loads((root/'receipts'/f'{name}.json').read_text()) for name in names]
fig, ax = plt.subplots(figsize=(8, 4), layout='constrained')
x = np.arange(3)
for offset, side, label in [(-.18, 'baseline', 'Deployed detector'),
                            (.18, 'candidate', 'Two-epoch candidate')]:
    bars = ax.bar(x+offset, [r['totals'][side] for r in rows], .36, label=label)
    ax.bar_label(bars, fmt='%.3f s', fontsize=9)
ax.set(xticks=x, xticklabels=names, ylabel='Detector seconds', ylim=(0, 10.5),
       title='16 frozen windows per cohort · all 96 receiver outputs exact')
ax.legend(loc='upper right', fontsize=9)
fig.savefig(root/'timing.png', dpi=160)
