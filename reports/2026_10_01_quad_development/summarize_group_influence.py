"""Summarize fixed-group local sensitivity without reference positions."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from check_group_influence import UNITS
from check_receiver_curvature import save
from screen_seed_prefix import digest, sealed
from regression_batch import verify_sources
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent


def main():
    rows = []; inputs = {}; launches = []
    for unit in UNITS:
        directory = HERE/'group-influence-v1'/unit
        frozen = sealed(directory/'sources.json')
        verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
        launch = sealed(directory/'launch.json'); assert process_ok(launch); launches.append(launch)
        row = sealed(directory/'result.json'); assert row['all_valid']; rows.append(row)
        for name in ('sources.json', 'result.json', 'launch.json'): inputs[str(directory/name)] = digest(directory/name)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.7), constrained_layout=True)
    colors = ('#386cb0', '#df8829', '#2b9871')
    labels = []
    for i, row in enumerate(rows):
        values = [r['horizontal_step_m'] for r in row['groups']]
        axes[0].scatter(i+np.linspace(-.16, .16, len(values)), values, s=9, color=colors[i//3], alpha=.5)
        axes[0].scatter(i, row['median_step_m'], marker='_', s=150, color='black')
        labels.append(row['unit'].replace('-B01-', '\n'))
        axes[1].scatter(i-.07, row['profiled_to_fixed_eigenvalue_ratios'][0], color=colors[i//3], marker='o')
        axes[1].scatter(i+.07, row['profiled_to_fixed_eigenvalue_ratios'][1], color=colors[i//3], marker='s')
    axes[0].set_yscale('log'); axes[0].set_ylabel('Predicted horizontal deletion step (m)')
    axes[0].set_title('All satellite groups; black marks = medians')
    axes[1].set_ylabel('Profiled / fixed-nuisance sorted eigenvalue')
    axes[1].set_title('Nuisance coupling reduces position curvature')
    axes[1].set_ylim(0, 1); axes[1].axhline(1, color='gray', linewidth=.8)
    for ax in axes: ax.set_xticks(range(9), labels, fontsize=8); ax.grid(axis='y', alpha=.2)
    fig.suptitle('Local IRLS sensitivity — not position error or calibrated uncertainty')
    figure = HERE/'group-influence-summary-v1.png'; fig.savefig(figure, dpi=160); plt.close(fig)
    summary = dict(rows=rows, groups=sum(len(r['groups']) for r in rows),
        total_process_seconds=sum(l['elapsed_seconds'] for l in launches), inputs=inputs,
        sources={str(Path(__file__).resolve()): digest(__file__)}, figure_sha256=digest(figure))
    save(HERE/'group-influence-summary-v1.json', summary)
    for r in rows:
        print(r['unit'], len(r['groups']), round(r['median_step_m'], 1), round(r['maximum_group']['horizontal_step_m'], 1), r['profiled_to_fixed_eigenvalue_ratios'])
    print('groups', summary['groups'], 'seconds', summary['total_process_seconds'])


if __name__ == '__main__': main()
