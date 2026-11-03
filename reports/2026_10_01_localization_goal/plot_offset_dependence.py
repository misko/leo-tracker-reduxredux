"""Display matched and independently calibrated controls on excluded datasets."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
data = json.loads((HERE/'offset-dependence-transfer-v2.json').read_text())
rows = [r for fold in data['folds'] for r in fold['rows']]
x = np.arange(len(rows))
fig, ax = plt.subplots(figsize=(10, 4.5), layout='constrained')
ax.bar(x-.18, [r['shared_minus_matched'] for r in rows], width=.36,
       label='Shared minus control with same parameters', color='#e07b16')
ax.bar(x+.18, [r['shared_minus_calibrated_control'] for r in rows], width=.36,
       label='Shared minus separately calibrated control', color='#287fa9')
ax.axhline(0, color='black', linewidth=.8)
ax.set(xticks=x, xticklabels=[r['unit'] for r in rows],
       ylabel='Change in log density (nats / candidate group)',
       title='Shared track offsets: calibration excludes the target dataset')
ax.tick_params(axis='x', rotation=45)
ax.legend(fontsize=8)
ax.grid(axis='y', alpha=.2)
fig.savefig(HERE/'offset-dependence-transfer-v2.png', dpi=160)
