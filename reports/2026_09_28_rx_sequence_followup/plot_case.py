"""Plot frozen match states for the sole uncensored receiver-order proxy."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / 'cases.json').read_text())
case, = [c for c in data['cases'] if c['sequence']['uncensored_lag_rx1_minus_rx0_s'] is not None]
start = min(r['prediction_utc_ns'] for rx in case['receivers'].values() for r in rx['eligible_observations'])
styles = {
    'no_matching_candidate': ('No compatible candidate', '#cbd5e1', '|'),
    'ambiguous_candidate': ('Multiple candidates', '#d55e00', 'x'),
    'ambiguous_hypothesis': ('Multiple hypotheses', '#e69f00', 'x'),
    'unique_hit': ('Unique proxy hit', '#0072b2', 'o'),
}
fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True, layout='constrained',
                         gridspec_kw={'height_ratios': [1, 1.5]})
seen = set()
for rid, (rx, record) in enumerate(case['receivers'].items()):
    for status, (label, color, marker) in styles.items():
        rows = [r for r in record['eligible_observations'] if r['status'] == status]
        if not rows:
            continue
        times = [(r['prediction_utc_ns'] - start) / 1e9 for r in rows]
        axes[0].scatter(times, [rid] * len(times), color=color, marker=marker,
                        s=45, label=label if status not in seen else None)
        seen.add(status)
    interval = record['first_hit_interval']
    if interval['valid']:
        low = (interval['lower_exclusive_utc_ns'] - start) / 1e9
        high = (interval['upper_inclusive_utc_ns'] - start) / 1e9
        axes[0].plot([low, high], [rid + .15, rid + .15], color='black', lw=3)
        axes[0].axvline(high, color='#475569', ls=':', alpha=.6)
    points = [(r, m) for r in record['eligible_observations'] for m in r['matches']]
    axes[1].scatter([(r['prediction_utc_ns'] - start) / 1e9 for r, m in points],
                    [m['fractional_margin'] for r, m in points],
                    s=25, marker=['o', '^'][rid], alpha=.75, label=rx.upper())
axes[0].set_yticks([0, 1], ['RX0', 'RX1'])
axes[0].set_ylim(-.35, 1.5)
axes[0].set_title('One 9.34 s recorded order; detections are intermittent', loc='left')
axes[0].legend(loc='upper right', ncol=3, fontsize=8, frameon=False)
axes[1].set_ylabel('Raw detector margin\n(all frozen compatible candidates)')
axes[1].set_xlabel('Seconds since first eligible reception-period observation')
axes[1].legend(frameon=False)
for ax in axes:
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis='x', alpha=.15)
fig.savefig(HERE / 'retained-sequence.png', dpi=170)
fig.savefig(HERE / 'retained-sequence.svg')
