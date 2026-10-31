"""Plot sealed reporting rows; never used for inference or acceptance."""
from pathlib import Path
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent / 'report-draft'
rows = list(csv.DictReader((ROOT / 'per-case.csv').open()))
cases = sorted({r['case'] for r in rows if r['added_associated'] and int(r['added_associated']) > 0})
fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), layout='constrained')
x = np.arange(len(cases))
control = {r['case']: r for r in rows if r['arm'] == 'c0'}
counts = [int(control[c]['added_associated']) for c in cases]
axes[0].bar(x, counts, color='#326ca8')
for i, n in enumerate(counts):
    axes[0].text(i, n + 1, str(n), ha='center')
axes[0].set(ylabel='Additional associated GLRT points', ylim=(0, 85), title='299 points recovered; same IDs in both c arms')
for arm, shift, color, label in [('c0', -.18, '#326ca8', 'c = 0'), ('fitted_c', .18, '#d97920', 'Fitted c')]:
    by_case = {r['case']: r for r in rows if r['arm'] == arm}
    delta = [1000 * float(by_case[c]['delta_error_km']) for c in cases]
    axes[1].bar(x + shift, delta, width=.35, color=color, label=label)
axes[1].axhline(0, color='black', linewidth=.8)
axes[1].set(ylabel='Position error change (m; negative improves)', title='Additional evidence has mixed position effects')
axes[1].legend()
for ax in axes:
    ax.set_xticks(x, [c.removeprefix('DS26-') for c in cases])
    ax.set_xlabel('DS26 scan')
    ax.grid(axis='y', alpha=.2)
fig.savefig(ROOT / 'recovery-cases.png', dpi=160)
fig.savefig(ROOT / 'recovery-cases.pdf')
