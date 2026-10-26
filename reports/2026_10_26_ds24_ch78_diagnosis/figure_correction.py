"""Versioned display correction; reads sealed results, performs no fits."""
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
source = ROOT / 'report/summary.json'
v = json.loads(source.read_text())
out = ROOT / 'report/figures_v2'
out.mkdir(exist_ok=True)
cases = ('DS24-0010', 'DS24-0011', 'DS24-0012', 'DS24-0013')
kinds = ('unmatched', 'count_only', 'family_RX_time')
fig, axes = plt.subplots(2, 4, figsize=(16, 8), layout='constrained', sharey=True)
maximum = max(r['error_km'] for r in v['matched_rows'])
for i, arm in enumerate(('c0', 'fitted_c')):
    for j, case in enumerate(cases):
        ax = axes[i, j]
        rows = [next(r for r in v['matched_comparisons'] if
                     r['case'] == case and r['arm'] == arm and r['comparison'] == kind)
                for kind in kinds]
        for band, color, shift in [('low', '#217d8b', -.07), ('high', '#c8752e', .07)]:
            y = np.array([r[f'{band}_error_mean_km'] for r in rows])
            low = np.array([r[f'{band}_error_min_km'] for r in rows])
            high = np.array([r[f'{band}_error_max_km'] for r in rows])
            ax.errorbar(np.arange(3) + shift, y, yerr=[y-low, high-y],
                        fmt='o-', color=color, capsize=3,
                        label='CH1–4' if band == 'low' else 'CH5–8')
        full = next(r['error_km'] for r in v['matched_rows'] if r['case'] == case
                    and r['arm'] == arm and r['method'] == 'full')
        ax.axhline(full, color='.45', ls=':', label='All curved points')
        ax.set_title(case + ' · ' + ('c=0' if arm == 'c0' else 'fitted c'))
        ax.set_xticks(range(3), ['Unmatched', 'Count\nmatched', 'Family/RX/time\nmatched'])
        ax.grid(alpha=.2)
        if j == 0:
            ax.set_ylabel('Position error (km)')
# Set one global range after all shared-axis plots have been drawn.
axes[0, 0].set_ylim(0, maximum * 1.12)
assert all(r['error_km'] <= axes[0, 0].get_ylim()[1] for r in v['matched_rows'])
axes[0, 0].legend(fontsize=8)
fig.suptitle('Frozen full-data precision and identities; curved evidence only\n'
             'Bars: range of three predetermined subsamples, not confidence intervals', fontsize=12)
for suffix in ('png', 'pdf'):
    target = out / ('matched_position_errors.' + suffix)
    assert not target.exists()
    fig.savefig(target, dpi=175)
plt.close(fig)
seal = {
    'reason': 'Original shared-axis plot clipped later panels; global limits now include every endpoint. No numerical result changed.',
    'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'maximum_position_error_km': maximum,
    'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()},
}
with (out / 'seal.json').open('x') as f:
    json.dump(seal, f, indent=2)
    f.write('\n')
print(json.dumps({'maximum_position_error_km': maximum, 'directory': str(out)}))
