"""Replay whole-scan association coverage at frozen ALGO02 endpoints and plot it."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from functools import lru_cache
from pathlib import Path

import numpy as np

from algo02_scan import bind_run_directory, load_scan
from audit_ds23_algo01_coverage import coverage
from ds23_predictive_linear import attach_predictive_linear
from evaluate_ds23_phase_refreshed import extend_associations
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import make_problem
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT, read, write, sha

SOURCE = ROOT / 'reports/2026_10_19_algo02_ds23_full'
OUT = ROOT / 'reports/2026_10_20_algo02_ds23_association_error'
ARMS = ('c0', 'fitted_c')


def audit(case):
    path = OUT / 'memberships' / (case + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    original_path = SOURCE / case / 'algo02_result.json'
    if path.exists():
        result = read(path)
        assert result['source_sha256'] == sha(original_path)
        return result
    bind_run_directory(SOURCE)
    old = read(original_path)
    assert old['status'] == 'accepted' and not old['GPS_used'] and not old['future_TLE_used']
    scan = load_scan(SOURCE, case)
    node = read(SOURCE / case / 'result.json')['final_node']
    keep, powers = np.asarray(old['mask'], bool), np.asarray(old['weights'])
    labels = sorted({r['candidate_index'] for r in node['seed']['rows']})
    model = old['hyperparameters_from_pre_RF_TLE_only']
    _, receipts = phase_widths(scan, labels)
    means = forecast_phase_mean(receipts, model['shrinkage'])
    observations = read(SOURCE / case / 'observations.json')
    ids = {o['observation_id'] for o in observations}
    assert len(ids) == len(observations)
    results = {}
    for arm in ARMS:
        saved = old['policy_arms'][arm]
        x = np.asarray(saved['endpoint_east_north_km'])
        p = make_problem(scan, node, keep, arm, np.asarray(saved['phase_reference']),
                         powers, means, model['multiplier'], model['nu'])
        entries = old['linear_entries'] if old['linear_paired_valid'] else []
        attach_predictive_linear(p, entries, powers)
        calculate = p.calculate
        @lru_cache(maxsize=2)
        def cached(position):
            return calculate(np.asarray(position))
        p.calculate = lambda position: cached(tuple(position))
        difference = float(p.calculate(x)['negative_twice_elbo'] - saved['negative_twice_elbo'])
        # Hierarchical Gamma precision iteration can vary at ~1e-8 relative
        # bound precision on replay; this is far below association gate scales.
        if abs(difference) > max(1e-5, 1e-8 * abs(saved['negative_twice_elbo'])):
            raise ValueError(f'{case} {arm}: objective replay differs by {difference}')
        extension = extend_associations(p, x, saved['gates'])
        # Preserve the actual qualified position-evidence owners, then attach
        # remaining graph tracks using frozen calibration. Never inflate a
        # partially retained curve to all of its original observations.
        accepted = {r['component']: r for r in extension['tracks']}
        for row in saved.get('linear_gates', []):
            if row['compatible']:
                accepted[row['component']] = row
        for row in saved['gates']['tracks']:
            if row['compatible']:
                accepted[row['component']] = row
        counts = coverage(list(accepted.values()), scan.tracks, ids)
        assert counts['associated_additional_peaks'] == 0
        assert counts['associated_original_winners'] <= len(ids)
        results[arm] = dict(**counts, error_km=position_error(saved['endpoint_latlon']),
                           position_evidence_points=saved['active_points'] + old['linear_used_points'],
                           objective_replay_difference=difference, tracks=list(accepted.values()))
    result = dict(case=case, algorithm='ALGO02-v1', source_sha256=sha(original_path),
                  observations_sha256=sha(SOURCE / case / 'observations.json'), arms=results,
                  no_position_refit=True, no_new_candidates=True, no_IQ_reread=True)
    write(path, result)
    return result


def collect(workers):
    with (SOURCE / 'case_summary.csv').open() as f:
        cases = [r['case'] for r in csv.DictReader(f) if r['status'] == 'accepted']
    errors = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(audit, case): case for case in cases}
        for n, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
            except Exception as exc:
                errors.append(dict(case=futures[future], error=repr(exc)))
                print('FAILED', futures[future], repr(exc), flush=True)
            if n % 25 == 0 or n == len(cases):
                print(f'coverage replay {n}/{len(cases)}; errors={len(errors)}', flush=True)
    write(OUT / 'execution.json', dict(cases=len(cases), errors=errors, workers=workers))
    if errors:
        raise RuntimeError('Coverage audit incomplete; see execution.json')


def ranks(x):
    values, inverse, counts = np.unique(x, return_inverse=True, return_counts=True)
    ends = np.cumsum(counts)
    return ((ends - counts + 1 + ends) / 2)[inverse]


def plot(quantity='percent'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with (SOURCE / 'case_summary.csv').open() as f:
        cases = list(csv.DictReader(f))
    rows = []
    for case in cases:
        if case['status'] != 'accepted':
            continue
        document = read(OUT / 'memberships' / (case['case'] + '.json'))
        for arm in ARMS:
            r = document['arms'][arm]
            assert r['original_winning_GLRT_points'] == int(case['GLRT_points'])
            rows.append(dict(case=case['case'], arm=arm,
                format='Fast' if case['recording_format'] == 'short_window_iq_recording' else 'Adaptive',
                GLRT_points=r['original_winning_GLRT_points'],
                associated_GLRT_points=r['associated_original_winners'],
                associated_GLRT_percent=r['associated_original_percent'],
                associated_tracks=r['associated_tracks'], position_error_km=r['error_km'],
                position_evidence_points=r['position_evidence_points']))
    with (OUT / 'association_vs_error.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    xfield = 'associated_GLRT_percent' if quantity == 'percent' else 'associated_GLRT_points'
    summary = {}
    for arm in ARMS:
        summary[arm] = {}
        for fmt in ('All', 'Fast', 'Adaptive'):
            selected = [r for r in rows if r['arm'] == arm and (fmt == 'All' or r['format'] == fmt)]
            x = np.array([r[xfield] for r in selected])
            y = np.array([r['position_error_km'] for r in selected])
            summary[arm][fmt] = dict(scans=len(x), mean_associated=float(x.mean()),
                median_associated=float(np.median(x)), mean_error_km=float(y.mean()),
                median_error_km=float(np.median(y)), pearson_r=float(np.corrcoef(x, y)[0, 1]),
                spearman_rho=float(np.corrcoef(ranks(x), ranks(y))[0, 1]))
    write(OUT / ('summary.json' if quantity == 'percent' else 'count_summary.json'), dict(
          algorithm='ALGO02-v1', horizontal_quantity=quantity, metrics=summary,
          total_scans=len(cases), accepted_scans=len(rows)//2,
          maximum_absolute_objective_replay_difference=max(abs(read(OUT / 'memberships' /
              (r['case'] + '.json'))['arms'][arm]['objective_replay_difference'])
              for r in cases if r['status'] == 'accepted' for arm in ARMS),
          unavailable_scans=[r['case'] for r in cases if r['status'] != 'accepted'],
          definition='Unique accepted original winning GLRT IDs / all winning GLRT IDs per scan; '
          'qualified position evidence plus frozen-calibration graph extensions at saved endpoints.',
          GPS_only_used_for_error_reporting=True))
    colors = {'Fast': '#087f8c', 'Adaptive': '#a647ae'}
    for logarithmic in (False, True):
        fig, axes = plt.subplots(1, 2, figsize=(14, 6.1), sharex=True, sharey=True)
        for ax, arm, title in zip(axes, ARMS, ('$c = 0$', 'Fitted $c$'), strict=True):
            selected = [r for r in rows if r['arm'] == arm]
            for fmt in colors:
                subset = [r for r in selected if r['format'] == fmt]
                ax.scatter([r[xfield] for r in subset],
                           [r['position_error_km'] for r in subset], s=28, alpha=.65,
                           color=colors[fmt], edgecolors='white', linewidths=.35,
                           label=f'{fmt} (n={len(subset)})')
            ax.axhline(.5, color='#444444', linestyle='--', linewidth=1, label='0.5 km')
            # Label the three largest errors per format without hiding outliers.
            for fmt in colors:
                for k, r in enumerate(sorted([r for r in selected if r['format'] == fmt],
                                           key=lambda r: r['position_error_km'], reverse=True)[:3]):
                    ax.annotate(r['case'].replace('DS23-', ''),
                        (r[xfield], r['position_error_km']),
                        xytext=(6, 10 if k % 2 == 0 else -13), textcoords='offset points', fontsize=8,
                        arrowprops=dict(arrowstyle='-',color='#777777',lw=.5))
            metric = summary[arm]['All']
            ax.set_title(f'{title}  |  Spearman ρ = {metric["spearman_rho"]:.2f}', fontsize=13)
            ax.set_xlabel('All GLRT points associated with a satellite (%)' if quantity == 'percent'
                          else 'Number of GLRT points associated with a satellite')
            ax.set_xlim(0, 100 if quantity == 'percent' else max(r[xfield] for r in rows)*1.12)
            ax.grid(alpha=.18); ax.set_axisbelow(True)
            if logarithmic:
                ax.set_yscale('log'); ax.set_ylim(.04, 24)
            else:
                ax.set_ylim(0, 18.5)
            ax.legend(loc='upper right', fontsize=9)
        axes[0].set_ylabel('Position error (km)' + (' — logarithmic scale' if logarithmic else ''))
        fig.suptitle('DS23 · ALGO02 · Associated GLRT ' +
                     ('percentage' if quantity == 'percent' else 'point count') +
                     ' versus position error', fontsize=15)
        fig.text(.5, .025, '404 qualified scans of 413; 3 missing contracts and 6 timeouts have no position error.\n'
                 'Each dot is one scan. Associations replayed at saved endpoints; positions unchanged.',
                 ha='center', fontsize=10)
        fig.tight_layout(rect=(0, .095, 1, .95))
        stem = ('association_vs_position_error' if quantity == 'percent' else
                'associated_GLRT_count_vs_position_error') + ('_log' if logarithmic else '')
        fig.savefig(OUT / (stem + '.png'), dpi=180)
        fig.savefig(OUT / (stem + '.pdf'))
        plt.close(fig)
    print(summary, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('audit', 'plot', 'all'), default='all')
    parser.add_argument('--workers', type=int, default=24)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.stage in ('audit', 'all'):
        collect(args.workers)
    if args.stage in ('plot', 'all'):
        plot()
        plot('count')
