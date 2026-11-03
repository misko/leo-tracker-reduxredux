"""Original-winner denominators and paired residuals for every saved receipt."""
import csv
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
PRIMARY = ['b0', 'b300-profile', 'b1000-profile']


def paired(base, new, use):
    before, after = base['associated'] & use, new['associated'] & use
    both = before & after
    rms = lambda values: float(np.sqrt(np.mean(values**2))) if len(values) else None
    return dict(denominator=int(use.sum()), assigned=int(after.sum()),
        assigned_rms_hz=rms(new['residual_hz'][after]), new=int((after & ~before).sum()),
        lost=int((before & ~after).sum()), retained=int(both.sum()),
        identity_changes=int(np.sum(both & (base['satellite_number'] != new['satellite_number']))),
        intersection_baseline_rms_hz=rms(base['residual_hz'][both]),
        intersection_variant_rms_hz=rms(new['residual_hz'][both]))


def main():
    records = []
    failures = []
    for path in sorted((HERE/'results').glob('*.json')):
        record = json.loads(path.read_text())
        if record.get('state') == 'failed':
            failures.append(record)
        else:
            records.append(record)
    lookup = {r['task']:r for r in records}
    arrays = {r['task']:dict(np.load(HERE/'results'/(r['task']+'.npz'))) for r in records}
    originals = {source:dict(np.load(REPORTS/'2026_10_16_dsx01_models/results'/
        f'{source}-full-fitted-c-original.npz')) for source in sorted({r['source_id'] for r in records})}
    original_records = {source:json.loads((REPORTS/'2026_10_16_dsx01_models/results'/
        f'{source}-full-fitted-c-original.json').read_text()) for source in originals}
    with (REPORTS/'2026_10_16_dsx01_fast_association_losses/membership.csv').open() as stream:
        membership = list(csv.DictReader(stream))
    rows, regions = [], []
    for record in records:
        name, source, arm = record['task'], record['source_id'], record['arm']
        baseline = arrays[f'{source}-{arm}-b0']
        point = arrays[name]
        original = originals[source]
        np.testing.assert_array_equal(original['times_s'], point['times_s'])
        use = np.ones(len(point['associated']), bool)
        full, challenge, outside = (paired(baseline, point, mask) for mask in
            (use, point['challenge_mask'], ~point['challenge_mask']))
        bias = np.asarray(list(record['biases_hz'].values()))
        row = dict(task=name, source_id=source, arm=arm, method=record['method'],
            comparison_baseline='matched-b0-continuation', original_baseline='immutable-fitted-c-production',
            accepted=record['endpoint_audit']['accepted'],
            stationarity=record['endpoint_audit']['stationarity'],
            objective=record['full_scan']['objective'], nll=record['full_scan']['likelihood_nll'],
            evaluations=record['diagnostics']['evaluations'],
            surrogate_profile_calls=record['diagnostics'].get('surrogate_profile_calls', 0),
            configured_reference_distance_km=record['full_scan']['configured_reference_distance_km'],
            position_movement_from_original_km=record['full_scan']['position_movement_km'],
            common_timing_s=record['full_scan']['common_timing_s'],
            relative_timing_rms_s=record['full_scan']['relative_timing_rms_s'],
            c=record['full_scan']['c'], bias_rms_hz=float(np.sqrt(np.mean(bias**2))),
            bias_max_hz=float(max(abs(bias))), bias_active_bounds=int(np.sum(abs(bias) >= 4000.-1e-6)))
        for label, stats in [('full', full), ('challenge', challenge), ('outside', outside)]:
            row.update({label+'_'+key:value for key, value in stats.items()})
        for label, mask in [('full', use), ('challenge', point['challenge_mask']), ('outside', ~point['challenge_mask'])]:
            row.update({'original_'+label+'_'+key:value for key, value in paired(original, point, mask).items()})
        rows.append(row)
        for region in sorted({m['region_id'] for m in membership if m['source_id'] == source}):
            ids = {m['observation_id'] for m in membership if m['region_id'] == region}
            mask = np.isin(point['observation_id'], list(ids))
            original_stats = paired(original, point, mask)
            assigned_original = int(np.sum(original['associated'] & mask))
            missing_original = int(mask.sum())-assigned_original
            net = original_stats['new']-original_stats['lost']
            restored = 100.*net/missing_original if missing_original else None
            regions.append(dict(task=name, source_id=source, arm=arm,
                method=record['method'], region_id=region,
                comparison_baseline='matched-b0-continuation',
                **paired(baseline, point, mask), original_assigned=assigned_original,
                original_missing=missing_original,
                **{'original_'+key:value for key, value in original_stats.items() if key != 'assigned'},
                net_original_missing_restored=net, net_original_missing_restored_pct=restored,
                strong_original_restoration=bool(restored is not None and restored >= 80.)))
    for filename, values in [('comparison.csv', rows), ('regions.csv', regions)]:
        with (HERE/filename).open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0]))
            writer.writeheader()
            writer.writerows(values)
    aggregates = []
    for arm in ['fitted-c', 'zero-c']:
        for method in PRIMARY:
            selected = [r for r in records if r['arm'] == arm and r['method'] == method]
            if not selected:
                continue
            points = [arrays[r['task']] for r in selected]
            before = [arrays[f"{r['source_id']}-{arm}-b0"] for r in selected]
            merged = {key:np.concatenate([p[key] for p in points]) for key in points[0]}
            original = {key:np.concatenate([p[key] for p in before]) for key in before[0]}
            production = {key:np.concatenate([originals[r['source_id']][key] for r in selected])
                for key in ['associated', 'residual_hz', 'satellite_number']}
            use = np.ones(len(merged['associated']), bool)
            aggregates.append(dict(arm=arm, method=method, completed_sources=len(selected),
                expected_sources=5, strict_endpoints=sum(r['endpoint_audit']['accepted'] for r in selected),
                full=paired(original, merged, use),
                challenge=paired(original, merged, merged['challenge_mask']),
                outside=paired(original, merged, ~merged['challenge_mask']),
                original_full=paired(production, merged, use),
                original_challenge=paired(production, merged, merged['challenge_mask']),
                strong_original_restoration_regions=[r['region_id'] for r in regions
                    if r['arm'] == arm and r['method'] == method and r['strong_original_restoration']],
                expected_full_denominator=20084, expected_challenge_denominator=693))
    summary = dict(receipts=len(records), failures=failures, aggregates=aggregates,
        qualification='All saved results retained; original693-winner challenge inventory and original classification. All are full-recording development fits; no predictive validation or localization accuracy claim. Cross-width total J is not model evidence: parameter-independent Gaussian normalizers are omitted to preserve zero-bias nesting.')
    (HERE/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    make_plots(rows, arrays, records)
    original_plots(records, original_records, regions)
    print(json.dumps(summary, indent=2))


def make_plots(rows, arrays, records):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors = {'b0':'#555555', 'b300-profile':'#1876a8', 'b1000-profile':'#bf6512'}
    for arm in ['fitted-c', 'zero-c']:
        fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
        specs = [('challenge_assigned', 'Assigned frozen challenge winners', 'count'),
            ('full_assigned_rms_hz', 'Assigned-point frequency RMS', 'Hz; population changes'),
            ('relative_timing_rms_s', 'Relative satellite timing RMS', 'seconds'),
            ('configured_reference_distance_km', 'Configured reference distance', 'km; not surveyed accuracy')]
        for axis, (field, title, ylabel) in zip(axes.ravel(), specs):
            for method in PRIMARY:
                selected = sorted([r for r in rows if r['arm'] == arm and r['method'] == method],
                    key=lambda r:r['source_id'])
                if selected:
                    axis.plot([r['source_id'] for r in selected], [r[field] for r in selected],
                        marker='o', label=method, color=colors[method])
            axis.set_title(title)
            axis.set_ylabel(ylabel)
            axis.grid(alpha=.25)
        axes[0, 0].legend()
        fig.suptitle(f'Empirical satellite constant-Hz bias, {arm}: full-data development fits')
        fig.savefig(HERE/f'comparison-{arm}.png', dpi=150)
        plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    for axis, challenge in zip(axes, [False, True]):
        for method in PRIMARY:
            selected = [r for r in records if r['arm'] == 'fitted-c' and r['method'] == method]
            if not selected:
                continue
            denom, residuals = 0, []
            for record in selected:
                point = arrays[record['task']]
                use = point['challenge_mask'] if challenge else np.ones(len(point['associated']), bool)
                denom += int(use.sum())
                residuals.extend(abs(point['residual_hz'][use & point['associated']]).tolist())
            values = np.asarray(residuals)
            thresholds = np.arange(0., 501., 5.)
            axis.plot(thresholds, [100.*np.sum(values <= value)/denom for value in thresholds],
                color=colors[method], label=method)
        axis.set_title('Frozen challenge' if challenge else 'All original observations')
        axis.set_xlabel('Absolute model residual threshold (Hz)')
        axis.set_ylabel('% original denominator assigned and within threshold')
        axis.grid(alpha=.25)
    axes[0].legend()
    fig.suptitle('Fitted-c residual coverage: unassigned points remain in denominator')
    fig.savefig(HERE/'residual-coverage.png', dpi=150)
    plt.close(fig)


def original_plots(records, originals, regions):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors = {'original':'#262626', 'b0':'#777777', 'b300-profile':'#1876a8', 'b1000-profile':'#bf6512'}
    timing_rows = []
    for arm in ['fitted-c', 'zero-c']:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
        for method in ['original']+PRIMARY:
            total, relative = [], []
            for source, original in originals.items():
                record = original if method == 'original' else next(r for r in records
                    if r['source_id'] == source and r['arm'] == arm and r['method'] == method)
                timings = record['full_scan']['total_timing_s']
                assert set(timings) == set(original['full_scan']['total_timing_s'])
                common = record['full_scan']['common_timing_s']
                for satellite in sorted(timings):
                    total.append(timings[satellite])
                    relative.append(timings[satellite]-common)
                    timing_rows.append(dict(arm=arm, method=method, source_id=source,
                        satellite_number=satellite, total_timing_s=timings[satellite],
                        relative_timing_s=timings[satellite]-common, common_timing_s=common))
            assert len(total) == 215
            for axis, values in zip(axes, [total, relative]):
                axis.hist(values, bins=np.arange(-25., 26., 1.), histtype='step',
                    color=colors[method], label=method, linewidth=1.6)
        for axis, title in zip(axes, ['Total satellite timing', 'Relative satellite timing (common removed)']):
            axis.set(title=title, xlabel='Timing shift (s)', ylabel='Recording-satellite pairs (same 215)')
            axis.grid(alpha=.2)
        axes[0].legend()
        fig.suptitle(f'{arm}: original and empirical-bias endpoints; common timing remains separate')
        fig.savefig(HERE/f'timing-histogram-{arm}.png', dpi=150)
        plt.close(fig)
        fig, axes = plt.subplots(2, 1, figsize=(14, 8), constrained_layout=True)
        ordered = sorted([r for r in regions if r['arm'] == arm and r['method'] == 'b0'], key=lambda r:r['region_id'])
        x = np.arange(len(ordered))
        axes[0].bar(x-.3, [r['original_assigned'] for r in ordered], width=.18, color=colors['original'], label='original')
        for offset, method in zip([-.1, .1, .3], PRIMARY):
            selected = sorted([r for r in regions if r['arm'] == arm and r['method'] == method], key=lambda r:r['region_id'])
            axes[0].bar(x+offset, [r['assigned'] for r in selected], width=.18, color=colors[method], label=method)
            axes[1].plot(x, [r['net_original_missing_restored_pct'] for r in selected], marker='o', color=colors[method], label=method)
        axes[0].plot(x, [r['denominator'] for r in ordered], 'k_', label='frozen denominator')
        axes[1].axhline(80., color='black', linestyle=':', label='80% net original missing restored')
        for axis in axes:
            axis.set_xticks(x, [r['region_id'].replace('DSX01-', '') for r in ordered])
            axis.set_xlabel('Frozen challenge window')
            axis.grid(axis='y', alpha=.2)
            axis.legend(fontsize=8, ncol=5)
        axes[0].set_ylabel('Assigned original winners (counts)')
        axes[1].set_ylabel('Net original missing restored (%)')
        fig.suptitle(f'{arm}: all 15 windows, all 693 original winners; descriptive threshold only')
        fig.savefig(HERE/f'window-coverage-{arm}.png', dpi=150)
        plt.close(fig)
    with (HERE/'timing-pairs.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(timing_rows[0]))
        writer.writeheader()
        writer.writerows(timing_rows)


if __name__ == '__main__':
    main()
