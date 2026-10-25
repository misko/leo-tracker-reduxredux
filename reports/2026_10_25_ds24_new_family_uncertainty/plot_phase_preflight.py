"""Plot existing independent preflight evidence; performs no fits/propagation."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import t

ROOT = Path(__file__).resolve().parent
linear = json.loads((ROOT / 'math_audit/phase_linearization.json').read_text())
domain = json.loads((ROOT / 'math_audit/phase_domain.json').read_text())
out = ROOT / 'figures'
out.mkdir(exist_ok=True)
plt.rcParams.update({'font.size': 10, 'axes.spines.top': False,
                     'axes.spines.right': False})
fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), layout='constrained')
for col, case in enumerate(linear['cases']):
    a = axes[0, col]
    for row in case['evaluations']:
        sd = row['phase_marginal_sd_s']
        points = [p for p in row['offsets'] if 'sd' in p['name']]
        # At the expansion point the linearization is exact by construction.
        pairs = sorted([(p['offset_s'] / sd, p['projected_RMS_error_hz'])
                        for p in points] + [(0., 0.)])
        xx, yy = zip(*pairs)
        arm = 'c = 0' if row['arm'] == 'c0' else 'fitted c'
        a.plot(xx, yy, 'o-', lw=1.3, alpha=.75,
               label=f"{arm}, {row['endpoint']}")
    shapes = [r['projected_shape_RMS_marginal_hz'] for r in case['evaluations']]
    a.axhspan(min(shapes), max(shapes), color='#267e39', alpha=.25)
    a.axhline(np.mean(shapes), color='#267e39', ls='--',
              label=f'Shape prior projection: {np.mean(shapes):.2f} Hz')
    a.set(xlabel='Phase offset / original prior SD',
          ylabel='Projected nonlinear Doppler error (Hz)',
          title=f"{case['case']} · {case['points']} target points")
    a.grid(alpha=.2)
    a.legend(fontsize=8)
    d = next(v for v in domain['cases'] if v['case'] == case['case'])
    b = axes[1, col]
    x = np.linspace(-24, 24, 3001)
    scale = d['original_marginal_sd_s'] / np.sqrt(3)
    density = t.pdf((x-d['original_location_s'])/scale, df=3)/scale
    inside = (x >= -15) & (x <= 15)
    b.plot(x, density, color='#656565', lw=1.6, label='Original causal Student prior')
    b.plot(x[inside], density[inside]/(1-d['prior_mass_removed']),
           color='#1864a4', lw=1.6, label='Conditioned on −15 to +15 s')
    b.fill_between(x, density, where=~inside, color='#c83d45', alpha=.4,
                    label=f"Excluded mass: {100*d['prior_mass_removed']:.5f}%")
    b.axvline(-15, color='#333', ls=':', lw=1)
    b.axvline(15, color='#333', ls=':', lw=1)
    b.set(xlabel='Absolute orbital-time correction (s)', ylabel='Prior density (1/s)',
          title=(f"Conditioning changes SD: {d['original_marginal_sd_s']:.3f} "
                 f"→ {d['conditional_sd_s']:.3f} s"))
    b.grid(alpha=.2)
    b.legend(fontsize=8)
fig.suptitle('Why the first target-phase approximation was rejected before position fitting',
             fontsize=15, weight='bold')
fig.supxlabel('Top: constant and local phase derivative removed using native-sigma weights.\n'
              'Engineering-prior diagnostics; no new position fits or satellite-identity validation.',
              fontsize=10)
fig.savefig(out / 'phase_preflight.png', dpi=170)
fig.savefig(out / 'phase_preflight.pdf')
print(out / 'phase_preflight.png')
