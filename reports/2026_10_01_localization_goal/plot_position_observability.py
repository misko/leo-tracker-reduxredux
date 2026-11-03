"""Display local information retained after freeing nuisance parameters."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE/'position-observability-v1.json').read_text())['rows']
x = np.arange(len(rows))
values = np.array([r['free_vs_prior_retention'] for r in rows])*100
fig, ax = plt.subplots(figsize=(10, 4.5), layout='constrained')
ax.vlines(x, values[:, 0], values[:, 1], color='#aaaaaa', linewidth=3)
ax.scatter(x, values[:, 0], label='Least retained direction', color='#287fa9')
ax.scatter(x, values[:, 1], label='Most retained direction', color='#e07b16')
ax.set(xticks=x, xticklabels=[r['unit'] for r in rows], ylim=(0, 105),
       ylabel='Information retained without nuisance priors (%)',
       title='Local baseline geometry retains position information\nFixed identities and IRLS weights; not calibrated uncertainty')
ax.tick_params(axis='x', rotation=45)
ax.legend(loc='lower right')
ax.grid(axis='y', alpha=.2)
fig.savefig(HERE/'position-observability-v1.png', dpi=160)
