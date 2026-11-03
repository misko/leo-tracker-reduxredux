"""Render the sealed one-source assay without choosing winners."""
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
LABELS = {'original': 'Original HF46 (historical)',
          'saved_space_track': 'Saved ST59 (historical)',
          'original_fitted-c': 'HF-state start → ST59, fitted c',
          'saved_space_track_fitted-c': 'ST-state start → ST59, fitted c',
          'original_zero-c': 'HF-state start → ST59, c=0',
          'saved_space_track_zero-c': 'ST-state start → ST59, c=0'}
COLORS = ['#666666', '#999999', '#0072B2', '#009E73', '#D55E00', '#CC79A7']


def main():
    evaluation = json.loads((HERE/'evaluation.json').read_text())
    rows = {row['label']: row for row in evaluation['rows']}
    labels = list(LABELS)
    states = {label: dict(np.load(HERE/f'eval_{label}.npz', allow_pickle=False))
              for label in labels}
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)
    grid = np.geomspace(1., 1000., 300)
    for label, color in zip(labels, COLORS, strict=True):
        if rows[label]['arm'] != 'fitted-c':
            continue
        state = states[label]
        residual = np.sort(abs(state['residual_hz'][state['associated']]))
        axes[0].step(grid, np.searchsorted(residual, grid, side='right')/4797,
                     where='post', color=color, label=LABELS[label])
        distance = rows[label]['configured_reference_distance_km']
        marker = 'o' if rows[label]['audit']['accepted'] else 'x'
        axes[1].scatter([distance], [1.], color=color, marker=marker, s=65)
        axes[1].step([.1, distance, 1000.], [0., 1., 1.], where='post', color=color)
    axes[0].set(xscale='log', xlim=(1, 1000), ylim=(0, 1.05),
        xlabel='Absolute associated CFO residual (Hz)', ylabel='Fraction of all 4,797 observations')
    axes[1].set(xscale='log', xlim=(.1, 1000), ylim=(0, 1.05),
        xlabel='Configured-reference distance (km)', ylabel='Fraction of one recording (S01 only)')
    axes[1].axvline(.5, color='black', alpha=.35)
    axes[0].legend(fontsize=8)
    for axis in axes:
        axis.grid(alpha=.2)
    fig.suptitle('S01 initialization diagnostic — fitted c; all outcomes retained\n'
        'Unassociated observations stay in denominator; historical HF/ST runs are unmatched')
    for suffix in ('png', 'pdf'):
        fig.savefig(HERE/f'performance.{suffix}', dpi=160)
    plt.close(fig)
    regions = ['DSX01-001', 'DSX01-002', 'DSX01-003']
    matrix = np.array([[next(w['assigned']/w['observations'] for w in evaluation['windows']
        if w['label'] == label and w['region_id'] == region) for region in regions]
        for label in labels])
    fig, axis = plt.subplots(figsize=(10, 5.7), constrained_layout=True)
    pic = axis.imshow(matrix, vmin=0, vmax=1, aspect='auto', cmap='viridis')
    for i, label in enumerate(labels):
        for j, region in enumerate(regions):
            window = next(w for w in evaluation['windows']
                          if w['label'] == label and w['region_id'] == region)
            axis.text(j, i, f"{window['assigned']}/{window['observations']}",
                      ha='center', va='center', color='white' if matrix[i, j] < .55 else 'black')
    axis.set_xticks(range(3), regions)
    axis.set_yticks(range(len(labels)), [LABELS[label] for label in labels])
    axis.set_title('Three frozen S01 windows /148 observations\n'
                   'Other 12 DSX01 windows /545 observations remain untested')
    fig.colorbar(pic, ax=axis, label='Associated fraction; identities unverified')
    for suffix in ('png', 'pdf'):
        fig.savefig(HERE/f'windows.{suffix}', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    bins = np.arange(-22., 23., 1.)
    for i, (label, color) in enumerate(zip(labels, COLORS, strict=True)):
        row = rows[label]
        tau = np.array(list(row['total_timing_s'].values()))
        axes[0].hist(tau-row['common_timing_s'], bins=bins, histtype='step',
                     color=color, label=LABELS[label])
        distance = row['configured_reference_distance_km']
        axes[1].scatter([distance], [i], color=color,
                        marker='o' if row['audit']['accepted'] else 'x', s=60)
        axes[1].annotate(f'{distance:.2f}', (distance, i), xytext=(5, 0),
                         textcoords='offset points', fontsize=8)
    axes[0].set(xlabel='Relative orbital timing offset (s)', ylabel='Candidate count')
    axes[0].legend(fontsize=7)
    axes[1].set(xscale='log', xlim=(.1, 400), xlabel='Configured-reference distance (km)')
    axes[1].set_yticks(range(len(labels)), [LABELS[label] for label in labels], fontsize=7)
    axes[1].axvline(.5, color='black', alpha=.35)
    fig.suptitle('S01 complete outcomes — timing and position are separate diagnostics\n'
                 'o: strict; x: nonstationary; configured reference survey uncertainty is unknown')
    for axis in axes:
        axis.grid(alpha=.2)
    for suffix in ('png', 'pdf'):
        fig.savefig(HERE/f'timing_and_position.{suffix}', dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    main()
