"""Render the saved audit without reading production storage."""

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


directory = Path(__file__).resolve().parent
evidence = json.loads((directory / 'evidence.json').read_text())
fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout='constrained')
sessions = evidence['sessions']
for rx in (0, 1):
    axes[0].plot(
        [s['start_utc'][11:19] for s in sessions],
        [s['median_rms_counts'][rx] for s in sessions],
        'o-', label=f'RX{rx}',
    )
    rows = sessions[-1]['rows']
    axes[1].plot([r['visit'] for r in rows], [r['rms_counts'][rx] for r in rows], '.', label=f'RX{rx}')
for ax in axes:
    ax.set_yscale('log')
    ax.set_ylabel('RMS per I/Q component (stored ADC counts)')
    ax.grid(alpha=.2)
    ax.legend()
axes[0].set_title('Before and after the roof move')
axes[0].set_xlabel('Capture start, 2026-09-26 UTC (uneven spacing)')
axes[1].set_title('Requested scan: 112 visits across all five minutes')
axes[1].set_xlabel('Visit index (every 20th stored visit)')
fig.suptitle('RX0 remains near the ADC floor; RX1 recovers')
fig.savefig(directory / 'rx0-floor.png', dpi=160)
