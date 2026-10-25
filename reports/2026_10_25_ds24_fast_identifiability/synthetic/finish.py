"""Replay original gates at frozen synthetic endpoints and summarize all results.

No position optimization, association selection, propagation search or real GPS.
"""

from collections import Counter
import csv
import json
from pathlib import Path
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import experiment as e
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile, whitening


def screen_flags(diagnostics, n, prefix):
    thresholds = dict(mean_z=3., slope_z=3., quadratic_bic_gain=10., maximum_step_z=4.,
                      lag1_acf=4 / np.sqrt(n))
    return {prefix + key: bool(abs(diagnostics[key]) <= limit) if key == 'lag1_acf'
            else bool(diagnostics[key] <= limit) for key, limit in thresholds.items()}


def vector_diagnostics(screen):
    return {key: float(value[0]) for key, value in screen.items() if key != 'noise_screen_pass'}


def replay_gates(d, scan, node, entries, row):
    p = e.build(d, scan, node, entries, row['arm'], row['phase_reference'])
    x = np.asarray(row['endpoint_east_north_km'])
    c, state = p.calculate(x), p.state(x)
    frequency, elevation = p.conditional_frequency(x)
    expected = {track['component']: track for track in row['gates']['tracks']}
    records = []
    for source, i, sl, alias in zip(p.rows, p.members, p.slices, p.alias, strict=True):
        track, active = scan.tracks[i], p.keep[sl]
        if not active.any(): continue
        times = track['times'][active]; n = len(times); q = track['rf_hz'] / 11.5e9
        corrected = track['values'] - scan.hardware(track, state['beta'])
        corrected -= q * scan.rx_basis[i] @ state['smooth'][track['receiver'] - 1]
        terms = profile(corrected[active], q * frequency[sl][active], *whitening(times))
        raw_screen = vector_diagnostics(batch_noise_screen(terms['innovations'], times))
        conditional = c['conditional_residual_hz'][sl][active]
        conditional_screen = vector_diagnostics(batch_noise_screen(conditional[None, :], times))
        checks = screen_flags(raw_screen, n, 'profile_')
        checks.update(screen_flags(conditional_screen, n, 'conditional_'))
        checks.update(profile_RMS=bool(terms['rms'][0] <= 450),
            profile_bias=bool(abs(terms['bias'][0]) <= 3000),
            conditional_RMS=bool(np.sqrt(np.mean(conditional ** 2)) <= 450),
            alias=bool(int(terms['alias'][0]) == alias),
            visibility=bool(elevation[sl][active].min() >= 0))
        record = dict(component=track['key'], candidate_index=source['candidate_index'],
            points=n, receiver=track['receiver'], channel=track['channel'],
            checks=checks, failed_predicates=[key for key, passed in checks.items() if not passed],
            before_support_passed=all(checks.values()), profile_noise=raw_screen,
            conditional_noise=conditional_screen,
            conditional_RMS_hz=float(np.sqrt(np.mean(conditional ** 2))),
            profile_RMS_hz=float(terms['rms'][0]), profile_bias_hz=float(terms['bias'][0]))
        record['after_support_passed'] = record['before_support_passed']
        records.append(record)
    changed = True
    while changed:
        owners = {}
        for record in records:
            if record['after_support_passed']:
                owners.setdefault(record['candidate_index'], set()).add((record['receiver'], record['channel']))
        changed = False
        for record in records:
            if (record['after_support_passed'] and record['candidate_index'] in p.supported
                    and len(owners[record['candidate_index']]) < 2):
                record['after_support_passed'] = False; changed = True
                record['failed_predicates'].append('owner_support_cascade')
    for record in records:
        assert record['after_support_passed'] == expected[record['component']]['compatible']
    predictive = []
    for entry, sl, saved in zip(entries, getattr(p, 'linear_slices', []), row['linear_gates'], strict=True):
        track = scan.tracks[entry['track_index']]
        residual = c['linear_raw_prediction_residual_hz'][sl]
        terms = profile(residual, np.zeros(len(residual)), *scan.white[entry['track_index']], bias_sigma=300.)
        diagnostics = vector_diagnostics(batch_noise_screen(terms['innovations'], track['times']))
        checks = screen_flags(diagnostics, len(residual), 'predictive_')
        checks.update(RMS=bool(terms['rms'][0] <= 450), bias=bool(abs(terms['bias'][0]) <= 3000),
            alias=bool(int(terms['alias'][0]) == 0), visibility=bool(c['linear_elevation'][sl].min() >= 0))
        assert all(checks.values()) == saved['compatible']
        predictive.append(dict(component=entry['component'], points=len(residual), checks=checks,
            failed_predicates=[key for key, passed in checks.items() if not passed],
            noise=diagnostics, RMS_hz=float(terms['rms'][0]), bias_hz=float(terms['bias'][0])))
    assert abs(c['negative_twice_elbo'] - row['negative_twice_elbo']) < 1e-7
    assert e.final_checks(p, x, row)['passed'] == row['qualification']['passed']
    return dict(curved=records, predictive=predictive, objective_replay_difference=
        float(c['negative_twice_elbo'] - row['negative_twice_elbo']))


def main():
    started = time.monotonic(); e.verify()
    execution = e.r.read(e.HERE / 'execution.json')
    seal = e.r.read(e.HERE / 'scientific_seal.json')
    for path, expected in seal['files'].items(): assert e.sha(path) == expected
    assert execution['attempted_fits'] == 24
    rows = sorted(execution['rows'], key=lambda row: (row['case'], row['site_index'], row['variant'], row['arm']))
    audits, flat = [], []
    for row in rows:
        if row['status'] != 'complete': continue
        d = e.context(row['case']); scan, node, entries, truth = e.synthesize(d, row['site_index'], row['variant'])
        assert truth['observations_sha256'] == row['observations_sha256']
        audit = dict(case=row['case'], site_index=row['site_index'], variant=row['variant'], arm=row['arm'],
            **replay_gates(d, scan, node, entries, row))
        audits.append(audit)
        diagnostic = row['fixed_objective_diagnostics']
        final = diagnostic['endpoint_at_final_reference']; target = diagnostic['truth_at_final_reference']
        flat.append(dict(case=row['case'], site=row['site_index'], variant=row['variant'], arm=row['arm'],
            error_km=row['synthetic_position_error_km'], qualified=row['qualification']['passed'],
            phase_change_s=row['final_phase_change_s'], Gamma_change=final['final_log_precision_change'],
            forward_identity_error_hz=diagnostic['known_forward_closure']['maximum_known_forward_mean_identity_error_hz'],
            final_minus_truth_objective=final['total_negative_twice_elbo'] - target['total_negative_twice_elbo'],
            weighted_residual_change=final['parent_weighted_residual_energy'] - target['parent_weighted_residual_energy'],
            mean_prior_change=final['parent_latent_mean_prior_energy'] - target['parent_latent_mean_prior_energy'],
            logvolume_change=final['logvolume'] - target['logvolume'],
            noise_Gamma_change=final['noise_gamma_cost'] - target['noise_gamma_cost'],
            prior_Gamma_change=final['prior_gamma_cost'] - target['prior_gamma_cost'],
            predictive_change=final['predictive_objective'] - target['predictive_objective'],
            truth_gradient_norm=float(np.linalg.norm(target['objective_gradient_per_km'])),
            final_gradient_norm=float(np.linalg.norm(final['objective_gradient_per_km']))))
    e.r.write_new(e.HERE / 'gate_replay.json', dict(all_passed=True,
        meaning='all saved gate decisions replay, including expected null rejections', rows=audits,
        position_fits=0, real_GPS_used=False, seconds=time.monotonic() - started,
        protocol_sha256=e.sha(e.PROTOCOL), scientific_seal_sha256=e.sha(e.HERE / 'scientific_seal.json'),
        source_sha256=e.sha(__file__)))
    with (e.HERE / 'per_fit.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat[0])); writer.writeheader(); writer.writerows(flat)
    counters = {}
    for variant in e.VARIANTS:
        chosen = [audit for audit in audits if audit['variant'] == variant]
        counters[variant] = {role: dict(Counter(key for audit in chosen for track in audit[role]
            for key in track['failed_predicates'])) for role in ('curved', 'predictive')}
    summary = dict(completed=execution['completed'], failures=execution['failed'], seconds=execution['seconds'],
        maximum_forward_identity_error_hz=max(row['forward_identity_error_hz'] for row in flat),
        gate_failure_counts=counters, summaries=[], position_fits=24, real_GPS_used=False,
        association_selection_tested=False)
    for mode in ('noiseless_null', 'stochastic'):
        for arm in e.ARMS:
            chosen = [row for row in flat if row['arm'] == arm and
                ((row['variant'] == mode) if mode == 'noiseless_null' else row['variant'].startswith(mode))]
            values = np.array([row['error_km'] for row in chosen])
            summary['summaries'].append(dict(mode=mode, arm=arm, fits=len(chosen), qualified=sum(row['qualified'] for row in chosen),
                mean_error_km=float(values.mean()), median_error_km=float(np.median(values)),
                minimum_error_km=float(values.min()), maximum_error_km=float(values.max())))
    e.r.write_new(e.HERE / 'summary.json', summary)
    figures = e.HERE / 'figures'; figures.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    for ax, mode in zip(axes, ('noiseless_null', 'stochastic')):
        chosen = [row for row in flat if (row['variant'] == mode if mode == 'noiseless_null' else row['variant'].startswith(mode))]
        labels = sorted({(row['case'], row['site'], row['variant']) for row in chosen})
        for arm, offset, color in [('c0', -.14, '#2563eb'), ('fitted_c', .14, '#dc2626')]:
            values = [next(row for row in chosen if (row['case'], row['site'], row['variant']) == label and row['arm'] == arm) for label in labels]
            ax.bar(np.arange(len(labels)) + offset, [row['error_km'] * (1000 if mode == 'noiseless_null' else 1) for row in values],
                width=.25, color=color, label=arm, alpha=.8)
        ax.set_xticks(np.arange(len(labels)), [f'{case[-4:]} S{site}'+(' D'+variant[-1] if mode != 'noiseless_null' else '') for case, site, variant in labels], rotation=55)
        ax.set_ylabel('Artificial position error (' + ('m)' if mode == 'noiseless_null' else 'km)'))
        ax.set_title('Noiseless: 0/8 original gate qualification' if mode == 'noiseless_null' else 'Stochastic: 16/16 original gate qualification')
        ax.grid(axis='y', alpha=.25); ax.legend()
    fig.suptitle('Known labels/aliases and inherited selection; no association test')
    fig.savefig(figures / 'synthetic_errors.png', dpi=150); plt.close(fig)
    null = [row for row in flat if row['variant'] == 'noiseless_null' and row['arm'] == 'c0']
    fields = [('weighted_residual_change', 'weighted residual'), ('mean_prior_change', 'mean prior'),
        ('logvolume_change', 'volume'), ('noise_Gamma_change', 'noise Gamma'),
        ('prior_Gamma_change', 'phase Gamma'), ('predictive_change', 'predictive')]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    for index, row in enumerate(null):
        axes[0].plot(np.arange(len(fields)), [row[key] for key, label in fields], marker='o', label=f"{row['case'][-4:]} S{row['site']}")
    axes[0].set_xticks(np.arange(len(fields)), [label for key, label in fields], rotation=35)
    axes[0].set_ylabel('Endpoint minus truth objective contribution'); axes[0].axhline(0, color='black', lw=.6); axes[0].legend(); axes[0].grid(alpha=.2)
    axes[1].bar(np.arange(len(null)) - .16, [row['truth_gradient_norm'] for row in null], width=.3, label='at truth')
    axes[1].bar(np.arange(len(null)) + .16, [row['final_gradient_norm'] for row in null], width=.3, label='at endpoint')
    axes[1].set_xticks(np.arange(len(null)), [f"{row['case'][-4:]} S{row['site']}" for row in null])
    axes[1].set_ylabel('Objective gradient norm / km'); axes[1].legend(); axes[1].grid(axis='y', alpha=.2)
    fig.suptitle('c=0 null diagnostics at each fit\'s same final phase reference; no refit')
    fig.savefig(figures / 'null_objective_components.png', dpi=150); plt.close(fig)
    files = [e.HERE / name for name in ('finish.py', 'gate_replay.json', 'per_fit.csv', 'summary.json')] + sorted(figures.glob('*.png'))
    e.r.write_new(e.HERE / 'report_data_seal.json', dict(files={str(path): e.sha(path) for path in files},
        scientific_seal_sha256=e.sha(e.HERE / 'scientific_seal.json'), real_GPS_used=False))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__': main()
