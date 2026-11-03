"""Render installed-runtime profiling attribution, without implying paired speedups."""

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

root = Path(__file__).resolve().parent
data = json.loads((root / 'receipts/profile-summary.json').read_text())
rows = data['hotspots'][:9]
labels = [r['function'].replace('{built-in method ', '').rstrip('}') for r in rows]
labels = [s.replace('leo.analysis.starlink._screen_native._native_acquisition.', '')
          for s in labels]
fig, ax = plt.subplots(figsize=(11, 6), layout='constrained')
ax.barh(labels[::-1], [r['self_seconds'] for r in rows][::-1], color='#287ba5')
ax.set(xlabel='Self time (seconds)',
       title='Installed batched detector: remaining CPU hotspots\n'
             'DS27-0004 · 16 frozen windows · cProfile attribution')
ax.grid(axis='x', alpha=.2)
ax.set_axisbelow(True)
fig.savefig(root / 'profile.png', dpi=160)
