"""Saved-array reporting only: no contexts, propagation, scoring or fitting."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / 'report'
ARMS = ('c0', 'fitted_c')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=True) + '\n')


def csv_file(path, rows):
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def scalar_gate(gate, prefix):
    result = {prefix + key: gate.get(key) for key in
              ('compatible', 'rms_hz', 'bias_hz', 'residual_alias',
               'raw_RMS_hz', 'minimum_elevation_deg')}
    result.update({prefix + key: val for key, val in gate.get('primitive', {}).items()})
    result.update({prefix + key: val for key, val in gate.get('noise', {}).items()})
    return result


def main():
    if OUT.exists():
        raise FileExistsError('Report outputs are immutable; use a new version for a correction')
    rf = read(HERE / 'RF_seal.json')
    for filename, expected in rf['files'].items():
        if sha(Path(filename)) != expected:
            raise ValueError('RF seal mismatch: ' + filename)
    OUT.mkdir()
    metadata = read(HERE / 'metadata.json')
    execution = read(HERE / 'execution.json')
    prior_inventory = read(Path('/srv/bulk/leo/research/ds24-ambiguity-position-r01/inventory/inventory.json'))
    prior_rows = {(q['case'], q['component']): q for q in prior_inventory['sources']}
    witnesses = []
    for case, availability in metadata['witness_availability'].items():
        selected = availability['selected']
        for owner in availability['all_other_owner_metadata']:
            old_owner = prior_rows[(case, owner['component'])]
            witnesses.append(dict(case=case, component=owner['component'],
                selected_by_frozen_metadata=bool(selected and selected['component'] == owner['component']),
                eligible_unused_complete_owner=owner['eligible'],
                exclusion_reasons=';'.join(owner['exclusion_reasons']),
                receiver=owner['receiver'], channel=owner['channel'], rf_hz=owner['rf_hz'],
                points=owner['points'], start_s=owner['start_s'], end_s=owner['end_s'],
                time_overlap_s=owner['time_overlap_s'], different_receiver=owner['different_receiver'],
                identical_RF=owner['identical_RF'], archived_nominee=old_owner.get('candidate_norad'),
                archived_nominee_compatible=old_owner.get('compatible'),
                same_family_validated=False, scored_in_this_branch=False))
    arms, candidates, historical, contexts = [], [], [], {}
    for target in metadata['targets']:
        case = target['case']
        directory = HERE / case
        trace = read(directory / 'original_trace.json')
        old = trace['canonical']
        for arm in ARMS:
            original = trace['original_fixed_fit_metrics'][arm][0]
            original_conditional = original.get('conditional_residual_gate', {})
            original_noise = original_conditional.get('diagnostics', {})
            historical.append(dict(case=case, arm=arm, component=target['component'],
                points=target['points'], original_nominee=target['candidate_norad'],
                canonical_compatible=old.get('compatible'),
                canonical_RMS_hz=old.get('rms_hz'), canonical_bias_hz=old.get('bias_hz'),
                original_fit_conditional_RMS_hz=original_conditional.get('rms_hz'),
                original_fit_compatible=original.get('compatible'),
                original_profile_compatible=original.get('original_profile_compatible'),
                original_conditional_noise_pass=original_noise.get('noise_screen_pass'),
                original_conditional_lag1_acf=original_noise.get('lag1_acf'),
                original_conditional_maximum_step_z=original_noise.get('maximum_step_z'),
                initial_failed=trace['initial_failed'],
                ALGO02_exclusion_epochs=';'.join(str(q['epoch']) for q in trace['histories']['ALGO02_curved_gate_history']),
                graph_to_native_alias_integers=str(trace['graph_to_native_alias_integers']),
                historical_epoch_primitive_details_unavailable=trace['original_gate_epoch_scalar_details_unavailable']))
            result_path = directory / (arm + '_result.json')
            failure_path = directory / (arm + '_failure.json')
            result = read(result_path) if result_path.exists() else {}
            failure = read(failure_path) if failure_path.exists() else {}
            checkpoint = directory / (arm + '_adequacy_checkpoint.json')
            diagnostic = result.get('source_diagnostic')
            if diagnostic is None and checkpoint.exists():
                diagnostic = read(checkpoint)['source_diagnostic']
            order = result.get('evidence_order_certificate', {})
            screen = read(directory / 'c0_screen.json')
            null_path = directory / (arm + '_null.json')
            null = read(null_path) if null_path.exists() else {}
            row = dict(case=case, arm=arm, component=target['component'],
                points=target['points'], status=result.get('status', failure.get('status', 'unavailable')),
                error=failure.get('error'), original_nominee=target['candidate_norad'],
                raw_best_physical=result.get('raw_physical_winner'),
                ordering_proved=order.get('proved', False),
                ordering_winner_kind=order.get('winner_kind'),
                ordering_winner_norad=order.get('winner_norad'),
                minimum_log_evidence_margin=order.get('minimum_log_evidence_margin'),
                original_remaining_residual_gates_pass=result.get('original_remaining_residual_gates_pass'),
                null_objective=null.get('objective'),
                identity_qualified=False, position_admission=False)
            if diagnostic:
                row.update(raw_best_physical=diagnostic['norad'], phase_s=diagnostic['phase_s'],
                    causal_z=diagnostic['causal_z'], whole_graph_alias=diagnostic['alias'],
                    original_growth_supported=diagnostic['original_growth_supported'],
                    requires_shared_family_restoration=diagnostic['requires_shared_family_restoration'],
                    global_MAP_certified=diagnostic['global_MAP_certified'])
                for key in ('conservative_gate', 'fullmode_gate'):
                    row.update(scalar_gate(diagnostic[key], key + '_'))
            contexts[(case, arm)] = (result, diagnostic, row)
            objective_values = []
            for rank, (index, norad) in enumerate(zip(screen['candidate_indices'], screen['candidate_norads'], strict=True), 1):
                final = next((q for q in result.get('candidates', []) if q['norad'] == norad), None)
                path = directory / (arm + '_' + str(norad) + '_checkpoint.json')
                q = final if final is not None else (read(path) if path.exists() else {})
                item = dict(case=case, arm=arm, screen_rank=rank, candidate_index=index, norad=norad,
                    terminal_arm_available=bool(result), status=q.get('status', 'unreached'),
                    error=q.get('error'), objective=q.get('objective'), seconds=q.get('seconds'),
                    primary_absolute_score_qualified=q.get('numerically_qualified', False),
                    absolute_score_qualified=bool(final is not None and q.get('numerically_qualified', False)),
                    visibility_certified=q.get('certified_visibility', False),
                    lower_log_evidence=q.get('full_support_lower_log_integral'),
                    upper_log_evidence=q.get('full_support_upper_log_integral'),
                    primary_reference_error=q.get('primary_reference_error'))
                if item['objective'] is not None:
                    item['physical_minus_null_objective'] = item['objective'] - null['objective']
                    objective_values.append(item['objective'])
                candidates.append(item)
            row['primary_candidate_checkpoints'] = sum(q['case'] == case and q['arm'] == arm and q['status'] != 'unreached' for q in candidates)
            if objective_values:
                row['raw_best_physical_minus_null_objective'] = min(objective_values) - null['objective']
            arms.append(row)
    if len(arms) != 8 or len(candidates) != 64:
        raise ValueError('Frozen denominator changed')
    csv_file(OUT / 'owner_arms.csv', arms)
    csv_file(OUT / 'candidate_slots.csv', candidates)
    csv_file(OUT / 'original_gate_history.csv', historical)
    csv_file(OUT / 'metadata_witnesses.csv', witnesses)
    summary = dict(owner_arm_slots=8, physical_candidate_slots=64,
        complete_owner_arms=sum(q['status'] == 'complete' for q in arms),
        candidate_checkpoints=sum(q['status'] != 'unreached' for q in candidates),
        candidate_absolute_score_qualified=sum(q['absolute_score_qualified'] for q in candidates),
        finite_pool_order_certificates=sum(q['ordering_proved'] for q in arms),
        conservative_primitive_gate_passes=sum(bool(q.get('conservative_gate_compatible')) for q in arms),
        fullmode_primitive_gate_passes=sum(bool(q.get('fullmode_gate_compatible')) for q in arms),
        source_adequacy_diagnostics=sum(key in q for q in arms for key in ['phase_s']),
        identity_qualified=0, position_fits=0, operational_admissions=0,
        execution=execution, owner_arms=arms, historical=historical,
        conditional_evidence_not_identity_probability=True,
        finite_order_not_absolute_precision=True)
    save_json(OUT / 'summary.json', summary)

    colors = {'c0': '#0072B2', 'fitted_c': '#D55E00'}
    fig, axes = plt.subplots(4, 2, figsize=(13, 12), constrained_layout=True)
    for i, target in enumerate(metadata['targets']):
        case = target['case']
        data = np.load(HERE / case / 'c0_original.npz')
        times, values = data['times'], data['values']
        center = float(np.median(values))
        left, right = axes[i]
        left.plot(times, (values - center) / 1000, 'o', ms=3, color='.25', label='Complete graph owner')
        available = False
        for arm in ARMS:
            result, diagnostic, row = contexts[(case, arm)]
            if diagnostic is None:
                continue
            available = True
            conservative = np.asarray(diagnostic['conservative_raw_hz'])
            fullmode = np.asarray(diagnostic['fullmode_raw_hz'])
            label = ('c = 0' if arm == 'c0' else 'Fitted c') + f", label {diagnostic['norad']}"
            left.plot(times, (values - conservative - center) / 1000, color=colors[arm], lw=1.5, label=label)
            left.plot(times, (values - fullmode - center) / 1000, '--', color=colors[arm], lw=1)
            right.plot(times, diagnostic['conservative_gate']['profile_residual_hz'], 'o-', ms=2.5,
                       color=colors[arm], lw=1, label=('c = 0' if arm == 'c0' else 'Fitted c') + ' conservative')
            right.plot(times, diagnostic['fullmode_gate']['profile_residual_hz'], '--', color=colors[arm], lw=1)
        if not available:
            right.text(.5, .5, 'MAP / adequacy unavailable\nFrozen slot deadline retained', ha='center', va='center', transform=right.transAxes)
        left.set_title(f"{case}: RX{target['receiver']} CH{target['channel']}, {target['points']} complete points", fontsize=11)
        right.set_title('Residual structure after the original constant profile', fontsize=10)
        left.set_ylabel('Graph CFO minus median (kHz)')
        right.set_ylabel('Profile residual (Hz)')
        right.axhline(0, color='.5', lw=.6)
        for ax in (left, right):
            ax.set_xlabel('Scan time (s)')
            ax.grid(alpha=.2)
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(fontsize=7, loc='best')
    fig.suptitle('A preferred physical label still has to explain a complete source', fontsize=15)
    fig.savefig(OUT / 'source_adequacy.png', dpi=170)
    fig.savefig(OUT / 'source_adequacy.pdf')
    plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(11, 11), constrained_layout=True)
    for ax, target in zip(axes, metadata['targets'], strict=True):
        case = target['case']
        chosen = [q for q in candidates if q['case'] == case]
        names = [str(q['norad']) for q in chosen if q['arm'] == 'c0']
        for j, arm in enumerate(ARMS):
            rows = [q for q in chosen if q['arm'] == arm]
            x = np.arange(8) + (j - .5) * .32
            good = [i for i, q in enumerate(rows) if q.get('physical_minus_null_objective') is not None]
            ax.scatter(x[good], [rows[i]['physical_minus_null_objective'] for i in good],
                       color=colors[arm], marker='o' if j == 0 else 'x', label='c = 0' if j == 0 else 'Fitted c')
            for i, q in enumerate(rows):
                if q.get('physical_minus_null_objective') is None:
                    ax.text(x[i], .04, 'NA', fontsize=6, color=colors[arm], rotation=90,
                            ha='center', va='bottom', transform=ax.get_xaxis_transform())
        ax.axhline(0, color='.4', lw=1)
        ax.set_xticks(np.arange(8), names)
        ax.set_ylabel('Physical − unresolved\n−2 log evidence')
        ax.set_title(case + ': identical ordinary c0 shortlist in both arms', fontsize=11)
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    fig.suptitle('Conditional evidence ranking; lower favors the physical model', fontsize=14)
    fig.savefig(OUT / 'evidence_ranking.png', dpi=170)
    fig.savefig(OUT / 'evidence_ranking.pdf')
    plt.close(fig)
    save_json(OUT / 'seal.json', dict(RF_seal_sha256=sha(HERE / 'RF_seal.json'),
        report_source_sha256=sha(Path(__file__)),
        files={str(p.relative_to(HERE)): sha(p) for p in sorted(OUT.iterdir()) if p.is_file()},
        saved_arrays_only=True, no_propagation_or_new_scores=True))
    print(json.dumps({key: value for key, value in summary.items() if key not in ('owner_arms', 'historical', 'execution')}))


if __name__ == '__main__':
    main()
