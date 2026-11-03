"""Show offset scale and within-track residual sign persistence."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
result = json.loads((HERE/'conditional-offset-audit-v1.json').read_text())
fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), layout='constrained')
datasets = ['DS9', 'DS10', 'DS11']
observed, shuffled = [], []
for ds, color in zip(datasets, ['#1f77b4', '#e07b16', '#289447'], strict=True):
    rows = [r for r in result['rows'] if r['unit'].startswith(ds+'-')]
    values = np.sort([r['posterior_sd_hz'] for r in rows])
    axes[0].step(values, np.arange(1, len(values)+1)/len(values), where='post', label=ds, color=color)
    total = sum(r['adjacent_pairs'] for r in rows)
    observed.append(sum(r['adjacent_same_sign'] for r in rows)/total)
    shuffled.append(sum(r['shuffled_expected_same_sign'] for r in rows)/total)
axes[0].set(xscale='log', xlabel='Conditional offset SD (Hz)', ylabel='Fraction of tracks',
            title='Offset uncertainty under assumed raw noise model', ylim=(0, 1))
axes[0].set_xticks([40, 100, 300, 600], labels=['40', '100', '300', '600'])
axes[0].minorticks_off()
axes[0].legend()
x = np.arange(3)
axes[1].bar(x-.18, observed, width=.36, label='Observed successive groups', color='#287fa9')
axes[1].bar(x+.18, shuffled, width=.36, label='Within-track shuffle expectation', color='#909090')
axes[1].set(xticks=x, xticklabels=datasets, ylim=(0, 1), ylabel='Fraction sharing residual sign',
            title='Residual temporal structure remains')
axes[1].legend(loc='upper right', fontsize=8)
for ax in axes:
    ax.grid(axis='y', alpha=.2)
fig.suptitle('526 training-only fitted tracks; diagnostic assumptions, not calibrated position uncertainty')
fig.savefig(HERE/'conditional-offset-audit-v1.png', dpi=160)
