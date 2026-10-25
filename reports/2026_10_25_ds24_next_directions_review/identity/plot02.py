"""Presentation-only correction: shorter titles; unchanged sealed numbers."""
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

p = Path(__file__).resolve().parent
d = json.loads((p / 'evidence_summary.json').read_text())
fig, axes = plt.subplots(1, 2, figsize=(10.7, 4.1))
colors = ['#3073ad', '#d27828']
pair = d['candidate_pair']
axes[0].barh([1, 0], [x['alternate_minus_nominal_NLL'] for x in pair], color=colors)
axes[0].axvline(0, color='black', linewidth=.8)
axes[0].set_yticks([1, 0], ['Saved c = 0 parent', 'Saved fitted-c parent'])
axes[0].set_xlim(-2.1, 2.1)
axes[0].set_xlabel('Difference in −2 log predictive density\n66259 minus 57743 (positive favors 57743)')
axes[0].set_title('0012: weak candidate ranking\nBoth candidates use archive alias 1', fontsize=11)
for y, row in zip([1, 0], pair):
    value = row['alternate_minus_nominal_NLL']
    axes[0].text(value + (.06 if value > 0 else -.06), y, f'{value:+.3f}',
                 ha='left' if value > 0 else 'right', va='center', fontsize=9)
x = np.arange(4)
for i, arm in enumerate(('c0', 'fitted_c')):
    values = [r['marginal_minus_conditional'] for r in d['owner_scores'] if r['arm'] == arm]
    axes[1].bar(x + (i - .5) * .34, values, .34, color=colors[i],
                label='Saved c = 0 parent' if i == 0 else 'Saved fitted-c parent')
axes[1].set_xticks(x, ['CH2 T005\n53 IDs', 'CH4 T000\n85 IDs', 'CH7 T004\n36 IDs', 'CH8 T004\n15 IDs'])
axes[1].set_ylabel('Marginal − held-owner conditional\n−2 log predictive density')
axes[1].set_title('0013: conditional consistency\nAssigned 60108, four RX1 sources', fontsize=11)
axes[1].set_ylim(0, 21)
axes[1].legend(fontsize=8, frameon=False)
fig.text(.5, .01, 'All sources RX1; no identity qualification. Overlapping owner folds must not be summed.\n'
         '0012 uses archive alias 1 and candidate-specific causal priors; saved parent positions and calibration both differ.',
         ha='center', fontsize=8)
fig.tight_layout(rect=(0, .11, 1, 1))
fig.savefig(p / 'identity_diagnostics02.png', dpi=180)
fig.savefig(p / 'identity_diagnostics02.pdf')
plt.close(fig)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
names = ['FINDINGS.md', 'plot02.py', 'identity_diagnostics02.png', 'identity_diagnostics02.pdf',
         'evidence_summary.json', 'checks.json', 'seal.json', 'owner02_seal.json', 'report_seal.json']
(p / 'report02_seal.json').write_text(json.dumps(dict(
    files={name: sha(p / name) for name in names},
    supersedes='report_seal.json',
    reason='correct report convergence bound to 1.904e-5; wrap plot titles and state minus2log units',
    scientific_results_unchanged=True, position_fits=0, GPS_used=False), indent=2) + '\n')
print('report02_seal.json', sha(p / 'report02_seal.json'))
