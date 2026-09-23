"""Display the central error distribution without changing full-sample normalization."""
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

root = Path(__file__).resolve().parent
groups = defaultdict(list)
with (root / 'position-errors.csv').open() as stream:
    for row in csv.DictReader(stream):
        groups[(row['prior'], float(row['sample_rate_msps']))].append(float(row['selected_error_km']))

colors = {2.5: '#0072B2', 10: '#D55E00', 15: '#009E73'}
styles = {2.5: '-', 10: '--', 15: ':'}
bins = np.arange(0, 55, 5)
fig, axes = plt.subplots(1, 2, figsize=(12, 5.3), sharex=True, sharey=True, layout='constrained')
for ax, prior in zip(axes, ('sacramento', 'reno'), strict=True):
    for rate, color in colors.items():
        values = np.asarray(groups[(prior, rate)])
        counts, _ = np.histogram(values, bins=bins)
        hidden = int(np.sum(values > 50))
        assert counts.sum() + hidden == len(values)
        density = counts / (len(values) * np.diff(bins))
        assert np.isclose(np.sum(density * np.diff(bins)), (len(values) - hidden) / len(values))
        ax.stairs(density, bins, color=color, linewidth=2.5, linestyle=styles[rate],
                  label=f'{rate:g} MS/s · n={len(values)} · {hidden} beyond 50 km')
        ax.stairs(density, bins, color=color, fill=True, alpha=.045)
    ax.set(title=f'{prior.title()} prior', xlim=(0, 50), ylim=(0, .14),
           xlabel='Horizontal error to true position (km)', ylabel='Density (1/km)')
    ax.set_xticks(np.arange(0, 51, 5))
    ax.grid(alpha=.2)
    ax.set_axisbelow(True)
    ax.legend(fontsize=9, loc='upper right')
fig.suptitle('All-track position error · focused view, 0–50 km\n'
             'Same pre-rotation eight-hour window · 5 km histogram bins', fontsize=15)
fig.supxlabel('Outliers remain in the normalization; they are hidden from this view only. '
              '45 recordings with results; 3 pending.\n'
              '23 Sep 2026, 06:39:14–14:39:14 UTC · original 100 km starting grid', fontsize=9)
fig.savefig(root / 'position-error-density-focused.png', dpi=180)
fig.savefig(root / 'position-error-density-focused.pdf')
print(root / 'position-error-density-focused.png')
