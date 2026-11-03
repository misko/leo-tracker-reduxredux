"""Geographic evaluation after score selection; cached terminal-case extraction."""
import argparse
import collections
import csv
import json
from pathlib import Path
import numpy as np
import run_soft as run
from summarize import distance_km, distribution, reference_point
from slope_penalty import penalty
from leo.contracts.regional_position import RegionalPrior
from leo.analysis.regional_position_score import coordinates

HERE, OLD, PREVIOUS = run.HERE, run.OLD, run.PREVIOUS
ARMS = ('zero-c', 'fitted-c')
MAIN = ('sigma2_60', 'gaussian60', 'smooth60', 'hard30', 'gaussian30', 'smooth30')
VARIANTS = ('before', 'after', 'sigma1_30', *MAIN)
NAMES = dict(before='Original baseline', after='1 s / hard 60', sigma1_30='1 s / hard 30',
             sigma2_60='Hard 60', hard30='Hard 30', gaussian60='Gaussian 60', smooth60='Smooth 60',
             gaussian30='Gaussian 30', smooth30='Smooth 30')
COLORS = dict(sigma2_60='#1876a3', hard30='#375b75', gaussian60='#d86c29', gaussian30='#9d4320',
              smooth60='#238b57', smooth30='#7d4399')


def read(path):
    return json.loads(Path(path).read_text())


def root(phase):
    if phase in ('before', 'after'):
        return OLD
    if phase in ('sigma2_60', 'sigma1_30'):
        return PREVIOUS
    return HERE


def case_rows(label, phase, reference, signature):
    folder = HERE / 'results' / label / phase
    path = folder / 'result.json'
    cache_path = HERE / 'evaluation_cache' / f'{label}_{phase}.json'
    key = dict(result_sha256=run.data.digest(path), analysis_sha256=signature, reference=reference)
    if cache_path.exists():
        cached = read(cache_path)
        if cached['key'] == key:
            return cached['value']
    d = read(OLD / 'inputs' / label / 'inputs.json')
    prior = RegionalPrior(**d['prior'])
    truth = reference_point(prior, reference)
    result = read(path)
    search = read(folder / 'search.json')
    points = search['search']['evaluations']
    assert len(points) == len({(p['east_km'], p['north_km']) for p in points}) == 400
    errors = [dict(label=label, phase=phase, **r) for r in result['region_status'] if r['status'] != 'complete']
    grid_errors = [dict(label=label, phase=phase, **r) for r in search['rows'] if r['status'] == 'failed']
    regions = {tuple(v['point']): v for p in (folder / 'regions').glob('*.json') for v in [read(p)]}
    candidates = [r for region in regions.values() for r in region['candidates']]
    covered = any(np.linalg.norm(np.array([b['east_km'], b['north_km']]) - truth)
                  <= max(25., b['spacing_km'] / np.sqrt(2)) for b in result['basins'])
    search_row = dict(label=label, phase=phase, points=len(points), failed=len(grid_errors),
        converged=sum(r['converged'] is True for r in search['rows']),
        time_limited=sum(r['stop_reason'] == 'time-budget' for r in search['rows']),
        levels=dict(collections.Counter(str(p['spacing_km']) for p in points)),
        outside_240km=sum(np.hypot(p['east_km'], p['north_km']) >= 240 for p in points),
        nearest_grid_point_km=min(float(np.linalg.norm(np.array([p['east_km'], p['north_km']]) - truth)) for p in points),
        reference_in_retained_region=covered, elapsed_s=result['elapsed_s'])
    rows = []
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
            region = regions[tuple(selected['point'])]
            correction = region['calibration']['correction']
            piecewise = np.diff(np.asarray(correction['knots_hz']), axis=1) / np.diff(correction['nodes_s'])
            total = piecewise + np.asarray(selected['combined_affine_slopes_hz_s'])[:, None]
            lat, lon = coordinates(prior, selected['vector'][:2])
            row.update(error_km=distance_km(lat, lon, reference), latitude_deg=lat, longitude_deg=lon,
                frequency_rms_hz=selected['frequency_rms_hz'], timing_penalty=selected['timing_penalty'],
                slope_penalty=selected['slope_penalty'], frozen_slope_penalty=selected['frozen_slope_penalty'],
                unpenalized_objective=selected['unpenalized_objective'],
                signal_windows=selected['signal_windows'], signal_fraction=selected['signal_windows'] / d['observation_count'],
                data_nll=selected['data_nll'], selection_score=selected['selection_score'],
                rx0_slope_hz_s=selected['additional_slopes_hz_s'][0], rx1_slope_hz_s=selected['additional_slopes_hz_s'][1],
                rx0_combined_affine_hz_s=selected['combined_affine_slopes_hz_s'][0],
                rx1_combined_affine_hz_s=selected['combined_affine_slopes_hz_s'][1],
                rx0_total_drift_min_hz_s=float(total[0].min()), rx0_total_drift_max_hz_s=float(total[0].max()),
                rx1_total_drift_min_hz_s=float(total[1].min()), rx1_total_drift_max_hz_s=float(total[1].max()),
                slope_bound_active=bool(selected['slope_active_bounds']), spatial_boundary=selected['boundary'],
                stationarity=selected['stationarity'], origin=selected['origin'],
                region_east_km=selected['point'][0], region_north_km=selected['point'][1])
        rows.append(row)
    value = dict(rows=rows, search=search_row, region_failures=errors, grid_failures=grid_errors)
    run.engine.write(cache_path, dict(key=key, value=value))
    return value


def paired(rows, arm, phase, reference):
    groups = [{r['label']: r for r in rows if r['arm'] == arm and r['phase'] == p} for p in (reference, phase)]
    left, right = groups
    pairs = [dict(label=label, reference_km=left[label]['error_km'], variant_km=right[label]['error_km'],
                  change_km=right[label]['error_km'] - left[label]['error_km'])
             for label in sorted(left.keys() & right.keys()) if left[label]['accepted'] and right[label]['accepted']]
    return dict(reference=reference, count=len(pairs), improved=sum(r['change_km'] < 0 for r in pairs),
        worsened=sum(r['change_km'] > 0 for r in pairs), unchanged=sum(r['change_km'] == 0 for r in pairs),
        median_change_km=float(np.median([r['change_km'] for r in pairs])) if pairs else None,
        largest_improvements=sorted(pairs, key=lambda r: r['change_km'])[:5],
        largest_regressions=sorted(pairs, key=lambda r: -r['change_km'])[:5])


def evaluate(partial=False):
    protocol = read(HERE / 'protocol.json')
    for path, expected in protocol['sources'].items():
        assert run.data.digest(path) == expected, path
    previous = read(PREVIOUS / 'summary.json')
    rows, searches = list(previous['rows']), list(previous['searches'])
    region_failures, grid_failures = list(previous['region_failures']), list(previous['grid_failures'])
    reference_doc = read(OLD / 'evaluation.json')
    reference = [reference_doc['reference_latitude_deg'], reference_doc['reference_longitude_deg']]
    (HERE / 'evaluation_cache').mkdir(exist_ok=True)
    signature = run.data.digest(__file__)
    for label in run.LABELS:
        for phase in run.PHASES:
            if not (HERE / 'results' / label / phase / 'result.json').exists():
                if partial:
                    continue
                raise ValueError(f'Missing result {label} {phase}')
            case = case_rows(label, phase, reference, signature)
            rows.extend(case['rows']); searches.append(case['search'])
            region_failures.extend(case['region_failures']); grid_failures.extend(case['grid_failures'])
    summary = {}
    for arm in ARMS:
        summary[arm] = {}
        for phase in VARIANTS:
            group = [r for r in rows if r['arm'] == arm and r['phase'] == phase]
            accepted = [r for r in group if r['accepted']]
            own_control = 'hard30' if phase in ('hard30', 'gaussian30', 'smooth30') else 'sigma2_60'
            summary[arm][phase] = dict(completed=len(group), accepted=len(accepted), failed=len(group) - len(accepted),
                position_error_km=distribution([r['error_km'] for r in accepted]),
                median_frequency_rms_hz=float(np.median([r['frequency_rms_hz'] for r in accepted])) if accepted else None,
                median_signal_fraction=float(np.median([r['signal_fraction'] for r in accepted])) if accepted else None,
                median_slope_penalty=float(np.median([r.get('slope_penalty', 0.) for r in accepted])) if accepted else None,
                median_frozen_slope_penalty=float(np.median([r.get('frozen_slope_penalty', 0.) for r in accepted])) if accepted else None,
                slope_bound_active=sum(r['slope_bound_active'] for r in accepted),
                spatial_boundary=sum(r['spatial_boundary'] for r in accepted),
                versus_baseline=paired(rows, arm, phase, 'before'),
                versus_hard60=paired(rows, arm, phase, 'sigma2_60'),
                versus_own_hard_control=paired(rows, arm, phase, own_control))
    result = dict(complete=len(searches) == 576, completed_phases=len(searches), new_completed=len(searches) - 256,
                  summary=summary, rows=rows, searches=searches, region_failures=region_failures,
                  grid_failures=grid_failures, protocol_hash=run.data.digest(HERE / 'protocol.json'))
    run.engine.write(HERE / ('partial_summary.json' if partial else 'summary.json'), result)
    if not partial:
        export(result)
        from plot_soft import plot_results
        plot_results(result)
        write_report(result)
    print(json.dumps(dict(complete=result['complete'], new_completed=result['new_completed'],
        stats={a: {p: {k: v for k, v in s.items() if not k.startswith('versus_')} for p, s in ss.items() if p in MAIN}
               for a, ss in summary.items()}), indent=2))
    return result


def export(result):
    wide = {}
    control = {(r['label'], r['arm']): r for r in result['rows'] if r['phase'] == 'sigma2_60'}
    for r in result['rows']:
        target = wide.setdefault(r['label'], {k: r[k] for k in ('label', 'session_id', 'capture_local', 'time_block')})
        prefix = r['arm'].replace('-', '_') + '_' + r['phase']
        for key in ('error_km', 'accepted', 'frequency_rms_hz'):
            target[prefix + '_' + key] = r[key]
        b = control[r['label'], r['arm']]
        target[prefix + '_change_from_hard60_km'] = r['error_km'] - b['error_km'] if r['accepted'] and b['accepted'] else None
    for filename, values in [('comparison.csv', [wide[k] for k in sorted(wide)]),
                             ('results_long.csv', result['rows']), ('search_diagnostics.csv', result['searches'])]:
        fields = list(dict.fromkeys(k for r in values for k in r))
        with (HERE / filename).open('w') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows(values)


def write_report(result):
    lines = ['N01--N64: Gaussian and smooth affine-slope priors', '',
        'Primary six variants all use relative timing sigma 2 s, common timing sigma 3 s, corrected 40/20/10/5 km search.',
        'Historical baseline: timing sigma .15 s, unbounded affine slopes, 100/50/25/12.5 km and legacy edge priority. Historical 1-second controls use the corrected grid with hard +/-60 or +/-30 Hz/s.',
        'Hard 60 and Hard 30 have no soft slope penalty. Gaussian 60/30 use zero-mean standard deviations 20/10 Hz/s.',
        'Smooth 60/30 are flat through +/-30 or +/-15 Hz/s, then add .5*(excess/10)^2 or .5*(excess/5)^2.',
        'All retain their named hard outer limit. Both penalty shapes cost 4.5 NLL units per receiver at that limit.',
        'Priors act on separate fitted affine terms at every fitting stage. Combined physical drift is reported separately.',
        'Selection score includes final data NLL, timing prior, final affine prior, original piecewise calibration prior, and the frozen postfit affine prior once. The preliminary prefit prior is not counted again.',
        'All final fits are rerun per variant; only geometric bootstrap seeds are reused. Previous verified hard-bound results are immutable references.',
        'Each scan/variant has 400 grid attempts, three distinct regions and the same optimizer budgets and start rules.',
        'Final-stage c=0 versus fitted-c share observations, calibration, association banks, initial starts, priors and budgets within each variant. Discovery and calibration retain fitted c.',
        'Reference coordinates are only read after selection and never select the winning state.',
        'Frequency RMS is posterior-weighted in-sample fit, separate from geographic error. Objective totals across priors are not a localization metric.',
        'This is a comparison on the existing cohort, not an independent held-out estimate. Runtime is affected by cache reuse and concurrency.', '']
    for arm in ARMS:
        lines.append(arm)
        for phase in VARIANTS:
            s = result['summary'][arm][phase]; d = s['position_error_km']
            lines.append(f"  {NAMES[phase]}: accepted {s['accepted']}/64; median {d.get('median', float('nan')):.3f} km; p90 {d.get('p90', float('nan')):.3f}; p95 {d.get('p95', float('nan')):.3f}; max {d.get('maximum', float('nan')):.3f}; mean {d.get('mean', float('nan')):.3f}; >100 km {d.get('over100', 0)}; <5 km {d.get('under5', 0)}; median frequency RMS {s['median_frequency_rms_hz']} Hz.")
            if phase in MAIN:
                for field in ('versus_hard60', 'versus_own_hard_control'):
                    p = s[field]
                    lines.append(f"    {field} ({p['reference']}): {p['count']} paired; improved {p['improved']}, worsened {p['worsened']}, unchanged {p['unchanged']}; median paired change {p['median_change_km']} km.")
        lines.append('')
    lines.append('Watch cases, error km for score-selected winner:')
    for label in ('N02', 'N05', 'N13', 'N25', 'N29', 'N39', 'N49', 'N56', 'N64'):
        for arm in ARMS:
            group = [next(r for r in result['rows'] if r['label'] == label and r['arm'] == arm and r['phase'] == p) for p in MAIN]
            lines.append(f"  {label} {arm}: " + ' | '.join(f"{NAMES[r['phase']]} {r['error_km']}; reference covered {r['reference_in_retained_region']}" for r in group))
    lines.append('')
    for phase in VARIANTS:
        group = [r for r in result['searches'] if r['phase'] == phase]
        lines.append(f"{NAMES[phase]}: reference in retained regions {sum(r['reference_in_retained_region'] for r in group)}/64; failed grid scores {sum(r['failed'] for r in group)}; timed-out grid fits {sum(r['time_limited'] for r in group)}; failed regions {sum(r['phase'] == phase for r in result['region_failures'])}.")
    lines.append('All failures remain in the fixed-budget result; no selective retries. Details: summary.json.')
    (HERE / 'findings.txt').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--partial', action='store_true')
    evaluate(partial=parser.parse_args().partial)
