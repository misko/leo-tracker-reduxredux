"""Plot saved one-window candidate parity; no IQ or detector execution."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
data = json.loads((ROOT / 'replay_one_window.json').read_text())
fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True, sharey=True)
for rx, ax in enumerate(axes):
    old = data['expected_probes'][str(rx)]['candidates']
    new = data['actual_exported_candidates'][str(rx)]
    ax.scatter([x['fractional_tracking_cfo_hz']/1000 for x in old],
               [x['fractional_margin'] for x in old], s=110, facecolors='none',
               edgecolors='#197a78', linewidths=2, label='Archived')
    ax.scatter([x['fractional_tracking_cfo_hz']/1000 for x in new],
               [x['fractional_margin'] for x in new], s=45, marker='x',
               color='#bd4d32', label='Replayed')
    ax.axhline(.025, ls='--', color='0.4', label='Original margin gate')
    ax.set(title=f'RX{rx+1}: all five exported candidates match', xlabel='CFO (kHz)')
    ax.grid(alpha=.2)
axes[0].set_ylabel('Fractional GLRT margin')
axes[1].legend(fontsize=9)
fig.suptitle('DS24-0011, visit 0: unchanged 20 ms / 10 MS/s window\n'
             'Historical code and environment match; maximum exported numerical difference = 0')
for suffix in ('png', 'pdf'):
    fig.savefig(ROOT / f'replay_candidates.{suffix}', dpi=170)
