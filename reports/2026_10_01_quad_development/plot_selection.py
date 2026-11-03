"""Render the selected four-scan blocks and the nested evaluation counts."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest, ROOT

HERE = Path(__file__).resolve().parent
path = HERE/'selection.json'
assert digest(path) == path.with_suffix('.sha256').read_text().strip()
data = json.loads(path.read_text())
for source, expected in data['source_sha256'].items():
    assert digest(ROOT/source) == expected
captures = {r['unit_id']: r for r in data['captures']}
fig, ax = plt.subplots(figsize=(11, 7), constrained_layout=True)
colors = {'DS9':'#3178a8', 'DS10':'#df8535', 'DS11':'#37936b'}
for y, block in enumerate(data['blocks']):
    start = block['capture_start_utc_ns']
    for i, unit in enumerate(block['scans']):
        c = captures[unit]
        left = (c['capture_start_utc_ns']-start)/60e9
        width = (c['capture_end_utc_ns']-c['capture_start_utc_ns'])/60e9
        ax.barh(y, width, left=left, height=.65, color=colors[block['dataset']],
                edgecolor='black' if c['original_64_member'] else 'white',
                linewidth=2 if c['original_64_member'] else .5)
        ax.text(left+width/2, y, unit.split('-')[1], ha='center', va='center', color='white', fontsize=8)
ax.set_yticks(range(16), [b['block_id'] for b in data['blocks']])
ax.invert_yaxis()
ax.set_xlabel('Minutes since first scan in each block (actual capture timestamps)')
ax.set_xlim(0,27)
ax.grid(axis='x', alpha=.2)
ax.set_title('64 scans in 16 consecutive quads\n64 singles · 32 adjacent pairs · 16 quads\nBlack outlines: 12 scans also in original benchmark', loc='left', fontsize=12)
fig.savefig(HERE/'selection.png', dpi=160)
