"""Display predictive calibration at sealed training-only location estimates."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
data = json.loads((HERE/'candidate-count-calibration-v1.json').read_text())
fig, ax = plt.subplots(figsize=(7, 5), layout='constrained')
colors = {'DS9': '#1f77b4', 'DS10': '#e07b16', 'DS11': '#289447'}
grid = np.linspace(0, 1, 201)
for dataset, color in colors.items():
    samples = np.array([s['central_probability'] for r in data['rows']
                        if r['unit'].startswith(dataset+'-') for s in r['samples']])
    ax.plot(grid, [(samples <= q).mean() for q in grid], color=color,
            label=f'{dataset}: {len(samples):,} groups')
ax.plot([0, 1], [0, 1], '--', color='gray', label='Assumed model')
ax.set(xlim=(0, 1), ylim=(0, 1), xlabel='Model probability of nearest-peak region',
       ylabel='Observed fraction inside region',
       title='Candidate frequency model is poorly calibrated\n12 development scans; training-only predictions')
ax.legend(loc='lower right')
ax.grid(alpha=.2)
fig.savefig(HERE/'candidate-count-calibration-v1.png', dpi=160)
