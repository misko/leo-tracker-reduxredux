"""Compare both failed geometry variants with the same Doppler baseline."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sequence = json.loads((HERE / 'sequence-summary.json').read_text())
original = json.loads((HERE / 'compatible-summary.json').read_text())
additional = json.loads((HERE / 'additional-summary.json').read_text())
jobs = [('original', i) for i in (0, 4, 9, 16, 19, 20)] + [('additional', 1)]
fig, ax = plt.subplots(figsize=(10, 5.4))
for y, (cohort, index) in enumerate(jobs):
    rows = [r for r in sequence['rows'] if r['cohort'] == cohort and r['index'] == index]
    base = next(r['distance_m'] for r in rows if r['arm'] == 'doppler') / 1000
    timed = next(r['distance_m'] for r in rows if r['arm'] == 'signed') / 1000
    earlier = original['rows'] if cohort == 'original' else additional['rows']
    independent = next(r['distance_m'] for r in earlier if r['arm'] == 'signed' and (cohort == 'additional' or r['index'] == index)) / 1000
    ax.plot([min(base, timed, independent), max(base, timed, independent)], [y, y], color='#c7ccd2', linewidth=2)
    for value, marker, color, label in ((base, 'o', '#637083', 'Joint Doppler'), (independent, 'D', '#007f73', 'Independent receiver states'), (timed, '|', '#bb5d29', 'Time-aware receiver states')):
        ax.scatter(value, y, marker=marker, color=color, s=110 if marker == '|' else 45, linewidths=2, label=label if y == 0 else None, zorder=3)
ax.axhline(5.5, color='#bfc4cb', linestyle='--', linewidth=1)
ax.set_yticks(range(7), [f'Development {i:02d}' for i in (0, 4, 9, 16, 19, 20)] + ['Separate recording 01'])
ax.invert_yaxis()
ax.set_xlim(left=0)
ax.set_xlabel('Distance to unsurveyed roof reference (km)')
ax.set_title('Receiver geometry: development gains did not pass confirmation\nFrozen causal models; only compatible 5MS/s / RF recordings', loc='left', pad=18)
ax.grid(axis='x', alpha=.2)
ax.spines[['top', 'right', 'left']].set_visible(False)
ax.legend(loc='upper center', bbox_to_anchor=(.5, -.15), ncol=3, fontsize=8.5)
fig.tight_layout()
fig.savefig(HERE / 'sequence-comparison.png', dpi=180)
fig.savefig(HERE / 'sequence-comparison.svg')
