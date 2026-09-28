"""Show the disjoint-panel contrasts against both required references."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
r = json.loads((HERE / 'results.json').read_text())
records = list(r['arm_minus_clutter_per_record']['S'])
fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), layout='constrained')
for ax, values, title, ylabel in (
    (axes[0], r['contrasts_per_record']['S-D'], 'Static geometry beats Doppler-only', 'S − D'),
    (axes[1], r['arm_minus_clutter_per_record']['S'], 'Only two records beat clutter', 'S − clutter'),
):
    heights = [values[s] for s in records]
    ax.bar(range(4), heights, color=['#0072b2' if x > 0 else '#d55e00' for x in heights])
    ax.axhline(0, color='#334155', lw=.8)
    ax.set_xticks(range(4), [s.removeprefix('scan-fw-')[:8] for s in records], rotation=25)
    ax.set_ylabel(ylabel + ': nats per paired held window')
    ax.set_title(title, loc='left')
    ax.spines[['top', 'right']].set_visible(False)
fig.savefig(HERE / 'confirmation-contrasts.png', dpi=170)
fig.savefig(HERE / 'confirmation-contrasts.svg')
