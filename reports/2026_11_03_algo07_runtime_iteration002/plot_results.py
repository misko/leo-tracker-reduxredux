"""Render measured numerical speedups without implying a whole-pipeline gain."""

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
baseline = json.loads((ROOT/'replay-baseline/timing.json').read_text())
candidate = json.loads((ROOT/'replay-contractions/timing.json').read_text())
sa = json.loads((ROOT/'replay-baseline/results/summary.json').read_text())
sb = json.loads((ROOT/'replay-contractions/results/summary.json').read_text())
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
for ax, label, values in [
    (axes[0], 'Full ALGO07 numerical worker\n(prepared native inputs → decision)',
     [baseline['wall_seconds'], candidate['wall_seconds']]),
    (axes[1], 'Two-family integration within that worker\n(436 calls in each run)',
     [sa['kernel_seconds'], sb['kernel_seconds']]),
]:
    ax.bar(['Baseline', 'BLAS contractions'], values, color=['#426b9a', '#dc8b35'])
    for i, value in enumerate(values):
        ax.text(i, value+max(values)*.025, f'{value:.1f} s', ha='center')
    ax.set_ylim(0, max(values)*1.2)
    ax.set_ylabel('Seconds')
    ax.set_title(label+f'\n{values[0]/values[1]:.2f}× faster')
    ax.grid(axis='y', alpha=.2)
    ax.set_axisbelow(True)
fig.suptitle('ALGO07 runtime iteration 002 — slow DS28-0015-equivalent case\n'
             'Same 4,267 scientific values; excludes upstream GLRT and ALGO02–06', fontsize=12)
fig.savefig(ROOT/'numerical_runtime.png', dpi=160)
plt.close(fig)
rows = sorted(json.loads((ROOT/'population-reconstruction.json').read_text())['results'],
              key=lambda r:r['case'])
fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
x = np.arange(len(rows))
ax.bar(x-.18, [r['baseline_kernel_seconds'] for r in rows], .36,
       label='Reference', color='#426b9a')
ax.bar(x+.18, [r['candidate_kernel_seconds'] for r in rows], .36,
       label='Candidate', color='#dc8b35')
ax.set_xticks(x, [r['case'] for r in rows], rotation=55, ha='right')
ax.set_ylabel('Seconds spent in two-family integration')
ax.set_title('All 16 two-family incumbents pass paired reconstruction\n'
             '96 calls; validation timings under four-worker concurrency, not isolated benchmarks')
ax.grid(axis='y', alpha=.2)
ax.set_axisbelow(True)
ax.legend()
fig.savefig(ROOT/'population_kernel_times.png', dpi=160)
