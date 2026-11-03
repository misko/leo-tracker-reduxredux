"""Plot excluded-dataset calibration before and after density fitting."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
baseline = json.loads((HERE/'candidate-count-calibration-v1.json').read_text())
transfer = json.loads((HERE/'candidate-density-transfer-v1.json').read_text())
fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), layout='constrained')
grid = np.linspace(0, 1, 201)
for fold, color in zip(transfer['folds'], ['#1f77b4', '#e07b16', '#289447'], strict=True):
    dataset = fold['target_dataset']
    before = np.array([s['central_probability'] for r in baseline['rows']
                       if r['unit'].startswith(dataset+'-') for s in r['samples']])
    after = np.array([p for r in fold['targets'] for p in r['central_probabilities']])
    for ax, values in zip(axes, [before, after], strict=True):
        ax.plot(grid, [(values <= q).mean() for q in grid], label=dataset, color=color)
for ax, title in zip(axes, ['Original candidate model', 'Calibration excludes target dataset'], strict=True):
    ax.plot([0, 1], [0, 1], '--', color='gray', label='Nominal coverage')
    ax.set(xlim=(0, 1), ylim=(0, 1), title=title,
           xlabel='Nominal nearest-peak coverage', ylabel='Observed coverage')
    ax.grid(alpha=.2)
axes[1].legend(loc='lower right')
fig.suptitle('Candidate-frequency calibration improves; geographic accuracy is a separate test')
fig.savefig(HERE/'candidate-density-transfer-v1.png', dpi=160)
