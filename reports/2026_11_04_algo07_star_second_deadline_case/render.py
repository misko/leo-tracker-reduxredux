"""Plot recorded ALGO03 stage durations without treating them as a benchmark."""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--summary', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
data = json.loads(args.summary.read_text())
fig, ax = plt.subplots(figsize=(10, 5.2), layout='constrained')
for side, label, color in [('reference', 'ALGO07 reference', '#2166ac'),
                           ('candidate', 'ALGO07* candidate', '#d6604d')]:
    rows = data['sides'][side]['timeline']
    ax.plot(range(1, len(rows) + 1), [r['cumulative_stage_seconds'] for r in rows],
            marker='o', color=color, label=label)
    index = next(i for i, row in enumerate(rows) if row['name'] == 'target-4-audit')
    value = rows[index]['cumulative_stage_seconds']
    ax.annotate(f'{value:.1f} s after five targets', (index + 1, value),
                xytext=(6.5, value + (42 if side == 'candidate' else -70)),
                arrowprops={'arrowstyle': '->', 'color': color}, color=color)
ax.axhline(600, color='black', linestyle='--', label='600 s discovery admission limit')
ax.set(xlabel='Completed ALGO03 child stage (inventory, annotation, fit or audit)',
       ylabel='Sum of recorded child-stage durations (s)', xlim=(.5, 15.5), ylim=(0, 740),
       title='DS26-0170: time-based admission changes search work\n'
             'Three candidate annotations omitted; final selected result remains identical')
ax.grid(alpha=.2)
ax.legend(loc='upper left')
fig.text(.5, -.035, 'Stage sums exclude bookkeeping; admission uses elapsed wall time. '
         'Shared-host timings are not a speed benchmark.\n'
         'Both arms retain exactly the same 3,353 owners. Strict scientific parity remains FAIL.',
         ha='center', fontsize=9)
fig.savefig(args.output, dpi=160, bbox_inches='tight')
plt.close(fig)
