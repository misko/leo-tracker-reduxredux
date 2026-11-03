"""Render the saved conditional controls without repeating scientific scoring."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE/'receipt.json').read_text())['summary']
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
for axis, model in zip(axes, ['half-forecast', 'blocked-interpolation']):
    selected = [r for r in rows if r['model']==model]
    x = np.arange(len(selected))
    actual = [100*r['actual_assigned']/r['denominator'] for r in selected]
    mean = [100*r['null_mean_assigned']/r['denominator'] for r in selected]
    lower = [100*(r['null_mean_assigned']-r['null_min_assigned'])/r['denominator'] for r in selected]
    upper = [100*(r['null_max_assigned']-r['null_mean_assigned'])/r['denominator'] for r in selected]
    axis.bar(x-.18, actual, width=.36, color='#0072B2', label='Actual held CFO')
    axis.bar(x+.18, mean, width=.36, color='#999999', label='Permuted held CFO',
        yerr=np.array([lower, upper]), capsize=4)
    for i, row in enumerate(selected):
        axis.text(i-.18, actual[i]+2, f"{row['actual_assigned']}/{row['denominator']}", ha='center', fontsize=9)
    axis.set_xticks(x, ['Whole held set', 'Requested held windows'])
    axis.set(title=model, ylabel='Assigned fraction (%)', ylim=(0, 100))
    axis.grid(axis='y', alpha=.2)
axes[0].legend(fontsize=8)
fig.suptitle('Frozen S03 predictors: temporal alignment versus within-RX/channel CFO permutations\n32 controls; whiskers show range. Different cohorts; not a controlled causal comparison.')
fig.savefig(HERE/'conditional-controls.png', dpi=160)
plt.close(fig)
