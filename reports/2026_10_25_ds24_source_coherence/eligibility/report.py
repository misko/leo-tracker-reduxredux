"""Render saved duration metadata; no scientific fits or likelihood calls."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
x = json.loads((ROOT/'summary.json').read_text())
fig, ax = plt.subplots(figsize=(9, 4.8), layout='constrained')
loc = np.arange(3)
for delta, field, color, label in [(-.18,'prefix_duration_s','#176da3','Prefix'),(.18,'suffix_duration_s','#c77b30','Suffix')]:
    vals = [r[field] for r in x['proposed_metadata_cuts']]
    bars = ax.bar(loc+delta, vals, width=.34, color=color, label=label)
    ax.bar_label(bars, fmt='%.2f s', padding=4)
ax.axhline(x['original_duration_threshold_s'], color='black', ls='--', label='Historical curved-salvage duration minimum')
ax.set_xticks(loc, [f"After point {r['cut_after_count']}\n{r['gap_times_s'][0]:.2f}–{r['gap_times_s'][1]:.2f} s" for r in x['proposed_metadata_cuts']])
ax.set_ylim(0,25)
ax.set_ylabel('Duration of the corresponding portion (s)')
ax.set_title('CH4: the middle-cut portions fail the old 20 s prerequisite\nPassing duration alone does not establish curvature or satellite identity')
ax.legend(loc='upper left', fontsize=8)
ax.grid(axis='y', alpha=.2)
fig.savefig(ROOT/'support_durations.png', dpi=160)
plt.close(fig)
files = [ROOT/'summary.json', Path(__file__), ROOT/'support_durations.png']
(ROOT/'report_seal.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2)+'\n')
