"""Post-selection four-way geographic and frequency evaluation; no fitting."""
import argparse
import collections
import csv
import json
from pathlib import Path
import numpy as np
import run_variants as run
from summarize import distance_km, distribution, reference_point
from leo.contracts.regional_position import RegionalPrior
from leo.analysis.regional_position_score import coordinates

HERE, OLD = run.HERE, run.OLD
VARIANTS = ('before', 'after', 'sigma2_60', 'sigma1_30')
ARMS = ('zero-c', 'fitted-c')
NAMES = {'before': 'Baseline', 'after': '1 s / ±60 Hz/s',
         'sigma2_60': '2 s / ±60 Hz/s', 'sigma1_30': '1 s / ±30 Hz/s'}
COLORS = {'before': '#9b5a37', 'after': '#1876a3', 'sigma2_60': '#c33576', 'sigma1_30': '#268442'}


def read(path):
    return json.loads(Path(path).read_text())


def root(phase):
    return OLD if phase in ('before', 'after') else HERE


def paired(rows, arm, phase, reference):
    left = {r['label']: r for r in rows if r['arm'] == arm and r['phase'] == reference}
    right = {r['label']: r for r in rows if r['arm'] == arm and r['phase'] == phase}
    pairs = [dict(label=label, reference_km=left[label]['error_km'], variant_km=right[label]['error_km'],
                  change_km=right[label]['error_km'] - left[label]['error_km'])
             for label in sorted(left.keys() & right.keys()) if left[label]['accepted'] and right[label]['accepted']]
    return dict(count=len(pairs), improved=sum(r['change_km'] < 0 for r in pairs),
                worsened=sum(r['change_km'] > 0 for r in pairs), unchanged=sum(r['change_km'] == 0 for r in pairs),
                median_change_km=float(np.median([r['change_km'] for r in pairs])) if pairs else None,
                largest_improvements=sorted(pairs, key=lambda r: r['change_km'])[:5],
                largest_regressions=sorted(pairs, key=lambda r: -r['change_km'])[:5])


def evaluate(partial=False):
    protocol = read(HERE / 'protocol.json')
    for path, expected in protocol['sources'].items():
        assert run.data.digest(path) == expected, path
    previous = read(OLD / 'summary.json')
    rows = list(previous['rows'])
    searches = list(previous['searches'])
    failures = list(previous['region_failures'])
    grid_failures = []
    reference_doc = read(OLD / 'evaluation.json')
    reference = [reference_doc['reference_latitude_deg'], reference_doc['reference_longitude_deg']]
    for label in run.LABELS:
        d = read(OLD / 'inputs' / label / 'inputs.json')
        prior = RegionalPrior(**d['prior'])
        truth = reference_point(prior, reference)
        for phase in run.PHASES:
            folder = HERE / 'results' / label / phase
            if not (folder / 'result.json').exists():
                if partial:
                    continue
                raise ValueError(f'Missing result {label} {phase}')
            result = read(folder / 'result.json')
            search = read(folder / 'search.json')
            points = search['search']['evaluations']
            grid_failures.extend(dict(label=label, phase=phase, **r) for r in search['rows'] if r['status'] == 'failed')
            assert len(points) == len({(p['east_km'], p['north_km']) for p in points}) == 400
            errors = [r for r in result['region_status'] if r['status'] != 'complete']
            failures.extend(dict(label=label, phase=phase, **r) for r in errors)
            candidates = [r for p in (folder / 'regions').glob('*.json') for r in read(p)['candidates']]
            covered = any(np.linalg.norm(np.array([b['east_km'], b['north_km']]) - truth)
                          <= max(25., b['spacing_km'] / np.sqrt(2)) for b in result['basins'])
            searches.append(dict(label=label, phase=phase, points=len(points),
                failed=sum(r['status'] == 'failed' for r in search['rows']),
                converged=sum(r['converged'] is True for r in search['rows']),
                time_limited=sum(r['stop_reason'] == 'time-budget' for r in search['rows']),
                levels=dict(collections.Counter(str(p['spacing_km']) for p in points)),
                outside_240km=sum(np.hypot(p['east_km'], p['north_km']) >= 240 for p in points),
                nearest_grid_point_km=min(float(np.linalg.norm(np.array([p['east_km'], p['north_km']]) - truth)) for p in points),
                reference_in_retained_region=covered, elapsed_s=result['elapsed_s']))
            for arm in ARMS:
                selection = result['selections'][arm]
                selected, best = selection['result'], selection['best_feasible']
                row = dict(label=label, session_id=d['session_id'], capture_local=d['capture_local'],
                           time_block=d['time_block'], phase=phase, arm=arm, accepted=selected is not None,
                           error_km=None, frequency_rms_hz=None, failed_regions=len(errors),
                           reference_in_retained_region=covered,
                           best_feasible_error_km=distance_km(*coordinates(prior, best['vector'][:2]), reference) if best else None,
                           best_available_candidate_error_km=min((distance_km(*coordinates(prior, c['vector'][:2]), reference)
                               for c in candidates if c['arm'] == arm and c['converged'] and c['feasible']), default=None))
                if selected:
                    x, y = selected['point']
                    radius = selected['local_radius_km']
                    region = read(folder / 'regions' / f'{x:g}_{y:g}_{radius:g}.json')
                    correction = region['calibration']['correction']
                    piecewise = np.diff(np.asarray(correction['knots_hz']), axis=1) / np.diff(correction['nodes_s'])
                    total = piecewise + np.asarray(selected['combined_affine_slopes_hz_s'])[:, None]
                    lat, lon = coordinates(prior, selected['vector'][:2])
                    row.update(error_km=distance_km(lat, lon, reference), latitude_deg=lat, longitude_deg=lon,
                        frequency_rms_hz=selected['frequency_rms_hz'], timing_penalty=selected['timing_penalty'],
                        signal_windows=selected['signal_windows'], signal_fraction=selected['signal_windows'] / d['observation_count'],
                        data_nll=selected['data_nll'], selection_score=selected['selection_score'],
                        rx0_slope_hz_s=selected['additional_slopes_hz_s'][0], rx1_slope_hz_s=selected['additional_slopes_hz_s'][1],
                        rx0_combined_affine_hz_s=selected['combined_affine_slopes_hz_s'][0],
                        rx1_combined_affine_hz_s=selected['combined_affine_slopes_hz_s'][1],
                        rx0_total_drift_min_hz_s=float(total[0].min()), rx0_total_drift_max_hz_s=float(total[0].max()),
                        rx1_total_drift_min_hz_s=float(total[1].min()), rx1_total_drift_max_hz_s=float(total[1].max()),
                        slope_bound_active=bool(selected['slope_active_bounds']), spatial_boundary=selected['boundary'],
                        stationarity=selected['stationarity'], origin=selected['origin'], region_east_km=x, region_north_km=y)
                rows.append(row)
    summary = {}
    for arm in ARMS:
        summary[arm] = {}
        for phase in VARIANTS:
            group = [r for r in rows if r['arm'] == arm and r['phase'] == phase]
            accepted = [r for r in group if r['accepted']]
            summary[arm][phase] = dict(completed=len(group), accepted=len(accepted), failed=len(group) - len(accepted),
                position_error_km=distribution([r['error_km'] for r in accepted]),
                median_frequency_rms_hz=float(np.median([r['frequency_rms_hz'] for r in accepted])) if accepted else None,
                median_signal_fraction=float(np.median([r['signal_fraction'] for r in accepted])) if accepted else None,
                slope_bound_active=sum(r['slope_bound_active'] for r in accepted),
                spatial_boundary=sum(r['spatial_boundary'] for r in accepted),
                versus_baseline=paired(rows, arm, phase, 'before'), versus_sigma1_60=paired(rows, arm, phase, 'after'))
    result = dict(complete=len(searches) == 256, completed_phases=len(searches), summary=summary,
                  rows=rows, searches=searches, region_failures=failures, grid_failures=grid_failures,
                  protocol_hash=run.data.digest(HERE / 'protocol.json'))
    run.engine.write(HERE / ('partial_summary.json' if partial else 'summary.json'), result)
    if not partial:
        export(result)
        plot(result)
        report(result)
    print(json.dumps(dict(complete=result['complete'], completed_phases=len(searches),
                         stats={a: {p: {k: v for k, v in s.items() if not k.startswith('versus_')}
                                    for p, s in ss.items()} for a, ss in summary.items()}), indent=2))
    return result


def export(result):
    wide = {}
    baseline = {(r['label'], r['arm']): r for r in result['rows'] if r['phase'] == 'before'}
    for r in result['rows']:
        target = wide.setdefault(r['label'], {k: r[k] for k in ('label', 'session_id', 'capture_local', 'time_block')})
        prefix = r['arm'].replace('-', '_') + '_' + r['phase']
        for key in ('error_km', 'accepted', 'frequency_rms_hz'):
            target[prefix + '_' + key] = r[key]
        b = baseline[r['label'], r['arm']]
        target[prefix + '_change_from_baseline_km'] = r['error_km'] - b['error_km'] if r['accepted'] and b['accepted'] else None
    for filename, values in [('comparison.csv', [wide[k] for k in sorted(wide)]),
                             ('results_long.csv', result['rows']), ('search_diagnostics.csv', result['searches'])]:
        fields = list(dict.fromkeys(k for r in values for k in r))
        with (HERE / filename).open('w') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(values)


def plot(result):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    positive = [r['error_km'] for r in result['rows'] if r['accepted'] and r['error_km'] > 0]
    lower = min(.01, 10. ** np.floor(np.log10(min(positive))))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
    for ax, arm in zip(axes, ARMS):
        for phase in VARIANTS:
            errors = sorted(r['error_km'] for r in result['rows'] if r['arm'] == arm and r['phase'] == phase and r['accepted'])
            ax.step([lower, *errors, 500], [0, *np.arange(1, len(errors) + 1) / 64 * 100, len(errors) / 64 * 100],
                    where='post', color=COLORS[phase], label=NAMES[phase], lw=1.8)
        ax.axvline(5, color='#777', lw=.7, ls=':')
        ax.set(title=arm, xscale='log', xlim=(lower, 500), ylim=(0, 102),
               xlabel='Horizontal position error (km)', ylabel='Scans at or below error (% of all 64)')
        ax.grid(alpha=.2)
        ax.legend(loc='upper left', fontsize=9)
    fig.suptitle('N01–N64: baseline and three controlled variants')
    for suffix in ('png', 'svg'):
        fig.savefig(HERE / f'position_comparison.{suffix}', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(16, 8), sharex=True, layout='constrained')
    for ax, arm in zip(axes, ARMS):
        for phase in VARIANTS:
            group = sorted((r for r in result['rows'] if r['arm'] == arm and r['phase'] == phase), key=lambda r: r['label'])
            ax.plot([int(r['label'][1:]) for r in group], [r['error_km'] if r['accepted'] else np.nan for r in group],
                    '.-', ms=4, lw=.7, alpha=.85, color=COLORS[phase], label=NAMES[phase])
        ax.axhline(5, color='#777', ls=':', lw=.8)
        ax.set(title=arm, yscale='log', ylabel='Position error (km)', ylim=(lower, 500), xlim=(.5, 64.5))
        ax.grid(alpha=.2)
        ax.legend(ncol=4, fontsize=9)
    axes[-1].set_xticks(range(1, 65), [f'N{i:02}' for i in range(1, 65)], rotation=90, fontsize=7)
    fig.suptitle('Same 64 scans, fixed budgets; locations selected by model score')
    for suffix in ('png', 'svg'):
        fig.savefig(HERE / f'per_scan_errors.{suffix}', dpi=160)
    plt.close(fig)


def report(result):
    lines = ['N01--N64: baseline and three variants', '',
        'Baseline: sigma .15 s, no affine-slope bound, 100/50/25/12.5 km, legacy edge priority.',
        'All variants: corrected edge priority, 40/20/10/5 km; 400 scores, three regions, same fitting budgets.',
        'after = sigma 1 s / +/-60 Hz/s; sigma2_60 = sigma 2 s / +/-60 Hz/s; sigma1_30 = sigma 1 s / +/-30 Hz/s.',
        'Original baseline and after results are reused verbatim from the hash-verified prior comparison.',
        'New passes refit all point scores and regions; only method-independent geometric bootstrap seeds are reused.',
        'Relative satellite timing sigma changes; common timing sigma remains 3 s.',
        'Slope bounds are hard, separately on each fitted affine term. Frozen baseline plus final and piecewise drift may exceed them.',
        'Reference coordinates are used only after fitting and model-score selection.',
        'Final-stage c ablation: both arms share discovery/calibration/association, observations, satellite bank, starts, priors and budgets.',
        'Discovery/calibration/association retain fitted c. This is not an end-to-end zero-c ablation.',
        'Frequency RMS is posterior-weighted in-sample; scores across different priors are not a localization metric.',
        'Runtime is affected by concurrency and cache reuse; these wall times are not independent performance benchmarks.', '']
    for arm in ARMS:
        lines.append(arm)
        for phase in VARIANTS:
            s = result['summary'][arm][phase]
            d = s['position_error_km']
            lines.append(f"  {NAMES[phase]}: accepted {s['accepted']}/64; median {d.get('median', float('nan')):.3f} km; p90 {d.get('p90', float('nan')):.3f}; p95 {d.get('p95', float('nan')):.3f}; max {d.get('maximum', float('nan')):.3f}; >100 km {d.get('over100', 0)}; <5 km {d.get('under5', 0)}; median frequency RMS {s['median_frequency_rms_hz']} Hz.")
            if phase != 'before':
                for name in ('versus_baseline', 'versus_sigma1_60'):
                    p = s[name]
                    lines.append(f"    {name}: {p['count']} paired scans, improved {p['improved']}, worsened {p['worsened']}, unchanged {p['unchanged']}; median paired change {p['median_change_km']} km.")
        lines.append('')
    lines.append('Cases N13, N56 and N64 (selected error / best accepted candidate error; truth never selects winner):')
    for label in ('N13', 'N56', 'N64'):
        for arm in ARMS:
            values = []
            for phase in VARIANTS:
                r = next(r for r in result['rows'] if r['label'] == label and r['arm'] == arm and r['phase'] == phase)
                values.append(f"{NAMES[phase]} {r['error_km']} / {r['best_available_candidate_error_km']} km; reference covered {r['reference_in_retained_region']}")
            lines.append(f"  {label} {arm}: " + ' | '.join(values))
    lines.append('')
    for phase in VARIANTS:
        group = [r for r in result['searches'] if r['phase'] == phase]
        lines.append(f"{NAMES[phase]}: reference in retained regions {sum(r['reference_in_retained_region'] for r in group)}/64; failed grid scores {sum(r['failed'] for r in group)}; timed-out grid fits {sum(r['time_limited'] for r in group)}; failed regions {sum(r['phase'] == phase for r in result['region_failures'])}.")
    lines.append('New grid failures remain in the fixed 400-attempt budget; they were not selectively retried:')
    for failure in result['grid_failures']:
        lines.append(f"  {failure['label']} {failure['phase']} {failure['point']}: {failure['error']}")
    (HERE / 'findings.txt').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--partial', action='store_true')
    evaluate(partial=parser.parse_args().partial)
