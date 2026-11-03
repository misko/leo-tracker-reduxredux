"""Standalone scientific comparison; no model or scan selection."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
development = json.loads((HERE / 'compatible-summary.json').read_text())
confirmation = json.loads((HERE / 'additional-summary.json').read_text())
rows = []
for index in (0, 4, 9, 16, 19, 20):
    rows.append((f'Development {index:02d}', {r['arm']: r for r in development['rows'] if r['index'] == index}))
rows.append(('Separate recording 01', {r['arm']: r for r in confirmation['rows']}))
fig, ax = plt.subplots(figsize=(10, 5))
for y, (label, values) in enumerate(rows):
    old, new = values['original']['distance_m'], values['signed']['distance_m']
    if old is None or new is None or not values['signed']['qualified']:
        ax.text(.05, y, 'Unqualified: see execution receipt')
        continue
    color = '#007f73' if new < old else '#c34c35'
    ax.plot([old / 1000, new / 1000], [y, y], color=color, linewidth=2, alpha=.8)
    ax.scatter(old / 1000, y, color='#718096', marker='o', s=52, label='Original IID' if y == 0 else None, zorder=3)
    ax.scatter(values['doppler']['distance_m'] / 1000, y, color='#292d35', marker='|', s=100, label='Joint Doppler only' if y == 0 else None, zorder=4)
    ax.scatter(new / 1000, y, color=color, marker='D', s=52, label='Joint receiver geometry' if y == 0 else None, zorder=5)
ax.axhline(5.5, color='#bfc4cb', linestyle='--', linewidth=1)
ax.set_yticks(range(len(rows)), [r[0] for r in rows])
ax.invert_yaxis()
ax.set_xlim(left=0)
ax.set_xlabel('Distance to unsurveyed roof reference (km)')
ax.set_title('Causal DS11 positioning: frozen receiver geometry model\nOnly matching 5MS/s recordings and exact calibrated RF centers', loc='left', pad=18)
ax.grid(axis='x', alpha=.2)
ax.spines[['top', 'right', 'left']].set_visible(False)
ax.legend(loc='upper center', bbox_to_anchor=(.5, -.16), ncol=3, fontsize=9)
fig.tight_layout()
fig.savefig(HERE / 'position-comparison.png', dpi=180)
fig.savefig(HERE / 'position-comparison.svg')
