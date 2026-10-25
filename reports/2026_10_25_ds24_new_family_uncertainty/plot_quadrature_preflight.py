"""Plot frozen numerical convergence checks, without new model evaluations."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
result = json.loads((ROOT / 'scientific/preparation02/result.json').read_text())
nodes = [81, 161, 321, 641, 1281, 2561]
specs = [
    ('score_error_vs_adaptive', 'Maximum target loss error'),
    ('gradient_error_vs_adaptive_per_km', 'Maximum gradient error (loss units/km)'),
]
fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), layout='constrained')
for ax, (metric, label) in zip(axes, specs):
    for case, color in [('DS24-0095', '#1764a3'), ('DS24-0087', '#bc4b22')]:
        rows = [r for r in result['rows'] if r['case'] == case]
        errors = [max(r['checks'][str(n)][metric] for r in rows) for n in nodes]
        ax.loglog(nodes, errors, 'o-', color=color, label=case)
    ax.axhline(1e-3, color='#333', ls='--', label='Predeclared tolerance')
    ax.axvline(result['global_fixed_node_count'], color='#30833d', ls=':',
               label='Selected common rule: 1281 nodes')
    ax.set(xlabel='Fixed Gauss–Legendre phase nodes', ylabel=label)
    ax.set_xticks(nodes, [str(n) for n in nodes])
    ax.grid(which='both', alpha=.18)
    ax.legend(fontsize=8)
fig.suptitle('Nonlinear timing integration: coarse rules distort the loss and gradient',
             fontsize=14)
fig.supxlabel('Independent adaptive reference; 160 fixed checks across both c settings, both covariance branches,\n'
              'saved baseline/support/midpoint and regional start, with ±10 m axis offsets. No new position fits.',
              fontsize=9)
out = ROOT / 'figures'
out.mkdir(exist_ok=True)
fig.savefig(out / 'phase_quadrature_convergence.png', dpi=170)
fig.savefig(out / 'phase_quadrature_convergence.pdf')
print(out / 'phase_quadrature_convergence.png')
