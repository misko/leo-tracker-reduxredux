"""Independent saved-input checks; no orbit propagation, fitting or geography."""
import hashlib
import csv
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'ds24-ambiguity-policy-r01'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(name, value):
    with (ROOT / 'audit' / name).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def bindings(values):
    failures = [path for path, expected in values.items() if sha(path) != expected]
    if failures:
        raise AssertionError('Changed bindings: ' + str(failures))
    return len(values)


def tests(path):
    began = time.monotonic()
    process = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q', '-p',
        'no:cacheprovider', str(path)], capture_output=True, text=True,
        timeout=40, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    if process.returncode:
        raise AssertionError(process.stdout + process.stderr)
    return dict(seconds=time.monotonic() - began, stdout=process.stdout,
        stderr=process.stderr, returncode=process.returncode)


def witness_preflight():
    began = time.monotonic()
    here = ROOT / 'witness'
    protocol = read(here / 'protocol.json')
    checked = bindings(protocol['bindings'])
    prior = OLD / 'qualification'
    seal = read(prior / 'RF_seal.json')
    for name in ['c0_screen.json'] + [arm + suffix for arm in ('c0', 'fitted_c')
            for suffix in ('_original.npz', '_conditional.npz')]:
        path = prior / 'DS24-0015' / name
        assert sha(path) == seal['files'][str(path)]
    inv = read(here / 'inventory.json')
    assert len(inv['all_complete_owner_rows']) == inv['complete_original_owners'] == 164
    assert inv['owners_with_persisted_68904_evidence'] == 1
    assert inv['potential_separate_owner_count'] == 0 and not inv['potential_separate_owners']
    assert all(not row['eligible_potential_separate_owner'] for row in inv['all_complete_owner_rows'])
    assert [row['component'] for row in inv['all_complete_owner_rows']
        if row['relevant_68904_evidence']] == [inv['discovery_component']]
    assert protocol['no_witness_prediction'] and not protocol['separate_witnesses']
    assert protocol['position_fits'] == protocol['new_catalogue_scores'] == 0
    d_ids = protocol['complete_D_IDs']
    assert len(d_ids) == len(set(d_ids)) == 29
    contexts = []
    x = None
    for arm in ('c0', 'fitted_c'):
        for label in ('full_parent', 'old_union_cavity'):
            a = np.load(here / (arm + '_' + label + '.npz'))
            previous = np.load(prior / 'DS24-0015' / (arm +
                ('_original.npz' if label == 'full_parent' else '_conditional.npz')))
            assert list(a['native_ids']) == d_ids
            assert a['covariance'].shape == (29, 29)
            assert np.all(np.isfinite(a['covariance']))
            np.linalg.cholesky(a['covariance'])
            if x is None:
                x = a['x']
            assert np.array_equal(a['x'], x)
            assert all(np.array_equal(a[key], previous[key]) for key in ('raw', 'covariance', 'q'))
            p = read(here / (arm + '_' + label + '_parent.json'))
            assert p['phase_qualified'] and p['precision_qualified'] and p['support_qualified']
            assert p['retained_calibration_nonempty'] and p['final_log_precision_change'] <= 1e-5
            assert p['maximum_unclipped_parent_phase_s'] <= 15.000001
            assert not set(d_ids) & (set(p['calibration_ids']) | set(p['predictive_ids']))
            assert len(p['removed_curved_ids']) == (0 if label == 'full_parent' else 480)
            assert not p['removed_predictive_ids']
            contexts.append(dict(arm=arm, context=label,
                original_remaining_gates_pass=p['original_remaining_gates_pass']))
    prep = read(here / 'preparation.json')
    assert prep['target_family_absent_from_active_curved_and_predictive']
    assert all(max(row['target_redaction_error'].values()) <= 1e-8 for row in prep['contexts'])
    result = tests(here / 'test_contrast.py')
    assert bindings(protocol['bindings']) == checked
    save('witness_preflight.json', dict(all_passed=True,
        protocol_sha256=sha(here / 'protocol.json'), bound_files_checked=checked,
        reused_RF_sealed_inputs_checked=5, actual_contexts=contexts,
        same_29_IDs_both_arms=True, target_response_redaction_passed=True,
        no_independent_witness_in_audited_persisted_fields=True,
        not_a_physical_absence_or_identity_certificate=True, tests=result,
        audit_seconds=time.monotonic() - began, orbit_propagations=0, fits=0, GPS_read=False))


def position_preflight():
    began = time.monotonic()
    here = ROOT / 'position'
    protocol = read(here / 'protocol.json')
    checked = bindings(protocol['source_input_hashes'])
    prep_protocol = read(here / 'preparation_protocol.json')
    assert bindings(prep_protocol['source_input_hashes'])
    prep = read(here / 'preparation_result.json')
    assert prep['all_passed'] and prep['rows'] == 16 and prep['seconds'] < 240
    assert protocol['total_worker_seconds'] == 600 and protocol['fit_seconds'] == 60
    assert protocol['workers'] == 2 and protocol['BLAS_threads'] == 1
    assert abs(protocol['preparation_seconds'] + 2 * protocol['arm_worker_seconds'] - 600) < 1e-9
    assert not protocol['candidate_pruning'] and not protocol['node_reduction']
    assert protocol['scientific_retries'] == 0 and not protocol['GPS_used']
    manifest = read(here / 'cache_manifest.json')['rows']
    assert len(manifest) == 24
    assert {row['order'] for row in manifest} == {16, 32, 64}
    assert len({row['norad'] for row in manifest}) == 8
    assert len({row['key'] for row in manifest}) == 24
    for row in manifest:
        states = np.load(here / 'cache' / (row['key'] + '.npy'), mmap_mode='r')
        assert not states.flags.writeable and states.shape[-3:] == (4, 2, 3)
        assert list(states.shape) == row['shape'] and states.dtype == np.float64
        assert 'parent_coefficients' not in row['inputs'] and 'covariance' not in row['inputs']
        assert 'nominal_position_km' in row['inputs'] and 'modes_position_km' in row['inputs']
    rows = [read(path) for path in sorted((here / 'equivalence').glob('*.json'))]
    assert len(rows) == 16 and {row['arm'] for row in rows} == {'c0', 'fitted_c'}
    tol = protocol['equivalence_tolerances']
    assert len([point for row in rows for point in row['points']]) == 80
    assert all(point['error'] <= 1e-6 for row in rows for point in row['points'])
    assert all(row['gradient_error'] <= 1e-5 for row in rows)
    assert all(g['errors'][name] <= tol[name] for row in rows for g in row['geometry'] for name in g['errors'])
    assert sum(len(row['geometry']) for row in rows) == 64
    assert sum(len(row['reference_orders']) for row in rows) == 12
    assert all(ref['error'] <= 1e-6 for row in rows for ref in row['reference_orders'].values())
    assert all(row['old_new_covariance_difference'] > 0 and row['direct_fresh_parent_error'] <= 1e-8
        and row['geometry_keys_unchanged'] for row in prep['cross_round'])
    # Independent finite perturbation of the Doppler range-rate derivative.
    P = np.array([[500., -250., 900.], [900., 150., 350.]])
    V = np.array([[2., -5., 4.], [-3., 1., 6.]])
    dP = np.array([[.03, .04, -.02], [-.05, .01, .03]])
    dV = np.array([[.002, -.001, .003], [.001, .003, -.002]])
    derivative_errors = []
    for observer in (np.zeros(3), np.array([10., -8., 4.])):
        line = P - observer
        direction = line / np.linalg.norm(line, axis=1)[:, None]
        rate = np.sum(direction * V, axis=1)
        grad = (V - rate[:, None] * direction) / np.linalg.norm(line, axis=1)[:, None]
        analytic = np.sum(grad * dP + direction * dV, axis=1)
        def value(eps):
            pos = P + eps * dP - observer
            return np.sum(pos * (V + eps * dV), axis=1) / np.linalg.norm(pos, axis=1)
        finite = (value(1e-3) - value(-1e-3)) / 2e-3
        derivative_errors.append(float(np.max(abs(analytic - finite))))
    assert max(derivative_errors) < 1e-10
    result = tests(here / 'test_cached.py')
    assert bindings(protocol['source_input_hashes']) == checked
    save('preflight.json', dict(all_passed=True, protocol_sha256=sha(here / 'protocol.json'),
        bound_files_checked=checked, exact_cache_state_files=24, actual_score_controls=80,
        actual_geometry_controls=64, actual_FD_gradient_controls=16,
        cross_round_parent_covariance_invalidation_verified=True,
        independent_range_rate_derivative_errors=derivative_errors,
        tests=result, audit_seconds=time.monotonic() - began,
        corpus_orbit_recomputations=0, fits=0, GPS_read=False,
        interpretation='Exact implementation equivalence, not source admission or position improvement.'))


def witness_terminal():
    began = time.monotonic()
    here = ROOT / 'witness'
    seal = read(here / 'RF_seal.json')
    protocol = read(here / 'protocol.json')
    bound = bindings(seal['files']) + bindings(protocol['bindings'])
    assert seal['protocol_sha256'] == sha(here / 'protocol.json')
    execution = read(here / 'execution.json')
    assert len(execution['slots']) == 4 and all(row['status'] == 'complete' for row in execution['slots'])
    assert execution['cumulative_worker_seconds'] <= 300
    assert execution['new_evidence_integrals'] == execution['position_fits'] == execution['identity_admissions'] == 0
    assert not execution['GPS_used']
    summary = []
    for arm in ('c0', 'fitted_c'):
        full = np.load(here / (arm + '_full_parent.npz'))
        cavity = np.load(here / (arm + '_old_union_cavity.npz'))
        comparison = read(here / (arm + '_comparison.json'))
        delta = cavity['raw'] - full['raw']
        assert np.array_equal(delta, comparison['full_minus_cavity_radio_mean_Hz'])
        assert abs(np.sqrt(np.mean(delta**2)) - comparison['radio_mean_change_RMS_Hz']) < 1e-12
        assert abs(np.mean(delta) - comparison['radio_mean_change_average_Hz']) < 1e-12
        relative = np.linalg.norm(full['covariance'] - cavity['covariance']) / np.linalg.norm(cavity['covariance'])
        assert abs(relative - comparison['covariance_relative_Frobenius_change']) < 1e-15
        for context in ('full_parent', 'old_union_cavity'):
            result = read(here / (arm + '_' + context + '_result.json'))
            diagnostic = result['source_diagnostic']
            assert result['status'] == 'complete' and result['target_not_in_parent_calibration']
            assert not result['independent_identity_validation']
            assert not diagnostic['global_MAP_certified'] and not diagnostic['shape_means_calibrated']
            assert not diagnostic['target_radio_mean_updated'] and not diagnostic['independent_owner_prediction_validated']
            assert not diagnostic['original_growth_supported']
            assert -15 <= diagnostic['phase_s'] <= 15 and diagnostic['alias'] in range(-4, 5)
            assert abs(diagnostic['causal_z'] - (diagnostic['phase_s'] - diagnostic['causal_location_s']) /
                diagnostic['causal_marginal_SD_s']) < 1e-14
            for key, raw_key in [('conservative_gate', 'conservative_raw_hz'), ('fullmode_gate', 'fullmode_raw_hz')]:
                gate = diagnostic[key]
                assert gate['compatible'] == all(gate['primitive'].values())
                assert gate['primitive']['RMS'] == (gate['rms_hz'] <= 450)
                assert gate['primitive']['constant'] == (abs(gate['bias_hz']) <= 3000)
                assert gate['primitive']['alias'] == (gate['residual_alias'] == 0)
                assert gate['primitive']['noise'] == gate['noise']['noise_screen_pass']
                assert gate['primitive']['visibility'] == (gate['minimum_elevation_deg'] >= 0)
                assert abs(gate['raw_RMS_hz'] - np.sqrt(np.mean(np.asarray(diagnostic[raw_key])**2))) < 1e-12
            if context == 'old_union_cavity':
                old = read(OLD / 'qualification' / 'DS24-0015' / (arm + '_result.json'))['source_diagnostic']
                assert diagnostic == old
                fixed = comparison['fixed_old_cavity_MAP'][context]
                assert np.array_equal(fixed['mode_coefficient'], diagnostic['mode_coefficient'])
                assert fixed['conservative_gate'] == diagnostic['conservative_gate']
                assert fixed['fullmode_gate'] == diagnostic['fullmode_gate']
            summary.append(dict(arm=arm, context=context, phase_s=diagnostic['phase_s'],
                first_mode_mean_prior_units=diagnostic['mode_coefficient'][0],
                conservative_RMS_hz=diagnostic['conservative_gate']['rms_hz'],
                conservative_compatible=diagnostic['conservative_gate']['compatible'],
                fullmode_RMS_hz=diagnostic['fullmode_gate']['rms_hz'],
                fullmode_compatible=diagnostic['fullmode_gate']['compatible'],
                remaining_parent_gates=result['old_parent_gates_pass']))
        a, b = summary[-2:]
        assert abs((a['phase_s'] - b['phase_s']) - comparison['MAP_phase_difference_s']) < 1e-15
        assert abs((a['first_mode_mean_prior_units'] - b['first_mode_mean_prior_units']) -
            comparison['MAP_mode_coefficient_difference'][0]) < 1e-15
    save('witness_terminal.json', dict(all_passed=True, protocol_sha256=sha(here / 'protocol.json'),
        RF_seal_sha256=sha(here / 'RF_seal.json'), bound_files_checked=bound,
        slots_complete=4, slots_planned=4, rows=summary,
        old_cavity_MAP_replayed_exactly=True, radio_mean_change_sign_verified=True,
        separate_archived_own_label_witnesses=0, witness_prediction_performed=False,
        audit_seconds=time.monotonic() - began, orbit_propagations=0, fits=0, GPS_read=False,
        interpretation='Restoration changes radio conditioning and target-fitted correction; neither context independently validates identity.'))


def position_terminal():
    began = time.monotonic()
    here = ROOT / 'position'
    seal = read(here / 'RF_seal.json')
    protocol = read(here / 'protocol.json')
    checked = bindings(seal['files']) + bindings(protocol['source_input_hashes'])
    assert seal['protocol_sha256'] == sha(here / 'protocol.json')
    execution = read(here / 'execution.json')
    assert execution['all_selected_terminal'] and len(execution['all6_slots']) == 6
    assert execution['cumulative_scientific_seconds'] <= 600
    assert not execution['GPS_used'] and execution['operational_policy'] == 'original_reference'
    ledger = read(ROOT.parent / 'ds24-fast-identifiability-r01' / 'transfer' /
        'ownership' / 'DS24-0011' / 'parent.json')['coverage']
    rows = []
    for arm in ('c0', 'fitted_c'):
        for method in ('no_addition', 'hard', 'mixture'):
            result = read(here / arm / (method + '_result.json'))
            assert result['arm'] == arm and result['method'] == method
            assert result['operational_policy'] == 'original_reference'
            raw_path = here / arm / method / 'raw_endpoint.json'
            row = dict(arm=arm, method=method, status=result['status'],
                raw_endpoint_available=raw_path.exists())
            if raw_path.exists():
                raw = read(raw_path)
                assert len(raw['history']) == 5 and not raw['target_association_qualified']
                assert raw['operational_policy'] == 'original_reference'
                np.testing.assert_array_equal(raw['history'][0]['reference'],
                    np.zeros(len(raw['history'][0]['reference'])))
                for first, second in zip(raw['history'][:-1], raw['history'][1:], strict=True):
                    np.testing.assert_array_equal(second['reference'], np.clip(first['unclipped_posterior_phase'], -15, 15))
                if method in ('no_addition', 'hard'):
                    old = read(OLD / 'position' / arm / method / 'raw_endpoint.json')
                    displacement = float(np.linalg.norm(np.asarray(raw['endpoint_east_north_km']) - old['endpoint_east_north_km']))
                    parent_delta = raw['parent_negative_twice_elbo'] - old['parent_negative_twice_elbo']
                    target_delta = (raw['target_prediction']['objective'] - old['target_prediction']['objective']) if method == 'hard' else 0.
                    assert displacement <= .001 and abs(parent_delta) <= 1e-3
                    assert abs(parent_delta + target_delta) <= 1e-3
                    row.update(prior_endpoint_difference_km=displacement,
                        prior_parent_ELBO_difference=parent_delta,
                        prior_full_parent_plus_target_objective_difference=parent_delta + target_delta)
                gate_path = here / arm / method / 'gates.json'
                numeric_path = here / arm / method / 'numerical_qualification.json'
                row.update(gates_available=gate_path.exists(), numerical_qualification_available=numeric_path.exists())
                if gate_path.exists():
                    gate = read(gate_path)
                    assert not gate['source_association_qualified'] and gate['operational_policy'] == 'original_reference'
                    assert not gate['source']['original_growth_supported']
                    lost = sorted(set(ledger[arm]['accepted_observation_ids']) -
                        set(gate['membership']['accepted_observation_ids']))
                    assert lost == gate['original_accepted_IDs_lost']
                    assert gate['Gamma_converged'] == (gate['final_log_precision_change'] <= 1e-5)
                    row.update(parent_valid=gate['parent_original_valid'],
                        original_accepted_IDs_lost=len(lost), Gamma_converged=gate['Gamma_converged'],
                        source_growth_supported=False, source_association_qualified=False)
                if numeric_path.exists():
                    numeric = read(numeric_path)
                    if method != 'no_addition':
                        error = max(abs(v['16'] - v['64']) for v in numeric['rows'])
                        reference_error = max(abs(v['32'] - v['64']) for v in numeric['rows'])
                        grad_error = max(float(np.max(abs(np.asarray(numeric['gradients'][str(order)]) -
                            numeric['gradients']['64']))) for order in (16, 32))
                        assert abs(error - numeric['maximum_score_error']) < 1e-10
                        assert abs(reference_error - numeric['reference_error']) < 1e-10
                        assert abs(grad_error - numeric['maximum_gradient_error']) < 1e-9
                        assert numeric['passed'] == (error <= 1e-3 and numeric['reference_error'] <= 1e-3 and grad_error <= 1e-3)
                    row['numerically_stable'] = numeric['passed']
            if result['status'] == 'complete':
                assert raw_path.exists() and row['gates_available'] and row['numerical_qualification_available']
            rows.append(row)
    save('position_terminal.json', dict(all_passed=True,
        protocol_sha256=sha(here / 'protocol.json'), RF_seal_sha256=sha(here / 'RF_seal.json'),
        bound_files_checked=checked, planned_slots=6,
        complete_slots=sum(row['status'] == 'complete' for row in rows), rows=rows,
        all_selected_terminal=True, operational_policy='original_reference',
        RF_ready_for_separate_geographic_evaluation=True,
        cumulative_scientific_seconds=execution['cumulative_scientific_seconds'],
        audit_seconds=time.monotonic() - began, orbit_propagations=0, fits=0, GPS_read=False,
        interpretation='Numerical completion and raw endpoints remain separate from source qualification and operational adoption.'))


def iq_preflight():
    began = time.monotonic()
    here = ROOT / 'iq'
    protocol = read(here / 'protocol.json')
    checked = bindings(protocol['files'])
    assert protocol['known_template_boundary_mismatch']
    assert not protocol['original_construction_check_passed']
    assert protocol['amended_construction_checks_passed']
    assert protocol['detector_calls_before_freeze'] == 0
    assert protocol['position_fits'] == 0 and not protocol['original_IQ_read']
    assert protocol['wall_cap_seconds'] == 120 and protocol['slot_cap_seconds'] == 20
    assert len(protocol['scenarios']) == 8 and protocol['seeds'] == [20261026, 20261027]
    mismatch = read(here / 'construction_mismatch.json')
    assert mismatch['count'] == 68 and mismatch['only_exact_symbol_boundaries']
    assert all(index % 44 == 0 for index in mismatch['boundary_indices'])
    assert mismatch['off_boundary_max'] < 5e-7 and mismatch['no_detector_calls']
    process = subprocess.run([sys.executable, '-B', str(here / 'test_control02.py')],
        capture_output=True, text=True, timeout=30,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    assert process.returncode == 0, process.stdout + process.stderr
    assert bindings(protocol['files']) == checked
    save('iq_preflight.json', dict(all_passed=True, protocol_sha256=sha(here / 'protocol.json'),
        bound_files_checked=checked, amended_construction_tests=5,
        test_stdout=process.stdout, test_stderr=process.stderr,
        original_frame_parity_still_failed=True, no_original_IQ_or_detector_calls_by_audit=True,
        audit_seconds=time.monotonic() - began,
        scope='Pilot-only continuous right-boundary synthetic law with known deployed-template discretization mismatch; no physical-waveform authority, field bias, identity or localization claim.'))


def geographic_readback():
    began = time.monotonic()
    here = ROOT / 'position'
    checked = bindings(read(here / 'evaluation_freeze.json')['files'])
    checked += bindings(read(here / 'geographic/seal.json')['files'])
    summary = read(here / 'geographic/summary.json')
    assert summary['completed_final_endpoints'] == 6 and not summary['partial_epochs_scored']
    def vector(latlon):
        lat, lon = np.radians(latlon)
        return np.array([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)])
    reference = vector(summary['reference_latlon'])
    def error(position):
        east, north = position
        point = vector([37.906 + north/111.,
            -122.545 + east/(111.32*math.cos(math.radians(37.906)))])
        return 6371.0088 * math.atan2(np.linalg.norm(np.cross(reference, point)), np.dot(reference, point))
    original = read(ROOT.parent / 'ds25-20261024/family_cavity/position/DS24-0011.json')['policy_arms']
    differences = []
    for row in summary['rows']:
        raw = read(here / row['arm'] / row['method'] / 'raw_endpoint.json')
        actual = error(raw['endpoint_east_north_km'])
        baseline = error(original[row['arm']]['endpoint_east_north_km'])
        differences.append(abs(actual - row['raw_position_error_km']))
        assert abs(actual - row['raw_position_error_km']) < 2e-9
        assert abs(baseline - row['original_reference_error_km']) < 2e-9
        assert abs(1000*(actual-baseline) - row['raw_error_minus_reference_m']) < 2e-6
        assert row['operational_policy_error_km'] == row['original_reference_error_km']
        assert row['operational_policy'] == 'exact_original_reference'
        assert row['final_endpoint_available'] and not row['partial_epoch_substituted']
        assert not row['target_association_qualified']
    save('geographic_readback.json', dict(all_passed=True,
        evaluation_seal_sha256=sha(here / 'geographic/seal.json'),
        RF_seal_sha256=sha(here / 'RF_seal.json'), bound_files_checked=checked,
        rows=6, independent_unit_vector_distance_maximum_error_km=max(differences),
        operational_policies_exact_original=True, all_raw_additions_unqualified=True,
        audit_seconds=time.monotonic() - began, new_fits=0, new_propagation=0,
        geographic_read_authority='Explicit root release to B after passing RF terminal audit.'))


def iq_terminal():
    began = time.monotonic()
    here = ROOT / 'iq'
    protocol = read(here / 'protocol.json')
    checked = bindings(protocol['files'])
    report_seal = read(here / 'report/seal.json')
    checked += bindings({str(here / path): digest for path, digest in report_seal.items()})
    raw = read(here / 'results.json')
    summary = read(here / 'report/summary.json')
    assert summary['protocol_sha256'] == sha(here / 'protocol.json')
    assert summary['results_sha256'] == sha(here / 'results.json')
    assert raw['total_slots'] == len(raw['slots']) == summary['total_slots'] == summary['complete_slots'] == 16
    assert raw['elapsed_seconds'] <= 120
    assert not raw['original_IQ_read'] and not raw['new_RF'] and not raw['graph_tracking'] and not raw['position_fit']
    assert raw['code_digest'] == protocol['code_digest'] and raw['environment_digest'] == protocol['environment_digest']
    assert summary['known_template_boundary_mismatch']
    assert not any(summary[key] for key in ('population_inference', 'source_identification', 'graph_test', 'position_test'))
    sources = dict(protocol['scenarios'])
    assert {(row['scenario'], row['seed']) for row in raw['slots']} == {
        (name, seed) for name in sources for seed in protocol['seeds']}
    with (here / 'report/receivers.csv').open() as stream:
        receivers = {(row['scenario'], int(row['seed']), int(row['receiver_id'])): row for row in csv.DictReader(stream)}
    samples = {name: [] for name in sources}
    counts = {name: 0 for name in sources}
    records = 0
    for slot in raw['slots']:
        assert slot == read(here / (slot['scenario'] + '_' + str(slot['seed']) + '.json'))
        assert slot['status'] == 'complete' and slot['sources'] == sources[slot['scenario']]
        assert len(slot['receivers']) == 2 and slot['input']['clipping_samples'] == 0
        assert len(slot['input']['iq_sha256']) == 64
        for receiver in slot['receivers']:
            candidates = receiver['candidates']
            assert len(candidates) <= 8
            records += len(candidates)
            fractional = [c for c in candidates if c['fractional_epoch_status'] == 'complete'
                and c['fractional_margin'] is not None]
            accepted = [c for c in fractional if c['fractional_margin'] >= .025]
            winner = max(accepted, key=lambda c: c['fractional_margin']) if accepted else None
            r = receiver['summary']
            assert r['highest_margin_accepted'] == winner
            assert r['accepted_count'] == len(accepted) and r['fractional_count'] == len(fractional)
            exported = receivers[slot['scenario'], slot['seed'], receiver['receiver_id']]
            assert int(exported['candidate_count']) == len(candidates)
            assert int(exported['accepted_count']) == len(accepted)
            counts[slot['scenario']] += bool(accepted)
            if winner:
                assert int(exported['selected_rank']) == winner['candidate_rank']
                assert float(exported['selected_CFO_hz']) == winner['fractional_tracking_cfo_hz']
                source = slot['sources'][0]
                reference = source['cfo_hz'] + .01 * source['rate_hz_s']
                difference = winner['fractional_tracking_cfo_hz'] - reference
                assert float(exported['selected_minus_strongest_midpoint_hz']) == difference
                samples[slot['scenario']].append(difference)
    assert len(receivers) == summary['receiver_outputs'] == 32
    assert records == summary['exported_candidate_records'] == 256
    for row in summary['scenarios']:
        name = row['scenario']
        assert row['complete_receiver_outputs'] == 4 and row['outputs_with_acceptance'] == counts[name]
        if samples[name]:
            assert abs(row['mean_selected_difference_hz'] - np.mean(samples[name])) < 1e-12
            assert row['minimum_selected_difference_hz'] == min(samples[name])
            assert row['maximum_selected_difference_hz'] == max(samples[name])
        else:
            assert row['mean_selected_difference_hz'] is None
    save('iq_terminal.json', dict(all_passed=True, protocol_sha256=sha(here / 'protocol.json'),
        results_sha256=sha(here / 'results.json'), report_seal_sha256=sha(here / 'report/seal.json'),
        bound_files_checked=checked, complete_paired_slots=16, receiver_outputs=32,
        all_exported_candidates=records, actual_margin_winner_verified=True,
        same_epoch_difference_hz={name: float(np.mean(samples[name])) for name in ('coincident_500', 'coincident_3000')},
        known_boundary_mismatch_retained=True, audit_seconds=time.monotonic() - began,
        detector_calls_by_audit=0, IQ_regenerations=0, new_fits=0,
        scope='Idealized declared pilot-only selection effect; not field bias, identity accuracy, graph composition or position performance.'))


if __name__ == '__main__':
    globals()[sys.argv[1]]()
