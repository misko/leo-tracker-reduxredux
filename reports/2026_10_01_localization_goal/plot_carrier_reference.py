"""Plot diagnostic displacement, explicitly distinct from geographic error."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from regression_batch import digest

HERE = Path(__file__).resolve().parent
source = HERE/'carrier-reference-v1.json'
assert digest(source) == source.with_suffix('.sha256').read_text().strip()
rows = json.loads(source.read_text())['rows']
fig, ax = plt.subplots(figsize=(10, 5), layout='constrained')
ax.barh([r['unit'] for r in rows], [r['predicted_position_shift_m'] for r in rows],
        color=['#3977a8' if r['maximum_carrier_difference_hz'] > 10 else '#9aa4ad' for r in rows])
ax.set_xlim(0, 55)
for i, row in enumerate(rows):
    value = row['predicted_position_shift_m']
    ax.text(value+.5, i, f'{value:.1f} m' if value > 1 else '<0.001 m', va='center', fontsize=9)
ax.set_xlabel('Predicted local position displacement (m), not error against reference')
ax.set_title('Nominal pilot versus tuner frequency: local sensitivity\n'
             'Fixed identities, weights and Jacobians; original nuisance priors retained')
ax.invert_yaxis()
output = HERE/'carrier-reference-v1.png'
assert not output.exists()
fig.savefig(output, dpi=160)
