"""Compare paired geographic errors for the fixed12development panel."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
result = json.loads((HERE/'calibrated-joint-panel-v1.json').read_text())
rows = result['rows']
x = np.arange(len(rows))
fig, ax = plt.subplots(figsize=(11, 4.5), layout='constrained')
for shift, key, label, color in [(-.25, 'original_all_data_error_m', 'All-data baseline', '#808080'),
    (0, 'uncalibrated_joint_error_m', 'Uncalibrated joint refit', '#e07b16'),
    (.25, 'calibrated_joint_error_m', 'Calibrated joint refit', '#287fa9')]:
    ax.bar(x+shift, [r[key] if r[key] is not None else np.nan for r in rows],
           width=.24, label=label, color=color)
ax.axhline(1000, color='black', linestyle=':', linewidth=1)
ax.set(xticks=x, xticklabels=[r['unit'] for r in rows], ylabel='Horizontal reference error (m)',
       title='Calibrated candidate likelihood: 12 independent development scans')
ax.tick_params(axis='x', rotation=45)
ax.legend()
ax.grid(axis='y', alpha=.2)
fig.savefig(HERE/'calibrated-joint-panel-v1.png', dpi=160)
