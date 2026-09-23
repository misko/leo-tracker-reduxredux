"""Plot saved production results beside the isolated 50 km replay."""
import json
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

root = Path(__file__).resolve().parent
baseline = json.loads((root / 'position-document.json').read_text())
replay = json.loads((root / 'position-50km.json').read_text())
truth = {'sacramento': (-87.03579588322457, -80.99086034665268),
         'reno': (-234.5971991843171, -183.42995911691125)}
fig, axes = plt.subplots(2, 2, figsize=(12, 10), layout='constrained')
for i, (old, new) in enumerate(zip(baseline['priors'], replay['priors'], strict=True)):
    name = old['name']
    for j, (prior, initial) in enumerate(((old, 100), (new, 50))):
        ax = axes[i, j]
        rows = baseline['diagnostics']['evaluated_points'][name] if j == 0 else new['evaluated_points']
        trace = baseline['diagnostics']['search_trace'][name] if j == 0 else new['trace']
        levels = Counter(p['spacing_km'] for p in trace if p['event'] == 'evaluate')
        pts = ax.scatter([p['east_km'] for p in rows], [p['north_km'] for p in rows],
                         c=[p['capped_weighted_rmse_hz'] for p in rows],
                         s=18, cmap='viridis_r', vmin=130, vmax=500)
        radius = prior['region']['radius_km']
        ax.add_patch(Circle((0, 0), radius, fill=False, color='gray'))
        ax.scatter(*truth[name], marker='*', c='#e44b28', s=150, edgecolor='black',
                   label='Known position (evaluation only)', zorder=5)
        winner = prior['selected']
        ax.scatter(winner['east_km'], winner['north_km'], marker='X', s=90,
                   c='#ffcf33', edgecolor='black', label='Selected position', zorder=6)
        ax.set(xlim=(-radius*1.08, radius*1.08), ylim=(-radius*1.08, radius*1.08),
               aspect='equal', xlabel='East of prior center (km)', ylabel='North of prior center (km)')
        ax.set_title(f"{name.title()} — {initial} km starting grid\n"
                     f"Error {winner['horizontal_error_m']/1000:.1f} km | score {winner['capped_weighted_rmse_hz']:.1f} Hz\n"
                     f"Initial samples: {levels[initial]} | 12.5 km samples: {levels[12.5]}", fontsize=10)
        ax.grid(alpha=.15)
axes[1, 1].legend(loc='lower left', fontsize=7)
fig.colorbar(pts, ax=axes, label='Selection RMSE (Hz; lower is better; colors clipped at 500)', shrink=.7)
fig.suptitle('50 km grid replay: same 34 tracks, same scoring, same 400-point budget\n'
             'scan-fw-9a10ab698717f70d · both searches remain incomplete', fontsize=13)
fig.savefig(root / 'search-coverage-50km-comparison.png', dpi=170)
print(root / 'search-coverage-50km-comparison.png')
