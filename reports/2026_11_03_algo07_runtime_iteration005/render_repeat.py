"""Show the controlled repeat without replacing the initial slower trial."""

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
result = json.loads((root/'DS27-alternating.json').read_text())
rows = result['rows']
fig, ax = plt.subplots(figsize=(10, 4.5))
ax.plot(range(1, 17), [r['baseline']['seconds'] for r in rows], 'o-', label='Installed GLRT')
ax.plot(range(1, 17), [r['candidate']['seconds'] for r in rows], 'o-', label='12-lane tiling')
ax.set_xticks(range(1, 17), [f"{i+1}\nCH{r['channel']}" for i, r in enumerate(rows)])
ax.set_ylabel('Detector seconds per paired-receiver window')
ax.set_xlabel('Randomly selected window; baseline/candidate order alternates')
ax.set_title('DS27-0004: same CPU, alternating implementations, no profiler\n'
             '25.45 → 16.64 seconds; 16/16 faster, exact outputs')
ax.legend()
fig.tight_layout()
fig.savefig(root/'DS27_alternating.png', dpi=160)
