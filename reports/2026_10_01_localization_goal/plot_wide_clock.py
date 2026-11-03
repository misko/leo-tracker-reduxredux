"""Plot matched clock-prior experiments and fitted shared offsets."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
data = json.loads((HERE/'wide-clock-v1-evaluation.json').read_text())
fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
arms = ['control', 'clock2', 'clock5']
units = list(dict.fromkeys(r['unit'] for r in data['rows']))
for unit in units:
    rows = [next(r for r in data['rows'] if r['unit'] == unit and r['arm'] == a) for a in arms]
    axes[0].plot(range(3), [r['error_m'] if r['accepted'] else np.nan for r in rows], '-o', alpha=.65, label=unit)
    axes[1].plot(range(3), [r['clock_s'] if r['accepted'] else np.nan for r in rows], '-o', alpha=.65)
for ax in axes:
    ax.set_xticks(range(3), ['1 s (baseline)', '2 s', '5 s'])
    ax.set_xlabel('Shared clock prior standard deviation')
    ax.grid(alpha=.2)
axes[0].set_ylabel('Horizontal error (m)')
axes[1].set_ylabel('Fitted shared time shift (s)')
axes[0].legend(fontsize=7, ncol=2)
fig.suptitle('12 independent development scans · fixed baseline satellite assignments')
fig.savefig(HERE/'wide-clock-v1.png', dpi=160)
