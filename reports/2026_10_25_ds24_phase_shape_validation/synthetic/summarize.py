"""Fixed saved-endpoint gate replay and predeclared factorial contrasts."""
from collections import Counter
import csv
import signal
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import factorial as f
import finish as gate_oracle


def contrasts(g):
    return dict(phase_removal_shape_on=g['01'] - g['11'], phase_removal_shape_off=g['00'] - g['10'],
        shape_removal_phase_on=g['10'] - g['11'], shape_removal_phase_off=g['00'] - g['01'],
        marginal_phase_removal=.5 * ((g['01'] - g['11']) + (g['00'] - g['10'])),
        marginal_shape_removal=.5 * ((g['10'] - g['11']) + (g['00'] - g['01'])),
        interaction=g['11'] - g['10'] - g['01'] + g['00'])


def save_csv(path, rows):
    with path.open('x', newline='') as stream:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def main():
    began = time.monotonic(); f.verify(require_approval=True)
    f.seal_verify(f.HERE / 'scientific_seal.json')
    start = f.r.read(f.HERE / 'scientific_start.json'); deadline = start['deadline_utc_ns']
    remaining = (deadline - time.time_ns()) / 1e9
    if remaining <= 0: raise TimeoutError('600s fixed-replay cap exhausted')
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('600s global cap during fixed replay')))
    signal.setitimer(signal.ITIMER_REAL, remaining)
    execution = f.r.read(f.HERE / 'execution.json')
    gates, fixed = [], []
    for row in execution['rows']:
        if row['status'] != 'complete': continue
        d = f.control.context(row['case'])
        scan, node, entries, _ = f.construct(d, row['site_index'], row['variant'], row['intervention'])
        gates.append(dict(case=row['case'], site_index=row['site_index'], variant=row['variant'],
            intervention=row['intervention'], arm=row['arm'], **gate_oracle.replay_gates(d, scan, node, entries, row)))
        truth = row['fixed_objective_diagnostics']['truth_at_final_reference']
        endpoint = row['fixed_objective_diagnostics']['endpoint_at_final_reference']
        record = {key:row[key] for key in ('case', 'site_index', 'variant', 'intervention', 'arm')}
        record.update(qualified=row['qualification']['passed'], endpoint_RMS_hz=endpoint['parent_conditional_RMS_hz'],
            endpoint_objective=endpoint['total_negative_twice_elbo'],
            endpoint_minus_truth_objective=endpoint['total_negative_twice_elbo'] - truth['total_negative_twice_elbo'],
            endpoint_gradient_norm_per_km=float(np.linalg.norm(endpoint['objective_gradient_per_km'])),
            truth_gradient_norm_per_km=float(np.linalg.norm(truth['objective_gradient_per_km'])),
            forward_closure_hz=row['fixed_objective_diagnostics']['known_forward_closure']['maximum_known_forward_mean_identity_error_hz'])
        for key in ('parent_weighted_residual_energy', 'parent_latent_mean_prior_energy', 'logvolume',
                'noise_gamma_cost', 'prior_gamma_cost', 'predictive_objective'):
            record['endpoint_minus_truth_' + key] = endpoint[key] - truth[key]
        fixed.append(record)
    signal.setitimer(signal.ITIMER_REAL, 0)
    f.r.write_new(f.HERE / 'gate_replay.json', dict(all_saved_decisions_replay=True, rows=gates, position_fits=0,
        seconds=time.monotonic() - began, within_original_deadline=time.time_ns() <= deadline,
        wall_seconds_since_first_preparation=(time.time_ns() - start['started_utc_ns']) / 1e9,
        scientific_seal_sha256=f.r.sha(f.HERE / 'scientific_seal.json'), real_GPS_used=False))
    flat, factorials, summaries = [], [], []
    for case in f.CASES:
        for site in range(2):
            for variant in f.VARIANTS:
                for arm in f.control.ARMS:
                    cells, cell_paths = {}, {}
                    for cell in ('11', '00', '01', '10'):
                        path = f.result_path(case, site, variant, arm, cell)
                        result = f.r.read(path); record = dict(case=case, site_index=site, variant=variant, arm=arm,
                            cell=cell, status=result['status'], source_path=str(path), source_sha256=f.r.sha(path))
                        cell_paths[cell] = record
                        if result['status'] == 'complete':
                            vector = np.asarray(result['endpoint_east_north_km']) - np.asarray(f.control.SITES[site])
                            error = float(np.linalg.norm(vector)); assert abs(error - result['synthetic_position_error_km']) < 1e-12
                            record.update(error_km=error, squared_error_km2=error ** 2,
                                error_east_km=float(vector[0]), error_north_km=float(vector[1]), qualified=result['qualification']['passed'])
                            cells[cell] = dict(vector=vector, error=error, squared_error=error ** 2)
                        else: record['failure'] = result.get('error')
                        flat.append(record)
                    out = dict(case=case, site_index=site, variant=variant, arm=arm,
                        all_cells_complete=len(cells) == 4, source_bindings=cell_paths)
                    if len(cells) == 4:
                        out['contrasts'] = {metric:contrasts({cell:g[metric] for cell, g in cells.items()})
                            for metric in ('vector', 'error', 'squared_error')}
                        out['all_cells_qualified'] = all(row['qualified'] for row in cell_paths.values())
                    else: out['undefined_reason'] = 'missing/failed cell retained, no imputation'
                    factorials.append(out)
    for cell in ('11', '00', '01', '10'):
        for arm in f.control.ARMS:
            selected = [row for row in flat if row['cell'] == cell and row['arm'] == arm]
            completed = [row for row in selected if row['status'] == 'complete']
            summary = dict(cell=cell, arm=arm, attempted=len(selected), completed=len(completed),
                qualified=sum(row['qualified'] for row in completed))
            if completed:
                errors = np.asarray([row['error_km'] for row in completed])
                summary.update(mean_error_km=float(errors.mean()), median_error_km=float(np.median(errors)),
                    maximum_error_km=float(errors.max()), minimum_error_km=float(errors.min()),
                    mean_squared_error_km2=float(np.mean(errors ** 2)),
                    mean_error_vector_km=[float(np.mean([row[key] for row in completed])) for key in ('error_east_km', 'error_north_km')])
                paired = [row for row in factorials if row['arm'] == arm and row['all_cells_complete']]
                changes = [row['source_bindings'][cell]['error_km'] - row['source_bindings']['11']['error_km'] for row in paired]
                summary.update(improve_full=sum(change < 0 for change in changes), worsen_full=sum(change > 0 for change in changes))
            summaries.append(summary)
    contrast_summary = []
    for arm in f.control.ARMS:
        selected = [row for row in factorials if row['arm'] == arm and row['all_cells_complete']]
        if not selected: continue
        for metric in ('vector', 'error', 'squared_error'):
            for name in selected[0]['contrasts'][metric]:
                values = np.asarray([row['contrasts'][metric][name] for row in selected])
                record = dict(arm=arm, metric=metric, contrast=name, count=len(values), mean=values.mean(axis=0))
                if metric != 'vector': record.update(minimum=float(values.min()), maximum=float(values.max()),
                    negative_count=int(sum(values < 0)), positive_count=int(sum(values > 0)))
                contrast_summary.append(record)
    failures = {name:{role:dict(Counter(key for gate in gates if gate['intervention'] == name
        for track in gate[role] for key in track['failed_predicates'])) for role in ('curved', 'predictive')}
        for name in f.INTERVENTIONS}
    new_complete = [row for row in execution['rows'] if row['status'] == 'complete']
    summary = dict(new_attempted_fits=execution['attempted_fits'], new_completed_fits=execution['completed'],
        runtime_failures=execution['failures'], new_qualified_fits=sum(row['qualification']['passed'] for row in new_complete),
        reused_fits=32, summaries=summaries, contrast_summaries=contrast_summary, gate_failure_counts=failures,
        phase_failure_count=sum(not row['qualification']['phase_converged'] for row in new_complete),
        Gamma_failure_count=sum(not row['qualification']['Gamma_converged'] for row in new_complete),
        region_failure_count=sum(np.max(abs(np.asarray(row['endpoint_east_north_km']))) > 12.500001 for row in new_complete),
        original_single_arm_invalid_count=sum(not row['qualification']['original_single_arm_valid'] for row in new_complete),
        complete_factorials=sum(row['all_cells_complete'] for row in factorials),
        all_completed_errors_included_regardless_of_qualification=True,
        maximum_forward_closure_hz=max((row['forward_closure_hz'] for row in fixed), default=None),
        maximum_endpoint_gradient_norm_per_km=max((row['endpoint_gradient_norm_per_km'] for row in fixed), default=None),
        fit_batch_wall_seconds=execution['fit_batch_wall_seconds'],
        wall_seconds_since_first_preparation_at_execution_end=execution['wall_seconds_since_first_preparation'],
        wall_seconds_through_fixed_replay=f.r.read(f.HERE / 'gate_replay.json')['wall_seconds_since_first_preparation'],
        real_GPS_used=False, association_selection_tested=False, full_generative_SBC=False)
    f.r.write_new(f.HERE / 'factorial_contrasts.json', dict(factorials=factorials, formulas=f.r.read(f.PROTOCOL)['contrasts']))
    f.r.write_new(f.HERE / 'summary.json', summary)
    save_csv(f.HERE / 'all_cell_results.csv', flat)
    save_csv(f.HERE / 'fixed_objective_diagnostics.csv', fixed)
    contrast_rows = []
    for row in factorials:
        base = {key:row[key] for key in ('case', 'site_index', 'variant', 'arm', 'all_cells_complete')}
        if not row['all_cells_complete']: contrast_rows.append(base); continue
        for metric, records in row['contrasts'].items():
            for name, value in records.items():
                record = dict(base, metric=metric, contrast=name)
                if metric == 'vector': record.update(east_km=float(value[0]), north_km=float(value[1]))
                else: record['value'] = float(value)
                contrast_rows.append(record)
    save_csv(f.HERE / 'factorial_contrasts.csv', contrast_rows)
    labels = [(case, site, variant) for case in f.CASES for site in range(2) for variant in f.VARIANTS]
    colors = {'11':'#64748b', '01':'#2563eb', '10':'#d97706', '00':'#059669'}
    names = {'11':'all deviations', '01':'phase at causal mean', '10':'zero shape', '00':'phase mean + zero shape'}
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), constrained_layout=True)
    for ax, arm in zip(axes, f.control.ARMS):
        for offset, cell in zip((-.3, -.1, .1, .3), colors):
            records = [next(row for row in flat if (row['case'], row['site_index'], row['variant']) == label
                and row['arm'] == arm and row['cell'] == cell) for label in labels]
            bars = ax.bar(np.arange(8) + offset, [row.get('error_km', np.nan) for row in records],
                width=.19, color=colors[cell], label=names[cell])
            for bar, row in zip(bars, records):
                if not row.get('qualified', False): bar.set_hatch('///')
        ax.set_xticks(np.arange(8), [f'{case[-4:]} S{site} D{variant[-1]}' for case, site, variant in labels], rotation=50)
        ax.set(ylabel='Artificial position error (km)', title=arm); ax.grid(axis='y', alpha=.2); ax.legend(fontsize=7)
    fig.suptitle('Complete generating phase x shape factorial; same eight noise realizations')
    fig.savefig(f.HERE / 'factorial_errors.png', dpi=150); plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), constrained_layout=True)
    chosen_names = ('marginal_phase_removal', 'marginal_shape_removal', 'interaction')
    for j, arm in enumerate(f.control.ARMS):
        chosen = [row for row in factorials if row['arm'] == arm and row['all_cells_complete']]
        for k, (metric, unit) in enumerate((('error', 'km'), ('squared_error', 'km²'))):
            ax = axes[k,j]
            for i, name in enumerate(chosen_names):
                values = [row['contrasts'][metric][name] for row in chosen]
                ax.scatter(i + np.linspace(-.08,.08,len(values)), values, s=24, color=('#2563eb','#d97706','#7c3aed')[i])
                if values: ax.plot([i-.15,i+.15], [np.mean(values)] * 2, color='black', lw=2)
            ax.axhline(0, color='black', lw=.7); ax.set_xticks(range(3), ['Phase removal','Shape removal','Interaction'])
            ax.set(ylabel=f'{metric.replace("_", " ")} contrast ({unit})', title=arm); ax.grid(axis='y', alpha=.2)
    fig.suptitle('Predeclared paired contrasts; points are realizations, black bars are means')
    fig.savefig(f.HERE / 'factorial_effects.png', dpi=150); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    for ax, arm in zip(axes, f.control.ARMS):
        for cell, marker in zip(colors, ('o','^','s','x')):
            chosen = [row for row in flat if row['cell'] == cell and row['arm'] == arm and row['status'] == 'complete']
            ax.scatter([row['error_east_km'] for row in chosen], [row['error_north_km'] for row in chosen],
                color=colors[cell], marker=marker, s=32, label=names[cell])
        ax.axhline(0, color='black', lw=.6); ax.axvline(0, color='black', lw=.6)
        ax.set(xlabel='East error (km)', ylabel='North error (km)', title=arm); ax.axis('equal'); ax.grid(alpha=.2); ax.legend(fontsize=7)
    fig.suptitle('Error vectors at the same artificial truths; inference unchanged')
    fig.savefig(f.HERE / 'factorial_directions.png', dpi=150); plt.close(fig)
    files = [f.HERE / name for name in ('summarize.py', 'summary.json', 'factorial_contrasts.json', 'factorial_contrasts.csv',
        'all_cell_results.csv', 'fixed_objective_diagnostics.csv', 'gate_replay.json', 'factorial_errors.png', 'factorial_effects.png', 'factorial_directions.png')]
    f.r.write_new(f.HERE / 'report_data_seal.json', dict(files={str(path):f.r.sha(path) for path in files},
        scientific_seal_sha256=f.r.sha(f.HERE / 'scientific_seal.json'), real_GPS_used=False))
    print('SUMMARY', summary, flush=True)


if __name__ == '__main__': main()
