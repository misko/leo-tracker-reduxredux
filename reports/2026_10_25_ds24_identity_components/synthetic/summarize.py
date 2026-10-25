"""Exact gate replay, paired synthetic summaries and simple figures; no refits."""

from collections import Counter
import csv
from pathlib import Path
import signal
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import components as c
import finish as gate_oracle


def main():
    began = time.monotonic(); protocol = c.verify(require_approval=True)
    seal = c.r.read(c.HERE / 'scientific_seal.json')
    for path, expected in seal['files'].items(): assert c.r.sha(path) == expected
    deadline = c.r.read(c.HERE / 'scientific_start.json')['deadline_utc_ns']
    remaining = (deadline - time.time_ns()) / 1e9
    if remaining <= 0: raise TimeoutError('no fixed-replay budget remains under600s total cap')
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('600s total scientific cap during fixed replay')))
    signal.setitimer(signal.ITIMER_REAL, remaining)
    execution = c.r.read(c.HERE / 'execution.json')
    rows = sorted(execution['rows'], key=lambda row:(row['case'], row['site_index'], row['variant'], row['intervention'], row['arm']))
    flat, gates, controls = [], [], {}
    for row in rows:
        record = {key:row[key] for key in ('case', 'site_index', 'variant', 'intervention', 'arm', 'status')}
        if row['status'] != 'complete':
            flat.append(dict(record, error=row.get('error'))); continue
        d = c.control.context(row['case'])
        scan, node, entries, truth = c.construct(d, row['site_index'], row['variant'], row['intervention'])
        gate = gate_oracle.replay_gates(d, scan, node, entries, row)
        gates.append(dict(record, **gate))
        target = row['fixed_objective_diagnostics']['truth_at_final_reference']
        final = row['fixed_objective_diagnostics']['endpoint_at_final_reference']
        vector, original = np.asarray(row['error_vector_east_north_km']), np.asarray(row['paired_control_error_vector_km'])
        record.update(qualified=row['qualification']['passed'], error_km=row['synthetic_position_error_km'],
            control_error_km=row['paired_control_error_km'], error_change_km=row['synthetic_position_error_km'] - row['paired_control_error_km'],
            error_east_km=float(vector[0]), error_north_km=float(vector[1]),
            control_error_east_km=float(original[0]), control_error_north_km=float(original[1]),
            endpoint_change_east_km=float(vector[0] - original[0]), endpoint_change_north_km=float(vector[1] - original[1]),
            error_direction_cosine=float(vector @ original / (np.linalg.norm(vector) * np.linalg.norm(original))) if np.linalg.norm(vector) * np.linalg.norm(original) > 0 else None,
            phase_change_s=row['final_phase_change_s'], Gamma_change=final['final_log_precision_change'],
            forward_closure_hz=row['fixed_objective_diagnostics']['known_forward_closure']['maximum_known_forward_mean_identity_error_hz'],
            endpoint_minus_truth_objective=final['total_negative_twice_elbo'] - target['total_negative_twice_elbo'],
            parent_weighted_residual_change=final['parent_weighted_residual_energy'] - target['parent_weighted_residual_energy'],
            parent_mean_prior_change=final['parent_latent_mean_prior_energy'] - target['parent_latent_mean_prior_energy'],
            parent_logvolume_change=final['logvolume'] - target['logvolume'],
            parent_noise_Gamma_change=final['noise_gamma_cost'] - target['noise_gamma_cost'],
            parent_prior_Gamma_change=final['prior_gamma_cost'] - target['prior_gamma_cost'],
            predictive_change=final['predictive_objective'] - target['predictive_objective'],
            truth_gradient_norm_per_km=float(np.linalg.norm(target['objective_gradient_per_km'])),
            endpoint_gradient_norm_per_km=float(np.linalg.norm(final['objective_gradient_per_km'])))
        flat.append(record)
        key = (row['case'], row['site_index'], row['variant'], row['arm'])
        controls[key] = dict(case=row['case'], site_index=row['site_index'], variant=row['variant'], arm=row['arm'],
            status='complete', qualified=True, intervention='original_all_deviations', error_km=row['paired_control_error_km'],
            error_east_km=float(original[0]), error_north_km=float(original[1]))
    signal.setitimer(signal.ITIMER_REAL, 0)
    c.r.write_new(c.HERE / 'gate_replay.json', dict(all_saved_decisions_replay=True, rows=gates, position_fits=0,
        seconds=time.monotonic() - began, scientific_seal_sha256=c.r.sha(c.HERE / 'scientific_seal.json'),
        within_original_deadline=time.time_ns() <= deadline, real_GPS_used=False))
    with (c.HERE / 'paired_results.csv').open('x', newline='') as stream:
        fields = list(dict.fromkeys(key for row in flat for key in row))
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(flat)
    summaries = []
    for intervention in ('original_all_deviations',) + c.INTERVENTIONS:
        for arm in c.control.ARMS:
            chosen = [row for row in list(controls.values()) + flat if row['intervention'] == intervention and row['arm'] == arm and row['status'] == 'complete']
            if not chosen: continue
            errors = np.array([row['error_km'] for row in chosen])
            summaries.append(dict(intervention=intervention, arm=arm, completed=len(chosen),
                qualified=sum(row['qualified'] for row in chosen), mean_error_km=float(errors.mean()),
                median_error_km=float(np.median(errors)), minimum_error_km=float(errors.min()), maximum_error_km=float(errors.max()),
                mean_error_vector_east_north_km=[float(np.mean([row[key] for row in chosen])) for key in ('error_east_km', 'error_north_km')],
                improve_control=sum(row.get('error_change_km', 0.) < 0 for row in chosen),
                worsen_control=sum(row.get('error_change_km', 0.) > 0 for row in chosen)))
    failure_counts = {method:{role:dict(Counter(key for gate in gates if gate['intervention'] == method for track in gate[role]
        for key in track['failed_predicates'])) for role in ('curved', 'predictive')} for method in c.INTERVENTIONS}
    summary = dict(new_attempted_fits=execution['attempted_fits'], new_completed_fits=execution['completed'], failures=execution['failures'],
        summaries=summaries, original_control_fit_count=16, original_control_fits_reused_not_repeated=True,
        gate_failure_counts=failure_counts, all_errors_include_unqualified_completed_fits=True,
        phase_failure_count=sum(not row.get('qualification', {}).get('phase_converged', False) for row in rows if row['status'] == 'complete'),
        Gamma_failure_count=sum(not row.get('qualification', {}).get('Gamma_converged', False) for row in rows if row['status'] == 'complete'),
        original_global_wall_seconds_at_execution_end=execution['wall_seconds_since_first_preparation'],
        wall_seconds_through_fixed_replay=(time.time_ns() - c.r.read(c.HERE / 'scientific_start.json')['started_utc_ns']) / 1e9,
        maximum_forward_closure_hz=max(row.get('forward_closure_hz', 0.) for row in flat),
        maximum_endpoint_gradient_norm_per_km=max(row.get('endpoint_gradient_norm_per_km', 0.) for row in flat),
        source_sha256=c.r.sha(__file__), real_GPS_used=False, association_selection_tested=False)
    c.r.write_new(c.HERE / 'summary.json', summary)
    labels = [(case, site, variant) for case in c.CASES for site in range(2) for variant in c.VARIANTS]
    colors = {'original_all_deviations':'#64748b', 'no_orbital_deviations':'#2563eb', 'no_receiver_deviations':'#dc2626'}
    names = {'original_all_deviations':'original all deviations', 'no_orbital_deviations':'no phase/shape deviations', 'no_receiver_deviations':'no hardware/smooth deviations'}
    all_rows = list(controls.values()) + [row for row in flat if row['status'] == 'complete']
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4), constrained_layout=True)
    for ax, arm in zip(axes, c.control.ARMS):
        for offset, method in zip((-.25, 0., .25), colors):
            values = [next((row for row in all_rows if (row['case'], row['site_index'], row['variant']) == key and row['arm'] == arm and row['intervention'] == method), None) for key in labels]
            bars = ax.bar(np.arange(8) + offset, [row['error_km'] if row else np.nan for row in values], width=.22, color=colors[method], label=names[method])
            for bar, row in zip(bars, values):
                if row and not row['qualified']: bar.set_hatch('///')
        ax.set_xticks(np.arange(8), [f'{case[-4:]} S{site} D{variant[-1]}' for case, site, variant in labels], rotation=50)
        ax.set_ylabel('Artificial position error (km)'); ax.set_title(arm); ax.grid(axis='y', alpha=.2); ax.legend(fontsize=8)
    fig.suptitle('Same eight noise realizations; generating components changed, inference unchanged')
    fig.savefig(c.HERE / 'paired_component_errors.png', dpi=150); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), constrained_layout=True)
    markers = {'original_all_deviations':'o', 'no_orbital_deviations':'^', 'no_receiver_deviations':'x'}
    for ax, arm in zip(axes, c.control.ARMS):
        for method in colors:
            chosen = [row for row in all_rows if row['arm'] == arm and row['intervention'] == method]
            ax.scatter([row['error_east_km'] for row in chosen], [row['error_north_km'] for row in chosen],
                marker=markers[method], color=colors[method], label=names[method], s=34)
            if method != 'original_all_deviations':
                for row in chosen:
                    ax.plot([row['control_error_east_km'], row['error_east_km']],
                        [row['control_error_north_km'], row['error_north_km']], color=colors[method], alpha=.25, lw=.7)
        ax.axhline(0, color='black', lw=.6); ax.axvline(0, color='black', lw=.6)
        ax.set(xlabel='East error (km)', ylabel='North error (km)', title=arm); ax.axis('equal'); ax.grid(alpha=.2); ax.legend(fontsize=8)
    fig.suptitle('Error directions at fixed artificial truth; lines join paired realizations')
    fig.savefig(c.HERE / 'paired_error_directions.png', dpi=150); plt.close(fig)
    files = [c.HERE / name for name in ('summarize.py', 'summary.json', 'paired_results.csv', 'gate_replay.json',
        'paired_component_errors.png', 'paired_error_directions.png')]
    c.r.write_new(c.HERE / 'report_data_seal.json', dict(files={str(path):c.r.sha(path) for path in files},
        scientific_seal_sha256=c.r.sha(c.HERE / 'scientific_seal.json'), real_GPS_used=False))
    print(summary, flush=True)


if __name__ == '__main__': main()
