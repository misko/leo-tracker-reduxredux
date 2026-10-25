"""Saved-only audit of discovery-conditioned predictions and all failures."""
import hashlib
import itertools
import json
from pathlib import Path
import time

import numpy as np

HERE = Path(__file__).resolve().parent
OWN = HERE.parent / 'prediction'
SCI = OWN / 'run02'
OLD = Path('/srv/bulk/leo/research/ds24-rx2-witness-r01/scientific')
read = lambda p: json.loads(Path(p).read_bytes())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    began = time.monotonic()
    output = HERE / 'prediction_terminal.json'
    if output.exists():
        raise FileExistsError('preserve terminal receipt')
    protocol, seal = read(SCI / 'protocol.json'), read(SCI / 'RF_seal.json')
    execution = read(SCI / 'execution.json')
    bindings = dict(protocol['source_input_hashes']); bindings.update(seal['files'])
    checks, summaries, posterior = [], [], []

    def check(name, passed, **details):
        checks.append(dict(name=name, passed=bool(passed), **details))

    check('repaired source/protocol/all RF inputs immutable',
          all(sha(path) == h for path, h in bindings.items()) and
          seal['protocol_sha256'] == sha(SCI / 'protocol.json') == read(HERE / 'preflight02.json')['protocol_sha256'])
    check('failed first execution preserved with no scientific outcome overwritten',
          all(sha(path) == h for path, h in read(OWN / 'RF_seal.json')['files'].items()) and
          read(OWN / 'execution.json')['scientific_seconds'] == execution['prior_harness_worker_seconds'])
    owners = [read(OLD / name / 'metadata.json') for name in ('owner1', 'owner0', 'owner2')]
    expected_ids = [oid for owner in owners for oid in owner['observation_ids']]
    expected_times = []
    tracks = {row['key']: row for row in read('/srv/bulk/leo/research/ds25-20261024/DS24-0013/tracks.json')}
    for owner in owners:
        expected_times.extend(tracks[owner['component']]['times'])
    expected_x = owners[0]['common_position_east_north_km']
    check('all complete124 native IDs retained and mutually disjoint', len(expected_ids) == len(set(expected_ids)) == 124)
    joint_final = joint_primary = absolute = 0
    for arm in ('c0', 'fitted_c'):
        directory = SCI / arm
        parent = read(directory / 'parent.json')
        check('same discovery cavity and original accepted IDs: ' + arm,
              parent['cavity'] == read(OLD / 'owner1' / (arm + '_cavity.json')) and
              not parent['original_accepted_IDs_changed'] and parent['same_CH5_discovery_cavity_every_model'] and
              parent['common_position_east_north_km'] == expected_x)
        background = np.load(directory / 'joint_background.npz')
        check('original source ordering and common RF position: ' + arm,
              list(background['native_ids']) == expected_ids and np.array_equal(background['times_s'], expected_times) and
              np.array_equal(background['common_position_east_north_km'], expected_x) and
              np.isfinite(background['raw_hz']).all() and np.linalg.eigvalsh(background['covariance_hz2']).min() > 0)
        with np.load(OLD / 'owner1' / (arm + '_conditional.npz')) as old:
            check('discovery arrays/calibration/Gamma unchanged: ' + arm,
                  np.array_equal(background['raw_hz'][:57], old['raw_hz']) and
                  np.allclose(background['covariance_hz2'][:57, :57], old['covariance_hz2'], atol=1e-7, rtol=1e-12) and
                  np.array_equal(background['parent_coefficients'], old['parent_coefficients']) and
                  np.array_equal(background['parent_noise'], old['parent_noise']))
        replay = read(directory / 'D_replay.json')
        discovery = read(directory / 'D_evidence.json')
        old_discovery = next(q for q in read(OLD / 'owner1' / (arm + '_result.json'))['candidates'] if q['norad'] == 57450)
        check('discovery evidence replays original source: ' + arm,
              replay['passed'] and replay['objective_error'] == 0 and discovery['objective'] == old_discovery['objective'])
        diagnostics = read(directory / 'Dposterior.json')
        d64 = diagnostics['GL64']
        with np.load(directory / 'Dposterior_GL64.npz') as data:
            weights, nodes = data['quadrature_posterior_mass'], data['quadrature_nodes']
            mass = weights.sum()
            mean = float(weights @ nodes / mass)
            sd = float(np.sqrt(weights @ (nodes - mean) ** 2 / mass))
            check('D-only posterior moment normalization and exported uncertainty: ' + arm,
                  abs(mass - 1) < 1e-12 and abs(mean - d64['phase_mean_s']) < 1e-11 and
                  abs(sd - d64['phase_SD_s']) < 1e-10 and len(data['prediction_mean_Hz']) == len(data['prediction_SD_Hz']) == 67 and
                  np.isfinite(data['prediction_mean_Hz']).all() and np.all(data['prediction_SD_Hz'] > 0) and
                  abs(sum(d64['alias_probabilities']) - 1) < 1e-12 and
                  np.linalg.eigvalsh(d64['latent_covariance']).min() >= -1e-10)
        check('diagnostic stability distinct from certified moments/identity: ' + arm,
              diagnostics['quadrature_stability_passed'] and all(diagnostics['checks'].values()) and
              not diagnostics['analytic_moment_error_certified'] and not diagnostics['calibrated_predictive_band'] and
              diagnostics['predictive_curve_W_response_free'] and not d64['W_responses_used'] and
              diagnostics['no_W_alias_selected_from_W_values'] and not diagnostics['discovery_evidence_absolute_precision'])
        posterior.append(dict(arm=arm, phase_mean_s=d64['phase_mean_s'], phase_SD_s=d64['phase_SD_s'],
            shape_mean=d64['shape_mean'], Dconstant_mean_Hz=d64['Dconstant_mean_Hz'], Dconstant_SD_Hz=d64['Dconstant_SD_Hz']))
        for witness, indices in (('CH3', np.r_[np.arange(57), np.arange(57, 81)]),
                                  ('CH4', np.r_[np.arange(57), np.arange(81, 124)])):
            models = np.load(directory / (witness + '_models.npz'))
            same_c, mixed_c = models['same_covariance_hz2'], models['mixed_covariance_hz2']
            poly = models['mixed_polynomial_columns_Hz']
            native_q = models['native_q']
            check('same D marginal/radio crosscov/nativeq and normalized81aliases: ' + arm + '/' + witness,
                  np.array_equal(models['raw_hz'], background['raw_hz'][indices]) and
                  np.array_equal(same_c, background['covariance_hz2'][np.ix_(indices, indices)]) and
                  np.array_equal(mixed_c, same_c + poly @ poly.T) and
                  np.array_equal(poly[:57], np.zeros((57, 5))) and np.array_equal(same_c[:57], mixed_c[:57]) and
                  np.array_equal(models['same_physical_q'], native_q) and
                  np.array_equal(models['mixed_physical_q'][:57], native_q[:57]) and np.all(models['mixed_physical_q'][57:] == 0) and
                  sorted(map(tuple, models['aliases'])) == list(itertools.product(range(-4, 5), repeat=2)))
            for kind in ('mixed', 'same'):
                support = read(directory / (witness + '_' + kind + '_support.json'))
                row = read(directory / (witness + '_' + kind + '_primary_checkpoint.json'))
                joint_primary += 1
                check('support law and completed primary checkpoint preserved: ' + arm + '/' + witness + '/' + kind,
                      support['certified'] and support['inner_visible_intervals'] == [[-15., 15.]] and
                      not support['root_brackets'] and not support['unresolved_intervals'] and
                      not row['visible_mass_renormalized'] and row['objective'] is not None)
                final_path = directory / (witness + '_' + kind + '_evidence.json')
                if final_path.exists():
                    joint_final += 1
                    final = read(final_path)
                    absolute += int(final['numerically_qualified'])
                    check('same frozen bounds/point score after independent reference: ' + arm + '/' + witness + '/' + kind,
                          all(final[key] == row[key] for key in ('objective', 'full_support_lower_log_integral', 'full_support_upper_log_integral')))
            result_path = directory / (witness + '_result.json')
            if result_path.exists():
                result = read(result_path)
                same, mixed = result['same_evidence'], result['mixed_evidence']
                lower = same['full_support_lower_log_integral'] - mixed['full_support_upper_log_integral']
                upper = same['full_support_upper_log_integral'] - mixed['full_support_lower_log_integral']
                order = result['comparison']
                check('complete comparison jointly conditioned; common D cancels: ' + arm + '/' + witness,
                      witness == 'CH3' and upper < 0 and order['proved'] and order['winner'] == 'unresolved_witness' and
                      np.array_equal(order['joint_log_evidence_odds_bounds'], [lower, upper]) and
                      order['discovery_denominator_cancels'] and not order['absolute_precision_implied'] and
                      not order['identity_acceptance'] and not result['alternative_identities_tested'] and
                      not result['operational_identity_assignment'] and result['position_fits'] == 0 and not result['GPS_used'])
                summaries.append(dict(arm=arm, witness=witness, status='complete', winner='unresolved_witness',
                    same_minus_mixed_log_evidence_bounds=[lower, upper]))
            else:
                failure = read(directory / (witness + '_failure.json'))
                check('budget-limited pair abstains; partial bounds not promoted: ' + arm + '/' + witness,
                      witness == 'CH4' and 'TimeoutError' in failure['error'] and 'sr.sm.reference' in failure['traceback'] and
                      not (directory / (witness + '_same_evidence.json')).exists())
                summaries.append(dict(arm=arm, witness=witness, status='budget_limited', winner=None,
                    partial_same_primary_checkpoint_retained=True, final_comparison_unavailable=True))
            models.close()
        background.close()
    check('all4 pair/8joint slots preserved; six final and two partial models',
          len(summaries) == 4 and joint_primary == 8 and joint_final == 6 and absolute == 0)
    check('original and repaired worker time exactly charged under600 cap',
          execution['scientific_seconds'] == execution['prior_harness_worker_seconds'] + execution['this_run_worker_seconds'] and
          execution['prior_harness_worker_seconds'] == 7.320185383781791 and execution['scientific_seconds'] <= 600 and
          execution['all_selected_terminal'] and execution['selected_arm_witness_contexts'] == 4 and
          execution['position_fits'] == execution['operational_identity_assignments'] == 0 and not execution['GPS_used'])
    check('all scientific bindings unchanged after audit', all(sha(path) == h for path, h in bindings.items()))
    elapsed = time.monotonic() - began
    prior = read(HERE / 'coupling_terminal.json')['cumulative_audit_seconds']
    receipt = dict(all_passed=all(c['passed'] for c in checks), checks=checks, rows=summaries, discovery_posterior=posterior,
        joint_model_primary_count=joint_primary, joint_model_final_count=joint_final, joint_model_absolute_precision_count=absolute,
        protocol_sha256=sha(SCI / 'protocol.json'), RF_seal_sha256=sha(SCI / 'RF_seal.json'), source_sha256=sha(__file__),
        seconds=elapsed, cumulative_audit_seconds=prior + elapsed, audit_cap_seconds=180,
        corpus_propagation_calls=0, position_fits=0, geographic_truth_read=False,
        conclusion='CH3 does not corroborate shared57450 withCH5; CH4 is budget-limited/unresolved. Neither proves CH5identity false. D-only posterior is assigned-model inference, not identity qualification; operational baseline unchanged.')
    receipt['all_passed'] &= receipt['cumulative_audit_seconds'] <= 180
    output.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(path=str(output), all_passed=receipt['all_passed'], checks=len(checks),
        cumulative_audit_seconds=receipt['cumulative_audit_seconds'], rows=summaries, failed=[c for c in checks if not c['passed']])))


if __name__ == '__main__':
    main()
