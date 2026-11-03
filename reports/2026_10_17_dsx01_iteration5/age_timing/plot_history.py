"""Descriptive historical update differences; no physical-truth interpretation."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.ticker import NullFormatter

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE/'calibration_v2.json').read_text())
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    for column, provider in enumerate(('space-track', 'huggingface')):
        rows = [r for p in data['pairs'] if p['provider'] == provider for r in p['rows']]
        ages = np.array([r['old_element_age_days'] for r in rows])
        along = np.array([abs(r['effective_along_track_s']) for r in rows])
        perpendicular = np.array([r['perpendicular_km'] for r in rows])
        for ax, values, title, unit in ((axes[0, column], along,
            'Projected along-track difference', 'seconds'), (axes[1, column], perpendicular,
            'Orthogonal position difference', 'km')):
            ax.scatter(ages, np.maximum(values, 1e-6), s=4, alpha=.12, rasterized=True)
            ax.set(xscale='log', yscale='log', xlabel='Old entry age at comparison epoch (days)',
                   ylabel=unit, title=f'{provider}: {title}')
            ax.grid(alpha=.2)
            ax.title.set_fontsize(10)
            ticks = [.25, .5, 1, 2, 4, 8, 16, 32, 64, 128, 256]
            upper = max(40., float(ages.max())*1.05)
            ticks = [t for t in ticks if t <= upper]
            ax.set_xlim(.2, upper)
            ax.set_xticks(ticks, [str(t) for t in ticks])
            ax.xaxis.set_minor_formatter(NullFormatter())
        bins = [b for b in data['age_bins'] if b['provider'] == provider and b['count']]
        for b in bins:
            if b['distinct_objects'] < 2:
                continue  # A singleton's zero MAD is not an estimated width.
            center = np.median([r['old_element_age_days'] for r in rows
                if b['lower_age_days'] <= r['old_element_age_days'] and
                (b['upper_age_days'] is None or r['old_element_age_days'] < b['upper_age_days'])])
            axes[0, column].scatter(center, max(b['mad_sigma_s'], 1e-6), marker='D', s=32,
                facecolors='#bb3311' if b['distinct_objects'] >= 100 else 'none',
                edgecolors='#bb3311')
        axes[0, column].plot([], [], 'D', color='#bb3311',
                            label='Age-bin MAD core (filled: >=100 objects)')
        axes[0, column].legend(fontsize=8)
    fig.suptitle('Causal same-provider TLE update consistency\n'
        'Newer elements are not truth; shared reference/errors and maneuvers can contribute')
    fig.savefig(HERE/'historical_consistency.png', dpi=160)
    fig.savefig(HERE/'historical_consistency.pdf')


if __name__ == '__main__':
    main()
