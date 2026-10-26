"""Saved-only reporting of the completed four-context diagnostic."""
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
CONTEXTS = ('full_parent', 'old_union_cavity')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def write_csv(path, rows):
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main():
    if OUT.exists():
        raise FileExistsError('Saved reporting output already exists')
    rf = read(HERE / 'RF_seal.json')
    for path, expected in rf['files'].items():
        if sha(Path(path)) != expected:
            raise ValueError('RF mismatch: ' + path)
    OUT.mkdir()
    inventory = read(HERE / 'inventory.json')
    owner_rows = []
    for row in inventory['all_complete_owner_rows']:
        evidence = row['archived_own_label_evidence']
        owner_rows.append(dict(component=row['component'], receiver=row['receiver'], channel=row['channel'],
            rf_hz=row['rf_hz'], bank=row['bank'], points=row['points'], start_s=row['start_s'], end_s=row['end_s'],
            quality_status=row['quality_status'],
            own_archived_labels=';'.join(str(x) for x in sorted({q['norad'] for q in evidence})),
            own_archived_evidence_records=len(evidence),
            explicit_own_68904_records=len(row['relevant_68904_evidence']),
            complete_alternative_feasibility_list_available=False,
            potential_separate_owner=row['eligible_potential_separate_owner'],
            c0_accepted_overlap=len(row['accepted_overlap']['c0']),
            fitted_c_accepted_overlap=len(row['accepted_overlap']['fitted_c']),
            exclusion_reasons=';'.join(row['exclusion_reasons']),
            native_ID_list_sha256=hashlib.sha256(json.dumps(row['observation_ids'], separators=(',', ':')).encode()).hexdigest()))
    write_csv(OUT / 'owner_inventory.csv', owner_rows)
    dump(OUT / 'inventory_summary.json', {key: value for key, value in inventory.items() if key != 'all_complete_owner_rows'})
    results, rows, parameters, fixed = {}, [], [], []
    for arm in ARMS:
        comparison = read(HERE / (arm + '_comparison.json'))
        for context in CONTEXTS:
            path = HERE / (arm + '_' + context + '_result.json')
            if not path.exists():
                rows.append(dict(arm=arm, context=context, status='unavailable'))
                continue
            result = read(path)
            diagnostic = result['source_diagnostic']
            results[(arm, context)] = diagnostic
            row = dict(arm=arm, context=context, status=result['status'],
                phase_s=diagnostic['phase_s'], causal_z=diagnostic['causal_z'], whole_graph_alias=diagnostic['alias'],
                old_parent_gates_pass=result['old_parent_gates_pass'],
                original_growth_supported=diagnostic['original_growth_supported'],
                identity_independently_validated=False)
            for gate_name in ('conservative_gate', 'fullmode_gate'):
                gate = diagnostic[gate_name]
                row.update({gate_name + '_' + key: gate[key] for key in
                            ('compatible', 'rms_hz', 'bias_hz', 'minimum_elevation_deg')})
                row.update({gate_name + '_' + key: value for key, value in gate['noise'].items()})
            for index, value in enumerate(diagnostic['mode_coefficient'], 1):
                row['mode_' + str(index) + '_prior_units'] = value
            rows.append(row)
            arrays = np.load(HERE / (arm + '_' + context + '.npz'))
            for index, time_s in enumerate(arrays['times']):
                parameters.append(dict(arm=arm, context=context, native_id=str(arrays['native_ids'][index]),
                    time_s=time_s, graph_value_hz=arrays['values'][index],
                    old_only_radio_mean_hz=arrays['values'][index] - arrays['raw'][index],
                    conservative_profile_residual_hz=diagnostic['conservative_gate']['profile_residual_hz'][index],
                    target_mode_profile_residual_hz=diagnostic['fullmode_gate']['profile_residual_hz'][index],
                    base_predictive_SD_hz=float(np.sqrt(arrays['covariance'][index, index]))))
            same = comparison['fixed_old_cavity_MAP'][context]
            fixed.append(dict(arm=arm, context=context, phase_s=same['phase_s'], whole_alias=same['whole_alias'],
                mode_1=same['mode_coefficient'][0], mode_2=same['mode_coefficient'][1], mode_3=same['mode_coefficient'][2],
                conservative_RMS_hz=same['conservative_gate']['rms_hz'],
                target_mode_RMS_hz=same['fullmode_gate']['rms_hz'],
                conservative_ACF=same['conservative_gate']['noise']['lag1_acf'],
                target_mode_ACF=same['fullmode_gate']['noise']['lag1_acf']))
    write_csv(OUT / 'diagnostics.csv', rows)
    write_csv(OUT / 'per_point.csv', parameters)
    write_csv(OUT / 'fixed_old_phase.csv', fixed)
    comparisons = {arm: read(HERE / (arm + '_comparison.json')) for arm in ARMS}
    dump(OUT / 'summary.json', dict(inventory=dict(complete_original_owners=164,
        potential_separate_owners=inventory['potential_separate_owner_count']), diagnostics=rows,
        comparisons=comparisons, execution=read(HERE / 'execution.json'),
        no_independent_prediction_performed=True, no_identity_or_position_gain_claim=True))

    colors = {'full_parent': '#0072B2', 'old_union_cavity': '#D55E00'}
    names = {'full_parent': 'Full parent', 'old_union_cavity': 'Old 480-point cavity'}
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for i, arm in enumerate(ARMS):
        for context in CONTEXTS:
            diagnostic = results.get((arm, context))
            if diagnostic is None:
                continue
            arrays = np.load(HERE / (arm + '_' + context + '.npz'))
            times = arrays['times']
            axes[i, 0].plot(times, diagnostic['conservative_gate']['profile_residual_hz'], 'o-', ms=3,
                            color=colors[context], label=names[context] + ' nominal')
            axes[i, 0].plot(times, diagnostic['fullmode_gate']['profile_residual_hz'], '--',
                            color=colors[context], label=names[context] + ' + D-fitted modes')
            axes[i, 1].plot(times, arrays['values'] - arrays['raw'], color=colors[context], label=names[context])
        arm_name = 'c = 0' if arm == 'c0' else 'Fitted c'
        axes[i, 0].set_title(arm_name + ': all29 points; no source trimming')
        axes[i, 0].set_ylabel('Profile residual (Hz)')
        axes[i, 0].axhline(0, color='.5', lw=.8)
        axes[i, 1].set_title(arm_name + ': old-only radio mean, before D')
        axes[i, 1].set_ylabel('Radio mean (Hz), inherited graph gauge')
        for ax in axes[i]:
            ax.set_xlabel('Scan time (s)')
            ax.legend(fontsize=8)
            ax.grid(alpha=.2)
    fig.suptitle('The full parent does not remove the target correction\nDashed curves use D-fitted physical modes, not independently calibrated orbit corrections', fontsize=13)
    fig.savefig(OUT / 'conditioning_residuals.png', dpi=170)
    fig.savefig(OUT / 'conditioning_residuals.pdf')
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.7), constrained_layout=True)
    for index, arm in enumerate(ARMS):
        ax = axes[index]
        for offset, context in enumerate(CONTEXTS):
            diagnostic = results.get((arm, context))
            if diagnostic is not None:
                ax.bar(np.arange(3) + (offset - .5) * .33, diagnostic['mode_coefficient'],
                       width=.33, color=colors[context], label=names[context])
        ax.axhline(0, color='.5', lw=.8)
        ax.set_xticks(np.arange(3), ['Physical mode1', 'Physical mode2', 'Physical mode3'])
        ax.set_ylabel('D-fitted coefficient (unit prior coordinates)')
        ax.set_title('c = 0' if arm == 'c0' else 'Fitted c')
        ax.legend(fontsize=9)
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('Restoring incumbent information increases the fitted physical pull\nThese modes include level/phase-like components; no separate owner validates them', fontsize=13)
    fig.savefig(OUT / 'physical_pull.png', dpi=170)
    fig.savefig(OUT / 'physical_pull.pdf')
    plt.close(fig)
    dump(OUT / 'seal.json', dict(RF_seal_sha256=sha(HERE / 'RF_seal.json'),
        source_sha256=sha(Path(__file__)), saved_arrays_only=True,
        files={str(path.relative_to(HERE)): sha(path) for path in sorted(OUT.iterdir()) if path.is_file()}))
    print('REPORT_READY', len(rows), 'diagnostics;', len(owner_rows), 'owner rows')


if __name__ == '__main__':
    main()
