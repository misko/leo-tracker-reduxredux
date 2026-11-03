"""Summarize frozen DSX01 endpoints without fitting or selecting a model."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
DATA = REPORTS / '2026_10_16_dsx01_fast_association_losses'
OLD = REPORTS / '2026_10_16_dsx01_models'
LATEST = REPORTS / '2026_10_16_dsx01_iteration2'
LABELS = {'original': 'Original', 'profile1000': 'Exact profile: fixed candidates',
          'expanded_profile': 'Exact profile: expanded candidates'}
COLORS = {'original': '#666666', 'profile1000': '#0072b2', 'expanded_profile': '#d55e00'}


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    inputs = [DATA / 'regions.csv', LATEST / 'window-comparison.csv']
    regions = read_csv(inputs[0])
    windows = {(r['region_id'], r['method']): r for r in read_csv(inputs[1])
               if r['arm'] == 'fitted-c'}
    methods = list(LABELS)
    timing, added = [], []
    summaries = {}
    for sid in ['S01', 'S02', 'S03', 'S04', 'S05']:
        paths = {'original': OLD / 'results' / f'{sid}-full-fitted-c-original.json',
                 'profile1000': LATEST / 'results' / f'{sid}-fitted-c-profile.json',
                 'expanded_profile': LATEST / 'expanded-results' / f'{sid}-fitted-c-profile.json'}
        metrics = {m: json.loads(p.read_text())['full_scan'] for m, p in paths.items()}
        inputs.extend(paths.values())
        npz_path = paths['original'].with_suffix('.npz')
        inputs.append(npz_path)
        with np.load(npz_path) as state:
            numbers, counts = np.unique(state['satellite_number'][state['associated']], return_counts=True)
        support = {str(int(n)): int(c) for n, c in zip(numbers, counts)}
        baseline = metrics['original']['total_timing_s']
        for method, metric in metrics.items():
            assert set(baseline).issubset(metric['total_timing_s'])
            for number, total in metric['total_timing_s'].items():
                row = dict(source_id=sid, satellite=number, method=method, total_timing_s=total,
                           common_timing_s=metric['common_timing_s'],
                           relative_timing_s=total - metric['common_timing_s'],
                           original_assigned_observations=support.get(number, 0))
                if number in baseline:
                    row['total_change_s'] = total - baseline[number]
                    timing.append(row)
                else:
                    row['total_change_s'] = None
                    added.append(row)
    write_csv(HERE / 'timing-offsets.csv', timing + added)
    for method in methods:
        rows = [windows[r['region_id'], method] for r in regions]
        assert len(rows) == 15 and sum(int(r['observations']) for r in rows) == 693
        net = np.array([float(r['net_original_missing_restored_pct']) for r in rows])
        summary = dict(associated=sum(int(r['associated']) for r in rows),
                       new=sum(int(r['new_associations']) for r in rows),
                       lost=sum(int(r['lost_associations']) for r in rows),
                       major_80=int(np.sum(net >= 80)), moderate_50_to_80=int(np.sum((net >= 50) & (net < 80))),
                       partial_below_50=int(np.sum((net > 0) & (net < 50))),
                       unchanged=int(np.sum(net == 0)), worsened=int(np.sum(net < 0)),
                       fully_associated=sum(int(r['associated']) == int(r['observations']) for r in rows))
        group = [r for r in timing if r['method'] == method]
        assert len(group) == 215
        supported = [r for r in group if r['original_assigned_observations'] >= 5]
        assert len(supported) == 182
        for name, cohort in [('all_original_pairs', group), ('original_supported_pairs', supported)]:
            total = np.array([r['total_timing_s'] for r in cohort])
            relative = np.array([r['relative_timing_s'] for r in cohort])
            summary[name] = dict(count=len(cohort), total_rms_s=float(np.sqrt(np.mean(total**2))),
                                 relative_rms_s=float(np.sqrt(np.mean(relative**2))),
                                 median_absolute_total_s=float(np.median(abs(total))),
                                 total_at_least_19_s=int(np.sum(abs(total) >= 19)),
                                 total_above_5_s=int(np.sum(abs(total) > 5)))
        summaries[method] = summary
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.6), constrained_layout=True)
    for col, supported_only in enumerate([False, True]):
        cohort = 'All original candidates: 215 pairs' if not supported_only else 'Original support ≥5 observations: 182 pairs'
        for row, (field, label) in enumerate([('total_timing_s', 'Total orbit-time offset τ (s)'),
                                             ('relative_timing_s', 'Offset minus recording common shift (s)')]):
            ax = axes[row, col]
            bins = np.arange(-32, 34, 2)
            for method in methods:
                values = [r[field] for r in timing if r['method'] == method and
                          (not supported_only or r['original_assigned_observations'] >= 5)]
                assert np.histogram(values, bins=bins)[0].sum() == len(values)
                ax.hist(values, bins=bins, histtype='step', linewidth=2,
                        linestyle='--' if method == 'original' else '-',
                        color=COLORS[method], label=LABELS[method])
            ax.axvline(0, color='#999999', linewidth=.7)
            if row == 0:
                for bound in [-20, 20]:
                    ax.axvline(bound, color='#aaaaaa', linewidth=.8, linestyle=':')
            ax.set(xlim=(-30, 30), xlabel=label, ylabel='Recording–satellite pairs / 2 s bin')
            ax.grid(axis='y', alpha=.2)
            if row == 0:
                ax.set_title(cohort)
            if row == 1:
                ax.legend(fontsize=8)
    fig.suptitle('DSX01: satellite timing-offset distributions, fitted c\nSame candidate cohort before and after; fitted offsets are not measured TLE errors')
    fig.savefig(HERE / 'satellite-timing-histogram.png', dpi=175)
    plt.close(fig)
    table = []
    for region in regions:
        rid = region['region_id']
        before, fixed, expanded = [windows[rid, m] for m in methods]
        table.append(dict(window=rid[-3:], source=region['source_id'], receiver=region['receiver'],
                          channel=region['channel'], start_s=region['start_s'], end_s=region['end_s'],
                          observations=int(before['observations']), original=int(before['associated']),
                          fixed=int(fixed['associated']), expanded=int(expanded['associated']),
                          expanded_new=int(expanded['new_associations']), expanded_lost=int(expanded['lost_associations']),
                          expanded_net_missing_restored_pct=float(expanded['net_original_missing_restored_pct'])))
    write_csv(HERE / 'window-breakdown.csv', table)
    fig, ax = plt.subplots(figsize=(12, 9), constrained_layout=True)
    y = np.arange(15)
    for offset, method, field in [(-.25, 'original', 'original'), (0, 'profile1000', 'fixed'), (.25, 'expanded_profile', 'expanded')]:
        ax.barh(y + offset, [100*r[field]/r['observations'] for r in table], height=.23,
                color=COLORS[method], label=LABELS[method])
    ax.set_yticks(y, [f"{r['window']} {r['source']} RX{r['receiver']}/CH{r['channel']} {float(r['start_s']):g}–{float(r['end_s']):g}s" for r in table])
    ax.invert_yaxis()
    ax.set(xlim=(0, 100), xlabel='Associated / all frozen window observations (%)',
           title='DSX01: association recovery across all 15 windows, fitted c')
    ax.grid(axis='x', alpha=.2)
    ax.legend(loc='lower right', fontsize=9)
    fig.savefig(HERE / 'window-recovery.png', dpi=175)
    plt.close(fig)
    lines = ['# DSX01: latest 15-window recovery and timing snapshot', '',
             'Read-only summary of saved fitted-c endpoints. Recovery means association coverage, '
             'not verified satellite identity or validated position accuracy. No parameters were refitted. '
             'No validation-position information is used for model selection or initialization.', '',
             'Expanded profile: 434/693 associated, up from 96/693. Seven windows restore ≥80% '
             'of originally missing associations, one restores 50–80%, six restore less than 50%, '
             'and window 003 remains unchanged at zero. Three windows reach complete association. '
             'The fixed-bank profile has six major restorations and 422/693 associations. '
             'Expansion regresses window 001 from 79/86 to 45/86; do not combine per-window maxima.', '',
             'Net missing restored = (new associations − lost original associations) / originally missing. '
             'The 80% grouping is descriptive, not a preregistered success criterion.', '',
             '| Window | Region | Original | Fixed | Expanded | Expanded new / lost | Net missing restored |',
             '|---|---|---:|---:|---:|---:|---:|']
    for r in table:
        lines.append(f"| {r['window']} | {r['source']} RX{r['receiver']}/CH{r['channel']} {float(r['start_s']):g}–{float(r['end_s']):g}s | {r['original']}/{r['observations']} | {r['fixed']}/{r['observations']} | {r['expanded']}/{r['observations']} | {r['expanded_new']} / {r['expanded_lost']} | {r['expanded_net_missing_restored_pct']:.1f}% |")
    lines += ['', '![All windows](window-recovery.png)', '', '![Timing histograms](satellite-timing-histogram.png)', '',
              'Each histogram entry is one recording–satellite fit, not one observation. The same satellite '
              'may occur in multiple recordings. Both comparisons retain the same original cohort even '
              'if support is subsequently lost. Added expanded-bank candidates are excluded from these '
              'matched histograms and retained separately in the timing CSV. Total offsets are bounded '
              'at ±20 s; subtracting the common shift can put relative offsets beyond those bounds. '
              'Timing offsets can absorb geometry, calibration and identity errors; they do not independently '
              'measure satellite clock error or TLE age.', '',
              '| Method | Total RMS (s), 215 pairs | Relative RMS (s), 215 pairs | Total abs(τ) ≥19 s |',
              '|---|---:|---:|---:|']
    for method in methods:
        s = summaries[method]['all_original_pairs']
        lines.append(f"| {LABELS[method]} | {s['total_rms_s']:.2f} | {s['relative_rms_s']:.2f} | {s['total_at_least_19_s']}/215 |")
    lines += ['', 'Across complete scans, the expanded model gains 3,817 assignments but loses 791 original '
              'assignments. Several position-reference distances remain above 100 km. These development '
              'results do not establish generalization to new positions. The next validation must keep '
              'position-independent initialization and data-derived candidate selection, and measure held '
              'observations with correct training-only band calibration.', '',
              'Source recording IDs and denominators are frozen in the dataset regions CSV. Controlled c=0 '
              'comparisons and numerical audit details remain in the [iteration 2 report](../2026_10_16_dsx01_iteration2/README.md).']
    (HERE / 'README.md').write_text('\n'.join(lines) + '\n')
    (HERE / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
    bindings = [{'path': str(p.resolve()), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs]
    outputs = [{'path': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
               for p in sorted(HERE.iterdir()) if p.is_file() and p.name != 'manifest.json']
    (HERE / 'manifest.json').write_text(json.dumps(dict(inputs=bindings, outputs=outputs), indent=2) + '\n')
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
