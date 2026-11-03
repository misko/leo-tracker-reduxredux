"""Full frozen64 accuracy comparison; empirical fractions retain failures."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from regression_batch import digest

HERE = Path(__file__).resolve().parent
path = HERE/'balanced-group-regression64-v1.json'
assert digest(path) == path.with_suffix('.sha256').read_text().strip()
result = json.loads(path.read_text())
rows = result['rows']
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
for name, field in [('Original baseline', 'baseline_error_m'), ('Satellite-balanced', 'error_m')]:
    values = sorted(r[field] for r in rows if r[field] is not None)
    axes[0].step(values, np.arange(1, len(values)+1)/64, where='post', label=name)
axes[0].set(xlabel='Horizontal error (m)', ylabel='Fraction of all64 scans', ylim=(0, 1))
axes[0].axvline(1000, color='gray', ls=':')
axes[0].axvline(3000, color='gray', ls=':')
axes[0].legend()
limit = max(max(r['baseline_error_m'], r['error_m'] or 0) for r in rows)*1.05
for ds in ['DS9', 'DS10', 'DS11']:
    chosen = [r for r in rows if r['unit'].startswith(ds+'-') and r['accepted']]
    axes[1].scatter([r['baseline_error_m'] for r in chosen], [r['error_m'] for r in chosen], label=ds)
axes[1].plot([0, limit], [0, limit], color='gray', ls=':')
axes[1].set(xlabel='Baseline error (m)', ylabel='Balanced error (m)', xlim=(0, limit), ylim=(0, limit))
axes[1].legend()
fig.suptitle('Frozen64: unchanged satellite-balanced score, warm refits\n'
             'Below diagonal = improved; no cold-runtime or held-out claim')
fig.savefig(HERE/'balanced-group-regression64-v1.png', dpi=150)
