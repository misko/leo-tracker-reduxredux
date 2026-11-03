"""Retain every paired phase-likelihood measurement, including the slower first pair."""

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

root = Path(__file__).resolve().parent
rows = json.loads((root/'receipts/full-phase-probe.json').read_text())['phase_timings']
fig, ax = plt.subplots(figsize=(8, 4), layout='constrained')
x = np.arange(3)
for offset, side, label in [(-.18, 'numpy', 'Separate solve + determinant'),
                            (.18, 'fused', 'Shared LU factorization')]:
    bars = ax.bar(x+offset, [r['seconds'] for r in rows if r['variant'] == side],
                  .36, label=label)
    ax.bar_label(bars, fmt='%.3f s', fontsize=9)
ax.set(xticks=x, xticklabels=['Repeat 0', 'Repeat 1', 'Repeat 2'],
       ylabel='Complete likelihood seconds', ylim=(0, 2.6),
       title='1,442,401 phase pairs per call · all scientific outputs exact')
ax.legend(loc='upper right', fontsize=9)
fig.savefig(root/'timing.png', dpi=160)
