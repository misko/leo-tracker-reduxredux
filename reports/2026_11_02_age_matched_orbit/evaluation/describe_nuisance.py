"""Postfit saved-coefficient description; no scientific model imports or refits."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parent
ARMS = ('c0', 'fitted_c')
GROUPS = ('RX1_low', 'RX1_high', 'RX2_low', 'RX2_high')
MODES = ('mean_motion', 'inclination', 'RAAN')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def describe(row, arm, positions, original_input):
    control = row['selected_A_control_replay'][arm]
    endpoint = row['raw_endpoints'][arm]
    a, b = control['nuisance'], endpoint['nuisance']
    assert a['status'] == b['status'] == 'available'
    assert a['layout'] == b['layout']
    target_a, target_b = a['target_orbit'], b['target_orbit']
    scale = np.asarray(target_a['current_declared_physical_SD'])
    assert np.array_equal(scale, target_b['current_declared_physical_SD'])
    for snapshot in (a, b):
        target = snapshot['target_orbit']
        assert np.allclose(np.asarray(target['transform_to_original']) @ target['fitted_standardized_coefficient'],
                           target['original_standardized_coefficient'], atol=1e-12)
        assert np.allclose(scale * target['original_standardized_coefficient'],
                           target['physical_parameter_revision'], atol=1e-12)
    ba, bb = np.asarray(a['state']['beta']), np.asarray(b['state']['beta'])
    pa, pb = np.asarray(a['state']['phases_for_labels_s']), np.asarray(b['state']['phases_for_labels_s'])
    norads = a['layout']['phase_norads']
    index = norads.index(row['target_family'])
    covariance = np.asarray(row['age_prior_receipt']['coefficient_covariance'])
    accepted = row['policies']['Age2']['accepted']
    control_position = row['immutable_comparators']['A'][arm].get('x')
    if control_position is None:
        assert row['immutable_comparators']['A'][arm]['source'] == 'exact_saved_ALGO07'
        control_position = original_input['baseline_arms'][arm]['endpoint_east_north_km']
    dx = 1000 * (np.asarray(endpoint['x']) - control_position)
    item = dict(case=row['case'], arm=arm, target_family=row['target_family'],
        pair_count=row['age_support']['pair_count'], Age2_accepted=accepted,
        A_error_m=float(positions[(row['case'], arm, 'A')]['error_m']),
        selected_Age2_error_m=float(positions[(row['case'], arm, 'Age2')]['error_m']),
        selected_Age2_minus_A_error_m=float(positions[(row['case'], arm, 'Age2')]['change_vs_A_m']),
        raw_age_minus_A_east_m=dx[0], raw_age_minus_A_north_m=dx[1], raw_endpoint_displacement_m=np.linalg.norm(dx),
        A_curved_RMS_Hz=control['rms_hz'], raw_age_curved_RMS_Hz=endpoint['rms_hz'],
        raw_age_minus_A_curved_RMS_Hz=endpoint['rms_hz']-control['rms_hz'],
        max_absolute_offset_change_Hz=max(abs(bb[:4]-ba[:4])),
        max_absolute_band_drift_change_Hz_per_s=max(abs(bb[4:8]-ba[4:8]))/150,
        A_c_Hz_per_GHz=ba[8] if len(ba)==9 else 0., raw_age_c_Hz_per_GHz=bb[8] if len(bb)==9 else 0.,
        target_A_phase_s=pa[index], target_raw_age_phase_s=pb[index], target_phase_change_s=pb[index]-pa[index],
        max_absolute_other_phase_change_s=max(abs(np.delete(pb-pa,index))),
        smooth_coefficient_change_norm_Hz=np.linalg.norm(np.asarray(b['state']['smooth'])-a['state']['smooth']))
    parameters = []
    def add(block, parameter, unit, av, bv, ascale='', bscale='', original_sd_change=''):
        parameters.append(dict(case=row['case'], arm=arm, Age2_accepted=accepted, block=block, parameter=parameter,
            unit=unit, A=av, raw_age=bv, raw_age_minus_A=bv-av, declared_scale_A=ascale,
            declared_scale_age=bscale, delta_in_original_declared_SD=original_sd_change))
    for k, group in enumerate(GROUPS):
        add('receiver_beta', group+'_offset', 'Hz', ba[k], bb[k])
        add('receiver_beta', group+'_drift', 'Hz/s', ba[4+k]/150, bb[4+k]/150)
    add('receiver_beta', 'c', 'Hz/GHz', item['A_c_Hz_per_GHz'], item['raw_age_c_Hz_per_GHz'])
    for k, norad in enumerate(norads):
        assert a['phase_sigma_s'][k] == b['phase_sigma_s'][k]
        add('family_phase', str(norad), 's', pa[k], pb[k], a['phase_sigma_s'][k], b['phase_sigma_s'][k],
            (pb[k]-pa[k])/a['phase_sigma_s'][k])
    for k, mode in enumerate(MODES):
        av, bv = target_a['physical_parameter_revision'][k], target_b['physical_parameter_revision'][k]
        add('target_physical_orbit', mode, target_a['physical_units'][k], av, bv,
            scale[k], scale[k]*np.sqrt(covariance[k,k]), (bv-av)/scale[k])
        for label, value in (('A_physical', av), ('raw_age_physical', bv), ('physical_delta', bv-av),
                             ('original_declared_SD', scale[k]), ('age_marginal_declared_SD', scale[k]*np.sqrt(covariance[k,k])),
                             ('A_original_standardized', target_a['original_standardized_coefficient'][k]),
                             ('raw_age_original_standardized', target_b['original_standardized_coefficient'][k])):
            item[mode+'_'+label] = value
    return item, parameters


def main():
    result_path, position_path = ROOT/'results.json', REPORT/'positions.csv'
    before = (sha(result_path), sha(position_path))
    packet = json.loads(result_path.read_text())
    roster = {r['case']:r for r in json.loads((ROOT/'rf_roster.json').read_text())['cases']}
    positions = {(r['case'],r['arm'],r['method']):r for r in csv.DictReader(position_path.open())}
    rows, parameters = [], []
    for row in packet['rows']:
        if set(row.get('raw_endpoints', {})) != set(ARMS):
            continue
        input_path = Path(roster[row['case']]['input_path'])
        assert sha(input_path) == row['input_sha256']
        original_input = json.loads(input_path.read_text())
        for arm in ARMS:
            item, detail = describe(row, arm, positions, original_input)
            rows.append(item)
            parameters.extend(detail)
    assert len(rows) == 60
    write_csv(ROOT/'nuisance_case_deltas.csv', rows)
    write_csv(ROOT/'nuisance_parameter_deltas.csv', parameters)
    adopted = sorted((r for r in rows if r['arm']=='fitted_c' and r['Age2_accepted']),
                     key=lambda r:r['selected_Age2_minus_A_error_m'])
    focus = [r['case'] for r in adopted[:3]+adopted[-3:]]
    for case in ('DS26-0309','DS26-0315','FRSH-0004'):
        assert case in focus
    plt.rcParams.update({'font.size': 9})
    fig, axes = plt.subplots(2, 3, figsize=(13.2, 7.2), constrained_layout=True)
    specifications = [('selected_Age2_minus_A_error_m','Position error change (m)'),
        ('raw_age_minus_A_curved_RMS_Hz','Curved residual RMS change (Hz)'),
        ('max_absolute_offset_change_Hz','Max absolute receiver offset change (Hz)'),
        ('max_absolute_band_drift_change_Hz_per_s','Max absolute receiver drift change (Hz/s)'),
        ('target_phase_change_s','Target satellite phase change (s)')]
    for ax, (key, label) in zip(axes.flat, specifications):
        for ai, arm in enumerate(ARMS):
            selected = [next(r for r in rows if r['case']==case and r['arm']==arm) for case in focus]
            ax.scatter([r[key] for r in selected], np.arange(len(focus))+(ai-.5)*.16,
                       label=arm, marker=('o','x')[ai], s=34)
        ax.axvline(0, color='0.6', lw=.8)
        ax.set(yticks=np.arange(len(focus)), yticklabels=focus, xlabel=label)
        ax.invert_yaxis()
        ax.grid(axis='x', alpha=.2)
    ax = axes.flat[-1]
    for k, mode in enumerate(MODES):
        selected = [next(r for r in rows if r['case']==case and r['arm']=='fitted_c') for case in focus]
        ax.scatter([r[mode+'_physical_delta']/r[mode+'_original_declared_SD'] for r in selected],
                   np.arange(len(focus))+(k-1)*.16, label=mode, marker=('o','x','+')[k])
    ax.axvline(0, color='0.6', lw=.8)
    ax.set(yticks=np.arange(len(focus)), yticklabels=focus,
           xlabel='Orbital revision change / original declared SD\n(fitted-c arm; physical units in CSV)')
    ax.invert_yaxis()
    ax.legend(fontsize=8)
    axes.flat[0].legend()
    fig.suptitle('Saved A → Age2 endpoint changes: postfit top three improvements and regressions\nAll six accepted by Age2; descriptive selection after position scoring')
    fig.savefig(ROOT/'nuisance_changes.png', dpi=180)
    plt.close(fig)
    lines = ['# Saved nuisance parameter changes', '',
        'These are postfit descriptions of the immutable selected-A control and the one fresh age-covariance endpoint. No models were reconstructed and no optimization was run. The panel selects the three largest fitted-c Age2 improvements and three largest regressions after position scoring. All 30 candidate pairs, including rejected raw endpoints, remain in the CSVs.', '',
        '| Case | Arm | Error Δ m | RMS Δ Hz | Max offset Δ Hz | Max drift Δ Hz/s | Target phase Δ s | Orbit Δ mean motion rev/day / inclination deg / RAAN deg |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for case in focus:
        for arm in ARMS:
            r = next(r for r in rows if r['case']==case and r['arm']==arm)
            orbit = ' / '.join(f"{r[m+'_physical_delta']:+.5g}" for m in MODES)
            lines.append(f"| {case} | {arm} | {r['selected_Age2_minus_A_error_m']:+.1f} | {r['raw_age_minus_A_curved_RMS_Hz']:+.5f} | {r['max_absolute_offset_change_Hz']:.2f} | {r['max_absolute_band_drift_change_Hz_per_s']:.4f} | {r['target_phase_change_s']:+.5f} | {orbit} |")
    lines += ['', '![Saved coefficient and residual changes](nuisance_changes.png)', '',
        'Receiver beta has four RX/band offsets in Hz. Its next four stored coordinates are 150 times the physical drift in Hz/s; the tables divide by 150. The optional ninth coordinate c is Hz/GHz about 11.5 GHz and is fixed to zero in the c0 arm. Beta amplitudes are coefficients, not independent measurements of receiver hardware error.', '',
        'Phase entries are absolute posterior phase in seconds, matched by saved NORAD. Their declared phase SDs are retained in the parameter CSV; the heavy-tailed hierarchy can alter conditional prior precision, so these SDs are coordinate scales rather than posterior uncertainty. Smooth-coefficient norm changes are in Hz times the unchanged receiver basis, not the RMS of a reconstructed receiver curve.', '',
        'The three target orbital coefficients represent mean-motion, inclination and RAAN revisions in rev/day, degrees and degrees. Raw transformed coefficients have different bases between A and age covariance: this report first maps age coefficients back with L @ z and multiplies by the original physical SD. Original and age marginal declared SDs (original SD × sqrt(diag(C))) are in both CSVs. The figure divides physical revisions by the original SD only for a common plotting scale; it is not a posterior z score. Non-target orbital coefficients may also adapt at a new endpoint; this panel isolates the changed target prior and receiver/phase response.', '',
        'Both the largest improvement (DS26-0309) and largest regression (DS26-0315), and the FRSH-0004 regression, use larger target-orbit corrections alongside receiver and phase changes. This shows a coupled response to the changed covariance. Saved endpoint coefficients cannot identify a unique physical cause or establish that an orbital or receiver estimate is correct. A better in-sample RMS is separately reported from position error and does not establish better localization. Ancillary phase-mixture families are separately scored; these snapshots are the conditional curved-model coefficient representation, not a joint posterior for all evidence.', '',
        '[Case/arm deltas](nuisance_case_deltas.csv) · [Physical parameter values, scales and deltas](nuisance_parameter_deltas.csv)', '',
        f'Input bindings: results `{before[0]}`; positions `{before[1]}`. All 60 saved endpoint/control pairs passed coefficient-coordinate mapping checks. Input bytes are unchanged after this description.', '']
    (ROOT/'NUISANCE_DIAGNOSTICS.md').write_text('\n'.join(lines))
    assert before == (sha(result_path), sha(position_path))
    print(json.dumps(dict(case_arm_rows=len(rows), parameter_rows=len(parameters), focus=focus,
                          results_sha256=before[0], positions_sha256=before[1], no_refits=True)))


if __name__ == '__main__':
    main()
