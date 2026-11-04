"""Render validated public diagnostic grids; no inference or fitting."""

import argparse
import json
from pathlib import Path

import matplotlib

from leo.cli.algo07_profile import write_new
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    stores = [FastStandardAnalysisStore(p) for p in (args.reference, args.candidate)]
    grids = [store.position_grid(args.run_id) for store in stores]
    details = [store.detail(args.run_id) for store in stores]
    assert details[0]['arms'] == details[1]['arms']
    maps = [{(p['east_km'], p['north_km']): p for p in grid['points']} for grid in grids]
    shared = maps[0].keys() & maps[1].keys()
    assert all(maps[0][xy] == maps[1][xy] for xy in shared)
    assert grids[0]['endpoints'] == grids[1]['endpoints']
    values = [p['scores']['fitted_c'] for p in grids[0]['points']]
    limits = dict(vmin=min(values), vmax=max(values))
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), layout='constrained',
                             sharex=True, sharey=True)
    for ax, grid, label in zip(axes, grids, ('ALGO07 reference', 'Optimized ALGO07*'), strict=True):
        rows = grid['points']
        dots = ax.scatter([p['east_km'] for p in rows], [p['north_km'] for p in rows],
                          c=[p['scores']['fitted_c'] for p in rows], cmap='viridis_r', s=23,
                          **limits)
        for arm, marker, color in [('c0', 's', '#ff5500'), ('fitted_c', '*', '#ffbb00')]:
            ax.scatter(*grid['endpoints'][arm], marker=marker, c=color,
                       edgecolors='black', s=100, label=arm + ' selected endpoint', zorder=5)
        ax.set(title=f"{label}: {grid['evaluated_points']}/{grid['planned_points']}",
               xlabel='East of regional centre (km)', xlim=(-13.2, 13.2), ylim=(-13.2, 13.2))
        ax.set_aspect('equal')
        ax.grid(alpha=.15)
    missing = sorted(maps[0].keys() - maps[1].keys())
    if missing:
        axes[1].scatter([p[0] for p in missing], [p[1] for p in missing], facecolors='none',
                        edgecolors='red', s=38, linewidths=1.2,
                        label='Not completed before deadline')
    axes[0].set_ylabel('North of regional centre (km)')
    axes[1].legend(fontsize=7, loc='upper left')
    fig.colorbar(dots, ax=axes, shrink=.85, label='Conditional fitted-c score (lower is better)')
    errors = {arm: details[0]['arms'][arm]['evaluation_error_m'] for arm in ('c0', 'fitted_c')}
    fig.suptitle(f'DS26-0002: post-fit diagnostic grid coverage\n'
                 f'{len(shared)} shared evaluations match exactly; selected positions unchanged\n'
                 f"Both paths: c=0 error {errors['c0']:.1f} m; "
                 f"fitted-c error {errors['fitted_c']:.1f} m (evaluation only)")
    args.output.mkdir(parents=True, exist_ok=True)
    write_new(args.output / 'grid-data.json', dict(reference=grids[0], candidate=grids[1],
                                                published_arms=details[0]['arms']))
    fig.savefig(args.output / 'grid-coverage.png', dpi=160)
    plt.close(fig)
    print(json.dumps(dict(shared=len(shared), missing=len(missing))))


if __name__ == '__main__':
    main()
