"""Render held score contrasts without converting them to accuracy claims."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / 'results.json').read_text())
contrasts = data['contrasts_per_record']
records = list(contrasts['S-D'])
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout='constrained')
axes[0].bar(range(4), [contrasts['S-D'][r] for r in records], color='#0072b2')
axes[0].set_title('Static geometry improves the pilot score', loc='left')
axes[0].set_ylabel('S − D: nats per paired held window')
for offset, (key, color) in enumerate([('T-S', '#009e73'), ('T-swap', '#e69f00'), ('T-reverse', '#cc79a7')]):
    axes[1].bar([i + (offset-1)*.23 for i in range(4)],
                [contrasts[key][r] for r in records], width=.23, label=key, color=color)
axes[1].set_title('Tilt does not beat the reversal control', loc='left')
axes[1].set_ylabel('Contrast: nats per paired held window')
axes[1].legend(frameon=False)
for ax in axes:
    ax.axhline(0, color='#334155', lw=.8)
    ax.set_xticks(range(4), [r.removeprefix('scan-fw-')[:8] for r in records], rotation=25)
    ax.set_xlabel('Evaluation recording')
    ax.spines[['top', 'right']].set_visible(False)
fig.savefig(HERE / 'held-contrasts.png', dpi=170)
fig.savefig(HERE / 'held-contrasts.svg')
