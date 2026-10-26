"""Independent saved-artifact checks; never imports a scientific runner."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

ROOT = Path('/srv/bulk/leo/research/ds24-precision-block-transfer-r01')
LATER = Path('/srv/bulk/leo/research/ds24-later-four-preparation-r01')
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
DIRTY_SHA = 'add0a0f9598b5045dbf6dd6eb05b744b856715c01a9cb3101f6890b999029a4b'
PREPARATION_SHA = '189c1cbfb11c862666a1c2912e3c75f233a387525177224f38195e6a296825d0'
RECORDINGS = [
    'fast8-auto-20261024-224359-7249fa17-1-upper',
    'fast8-auto-20261024-233414-efe03d6d-1-lower',
    'fast8-auto-20261025-002429-895cc487-1-upper',
    'fast8-auto-20261025-020456-a88a5971-1-upper',
]


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def bindings(files):
    errors = []
    for path, expected in files.items():
        try:
            actual = sha(path)
            if actual != expected:
                errors.append(dict(path=path, expected=expected, actual=actual))
        except OSError as error:
            errors.append(dict(path=path, error=str(error)))
    return errors


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def preparation_preflight():
    began = time.monotonic()
    checks = []

    def need(name, passed):
        checks.append(dict(check=name, passed=bool(passed)))

    protocol_path = LATER / 'readiness/preparation_protocol.json'
    protocol = read(protocol_path)
    need('exact_frozen_protocol', sha(protocol_path) == PREPARATION_SHA)
    errors = bindings(protocol['source_and_input_bindings'])
    need('all_frozen_source_and_input_hashes', not errors)
    sample_path = LATER / 'prepared/sample.json'
    sample = read(sample_path)
    need('original_sample_bytes', sha(sample_path) == protocol['sample_sha256'] ==
         'c19af75560ff1ff962ec73064c49b68d10fe94bd990b37b09f73e588242e8ec5')
    rows = sample['selected']
    labels = ['LATER4-%04d' % i for i in range(1, 5)]
    need('exact_four_recordings_and_order', [r['recording_id'] for r in rows] == RECORDINGS)
    need('exact_four_labels_and_order', [r['dataset_label'] for r in rows] == labels == protocol['fixed_labels'])
    need('distinct_sessions', len({r['session_id'] for r in rows}) == 4)
    validation = read(LATER / 'readiness/validation_result.json')
    for member, source in zip(rows, validation['rows'], strict=True):
        label = member['dataset_label']
        clock = member['capture_time_authority']
        need(label + '_original_public_metadata_ready', source['status'] == 'ready')
        need(label + '_recording_session_join',
             member['recording_id'] == source['recording_id'] and
             member['session_id'] == source['sample_member']['session_id'])
        need(label + '_clock_authority_exact', clock == source['clock_authority'])
        need(label + '_midpoint_and_before_bound',
             member['captured_utc_ns'] == clock['anchor_utc_ns'] ==
             (clock['first_sample_earliest_utc_ns'] + clock['first_sample_latest_utc_ns']) // 2 and
             clock['causal_cutoff_utc_ns'] == clock['first_sample_earliest_utc_ns'])
        need(label + '_raw_authority_exact', member['raw_authority_digest'] ==
             source['sample_member']['raw_authority_digest'])
        need(label + '_stored_fast_10MS', member['recording_format'] ==
             'short_window_iq_recording' and member['sample_rate_hz'] == 10_000_000)
    fixture_path = LATER / 'readiness/owned_test_receipt.json'
    fixture = read(fixture_path)
    first = read(LATER / 'readiness/owned_test_receipt01.json')
    need('six_final_owned_fixtures', fixture['all_passed'] and fixture['returncode'] == 0 and
         'Ran 6 tests' in fixture['stderr'])
    need('initial_adapter_failure_preserved', not first['all_passed'] and first['returncode'] != 0)
    need('old_metadata_cost_preserved', protocol['metadata_seconds'] == validation['numerical_seconds'] ==
         13.850415848195553)
    need('failed_and_final_fixtures_charged', protocol['freeze_and_tests_seconds'] >=
         fixture['seconds'] + first['seconds'])
    need('fixed_budget_and_workers', protocol['cumulative_worker_cap_seconds'] == 600 and
         protocol['per_case_cap_seconds'] == 140 and protocol['workers'] == 2 and
         protocol['fixed_case_reservation_seconds'] == 560)
    need('reservation_fits_original_cap', protocol['metadata_seconds'] +
         protocol['freeze_and_tests_seconds'] + 4 * protocol['per_case_cap_seconds'] <= 600)
    need('existing_all_stage_only_no_retries', protocol['command_stage'] == 'all' and
         protocol['no_retries'] and protocol['public_helper'] == str(REPO / 'tools/prepare_algo02_ds23.py'))
    need('no_preparation_already_terminal', not (LATER / 'prepared/preparation_execution.json').exists())
    diff = subprocess.check_output(['git', 'diff', '--binary'], cwd=REPO)
    need('unrelated_repository_diff_preserved', hashlib.sha256(diff).hexdigest() == DIRTY_SHA)
    reviewed = [LATER / 'readiness/preparation.py', LATER / 'readiness/test_preparation.py',
                REPO / 'tools/prepare_algo02_ds23.py', REPO / 'tools/evaluate_ds23_phase_refreshed.py',
                REPO / 'tools/prepare_ds23_genuine_causal_prior.py',
                REPO / 'tools/export_ds23_causal_history.py',
                REPO / 'tools/learn_ds23_causal_phase_forecast.py']
    result = dict(all_passed=all(r['passed'] for r in checks), protocol_sha256=sha(protocol_path),
        checks=checks, checks_passed=sum(r['passed'] for r in checks), binding_errors=errors,
        bindings_verified=len(protocol['source_and_input_bindings']),
        files={str(p): sha(p) for p in [protocol_path, fixture_path, *reviewed]},
        static_review=dict(external_new_process_group=True, descendant_SIGKILL_at_case_cap=True,
            export_and_prepare_both_covered=True, no_retry_or_replacement=True,
            source_elements_and_collection_times_causal=True,
            actual_export_clock_checked_against_frozen_sample=True,
            site_coordinate_not_an_inference_input=True),
        scope='stored GLRT export/graph/noise/causal catalogue and history preparation only; separate root GO required',
        numerical_seconds=time.monotonic() - began,
        detector_optimizer_geometry_or_IQ_calls=0)
    output = ROOT / 'audit/preparation_preflight.json'
    if output.exists():
        raise ValueError('preserve existing receipt rather than overwrite')
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(path=str(output), all_passed=result['all_passed'],
                         checks_passed=result['checks_passed'], checks=len(checks),
                         bindings_verified=result['bindings_verified'], numerical_seconds=result['numerical_seconds'])))


def mechanism_preflight():
    import numpy as np
    began = time.monotonic()
    checks = []

    def need(name, passed):
        checks.append(dict(check=name, passed=bool(passed)))

    here = ROOT / 'mechanism'
    old = Path('/srv/bulk/leo/research/ds24-cfo-precision-factorial-r01/solver')
    protocol_path = here / 'protocol.json'
    protocol = read(protocol_path)
    need('exact_frozen_protocol', sha(protocol_path) ==
         '8dfd74806124cbd2cb057ce7269437f661c010a963f434eba08746a22a044cac')
    errors = bindings(protocol['files'])
    need('all_frozen_source_and_input_hashes', not errors)
    old_errors = bindings(read(old / 'RF_seal.json')['files'])
    need('previous_RF_artifacts_immutable', not old_errors)
    cases = ['DS24-0010', 'DS24-0011']
    arms = ['c0', 'fitted_c']
    need('exact_cases_arms_and_new_cells', protocol['cases'] == cases and protocol['arms'] == arms and
         protocol['new_cells'] == [['01', 'original', 'corrected'], ['10', 'corrected', 'original']])
    need('exact_original_CFO_diagonal_mapping', protocol['diagonal_mapping'] ==
         {'00': 'old_original_CFO_cell00', '11': 'old_original_CFO_cell01'})
    need('eight_new_eight_reused_slots', protocol['new_fit_count'] == 8 and protocol['reused_diagonal_count'] == 8)
    need('fixed_solver_law_and_controls', protocol['observations'] == 'original_CFO_only' and
         protocol['volume_weight'] == 1 and protocol['phase_rounds'] == 5 and protocol['iterations'] == 48 and
         protocol['cold_position'] == [0., 0.] and protocol['cold_phase_reference'] == 'zero')
    need('fixed_caps_and_workers', protocol['cap_seconds'] == 360 and protocol['preparation_cap_seconds'] == 60 and
         protocol['maximum_seconds_per_fit'] == 30 and protocol['workers'] == 2 and protocol['BLAS_threads'] == 1)
    preparation = read(here / 'preparation.json')
    need('all_preparation_successful_and_charged', preparation['all_passed'] and
         preparation['seconds'] == protocol['preparation_seconds'] and preparation['seconds'] <= 60)
    need('four_owned_mapping_arithmetic_fixtures', '4 passed' in preparation['test_stdout'])
    controls = preparation['diagonal_controls']
    need('all_eight_diagonal_controls', len(controls) == 8 and all(r['passed'] for r in controls))
    packets = read(here / 'packets.json')
    sources = read(old / 'packets.json')
    smokes = preparation['serialized_mixed_port_smokes']
    need('eight_distinct_serialized_port_smokes', len(smokes) == 8 and
         len({(r['case'], r['arm'], r['cell']) for r in smokes}) == 8)
    for control in controls:
        name = control['case'] + '_' + control['arm'] + '_' + control['origin']
        source = sources[name]
        a = np.load(control['array_path'], allow_pickle=False)
        need(name + '_independent_saved_coefficient_residual_closure',
             np.all(np.abs(a['coefficient'] - a['source_coefficient']) <=
                    1e-6 + 1e-8 * np.abs(a['source_coefficient'])) and
             np.max(np.abs(a['residual_hz'] - a['source_residual_hz'])) <= 1e-3 and
             (not len(a['predictive_residual_hz']) or
              np.max(np.abs(a['predictive_residual_hz'] - a['source_predictive_residual_hz'])) <= 1e-3))
        need(name + '_exact_packet_and_reference', np.array_equal(a['noise_precision'], source['noise_precision']) and
             np.array_equal(a['prior_precision'], source['coefficient_prior_precision']) and
             control['phase_reference'] == source['final_phase_reference'] and
             control['source_endpoint'] == source['source_endpoint'])
        need(name + '_predictive_factor_retained', control['predictive_points'] ==
             (615 if control['case'] == 'DS24-0010' else 0) and abs(control['predictive_objective_difference']) <= 1e-3 and
             control['predictive_relative_error'] <= 1e-8)
    for smoke in smokes:
        case, arm, cell = (smoke[k] for k in ('case', 'arm', 'cell'))
        name = case + '_' + arm + '_' + cell
        packet = packets[name]
        noise_origin, prior_origin = ('original', 'corrected') if cell == '01' else ('corrected', 'original')
        n = sources[case + '_' + arm + '_' + noise_origin]
        p = sources[case + '_' + arm + '_' + prior_origin]
        original = next(r for r in controls if (r['case'], r['arm'], r['origin']) == (case, arm, 'original'))
        need(name + '_exact_noise_prior_swap', packet['noise_precision'] == n['noise_precision'] and
             packet['coefficient_prior_precision'] == p['coefficient_prior_precision'] and
             packet['layout'] == n['layout'] == p['layout'] and
             packet['noise_source_sha256'] == digest(n) and packet['prior_source_sha256'] == digest(p))
        need(name + '_original_data_alias_layout_smoke', smoke['passed'] and smoke['exact_selected_blocks'] and
             smoke['values_sha256'] == original['values_sha256'] and smoke['aliases'] == original['aliases'] and
             smoke['layout'] == packet['layout'] and smoke['packet_sha256'] == digest(packet))
        need(name + '_inactive_noise_and_fitted_c_slot_preserved',
             np.array_equal(np.asarray(packet['noise_precision']) == 0, np.asarray(p['noise_precision']) == 0) and
             (arm == 'c0' or packet['coefficient_prior_precision'][8] == 1.))
        need(name + '_no_packet_mean_or_reference_carried', not packet['nuisance_means_carried'] and
             not packet['phase_reference_carried'])
    for case in cases:
        rr = [r for r in controls if r['case'] == case and r['origin'] == 'original']
        need(case + '_same_observations_in_both_c_arms', len({r['values_sha256'] for r in rr}) == 1 and
             rr[0]['aliases'] == rr[1]['aliases'])
    need('evaluator_frozen_before_endpoints', protocol['evaluator_frozen_before_results'] and
         str(here / 'evaluate.py') in protocol['files'] and not (here / 'execution.json').exists())
    result = dict(all_passed=all(r['passed'] for r in checks), protocol_sha256=sha(protocol_path),
        checks=checks, checks_passed=sum(r['passed'] for r in checks),
        binding_errors=errors + old_errors, bindings_verified=len(protocol['files']),
        files={str(p): sha(p) for p in [protocol_path, here / 'blocks.py', here / 'run.py',
               here / 'evaluate.py', here / 'preparation.json', here / 'packets.json']},
        static_review=dict(same_original_conditional_builder_and_predictive_wrapper=True,
            same_conditional_posterior_membership_and_gates=True, no_Gamma_update_or_VI_objective_comparison=True,
            zero_cold_references_and_original_refresh_rule=True, no_target_or_packet_selection_from_GPS=True,
            thirty_second_fit_alarm_covers_five_rounds=True, failure_slots_retained=True),
        scope='eight mixed noise/prior fits at original CFO only; separate root GO required',
        numerical_seconds=time.monotonic() - began, detector_optimizer_geometry_or_IQ_calls=0)
    output = ROOT / 'audit/mechanism_preflight.json'
    if output.exists():
        raise ValueError('preserve existing receipt rather than overwrite')
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(path=str(output), all_passed=result['all_passed'],
                         checks_passed=result['checks_passed'], checks=len(checks),
                         bindings_verified=result['bindings_verified'], numerical_seconds=result['numerical_seconds'])))


def preparation_terminal():
    began = time.monotonic()
    checks = []
    def need(name, passed):
        checks.append(dict(check=name, passed=bool(passed)))
    run = LATER / 'prepared'
    protocol = read(LATER / 'readiness/preparation_protocol.json')
    execution = read(run / 'preparation_execution.json')
    seal_path = run / 'preparation_RF_seal.json'
    seal = read(seal_path)
    errors = bindings(seal['files']) + bindings(protocol['source_and_input_bindings'])
    need('all_frozen_inputs_and_terminal_outputs_exact', not errors)
    need('exact_protocol_and_go', execution['protocol_sha256'] == seal['protocol_sha256'] == PREPARATION_SHA and
         read(ROOT / 'preparation_go.json')['protocol_sha256'] == PREPARATION_SHA and
         read(ROOT / 'preparation_go.json')['authorized'])
    rows = execution['rows']
    need('all_four_terminal_denominator', execution['terminal'] and execution['all_four_slots_preserved'] and
         [r['case'] for r in rows] == ['LATER4-%04d' % i for i in range(1, 5)])
    expected_time = protocol['metadata_seconds'] + protocol['freeze_and_tests_seconds'] + sum(r['charged_seconds'] for r in rows)
    need('original_cumulative_budget_exact', expected_time == execution['cumulative_worker_seconds'] and
         execution['budget_pass'] and expected_time <= 600)
    sample = read(run / 'sample.json')['selected']
    evidence = []
    for row, member in zip(rows, sample, strict=True):
        label = row['case']
        directory = run / label
        need(label + '_helper_terminal_waited_no_retry', row['status'] == 'prepared' and row['returncode'] == 0 and
             row['no_retry'] and row['elapsed_seconds'] <= 140 and not Path('/proc/%s' % row['pid']).exists())
        complete_path = directory / 'preparation_receipt.json'
        complete = read(complete_path)
        need(label + '_complete_receipt_and_output_bindings', sha(complete_path) == row['preparation_receipt_sha256'] and
             not bindings({str(run / p): h for p, h in complete['files_sha256'].items()}))
        prepared = read(directory / 'prepared.json')
        receipt = read(directory / 'receipt.json')
        clock = member['capture_time_authority']
        need(label + '_actual_clock_and_causal_cutoff', prepared['metadata']['anchor_utc_ns'] == receipt['origin_utc_ns'] ==
             clock['anchor_utc_ns'] and prepared['metadata']['causal_cutoff_utc_ns'] == receipt['cutoff_utc_ns'] ==
             clock['causal_cutoff_utc_ns'])
        cutoff = receipt['cutoff_utc_ns']
        elements = read(directory / 'nominal_elements.json')
        need(label + '_every_nominal_element_and_collection_causal', len(elements) == receipt['candidate_count'] and
             all(e['provenance']['element_epoch_utc_ns'] <= cutoff and
                 e['provenance']['collected_utc_ns'] <= cutoff for e in elements.values()))
        previous = read(directory / 'previous_receipt.json')
        need(label + '_every_previous_element_and_collection_causal', all(
             e['epoch_utc_ns'] <= cutoff and e['collected_utc_ns'] <= cutoff for e in previous['sources'].values()))
        history = read(run / 'causal_phase_history' / (label + '.json'))
        forecast = read(run / 'causal_phase_history' / (label + '_forecast.json'))
        need(label + '_entire_history_and_forecast_causal', history['cutoff_utc_ns'] == cutoff and
             history['origin_utc_ns'] == receipt['origin_utc_ns'] and
             all(v['epoch'] <= cutoff and v['collected_utc_ns'] <= cutoff for vv in history['past_versions'].values() for v in vv) and
             all(s['collected_utc_ns'] <= cutoff for s in history['sources']) and
             forecast['strictly_pre_RF'] and not forecast['GPS_or_radio_used'])
        observations = read(directory / 'observations.json')
        tracks = read(directory / 'tracks.json')
        ids = [o['observation_id'] for o in observations]
        graph_ids = [oid for t in tracks for oid in t['observation_ids']]
        need(label + '_native_and_graph_ownership', len(ids) == len(set(ids)) == prepared['GLRT_points'] and
             len(graph_ids) == len(set(graph_ids)) and set(graph_ids) <= set(ids))
        exported = read(directory / 'input_receipt.json')
        need(label + '_unchanged_stored_GLRT_authority', exported['status'] == 'exported' and
             exported['recording_id'] == member['recording_id'] and
             exported['raw_authority_digest'] == member['raw_authority_digest'] and
             exported['sample_sha256'] == protocol['sample_sha256'] and
             sha(directory / 'tracking.json') == exported['tracking_sha256'])
        evidence.append(dict(case=label, status=row['status'], native_points=len(ids), graph_points=len(graph_ids),
                             graph_tracks=len(tracks), causal_candidates=len(elements), elapsed_seconds=row['elapsed_seconds']))
    result = dict(all_passed=all(c['passed'] for c in checks), checks=checks,
        checks_passed=sum(c['passed'] for c in checks), binding_errors=errors,
        protocol_sha256=PREPARATION_SHA, RF_seal_sha256=sha(seal_path),
        all_four_slots_preserved=True, per_case=evidence,
        cumulative_worker_seconds=execution['cumulative_worker_seconds'],
        completion_evidence='session34065 explicitly exited0; each external child returncode0 and PID absent',
        ready_for_separate_retained_baseline=True,
        scope='stored GLRT preparation; no new IQ, detector, baseline inference or geographic evaluation',
        numerical_seconds=time.monotonic() - began, detector_optimizer_geometry_or_IQ_calls=0,
        files={str(p): sha(p) for p in [seal_path, run / 'preparation_execution.json',
               LATER / 'readiness/preparation_protocol.json', ROOT / 'audit/preparation_preflight.json']})
    output = ROOT / 'audit/preparation_terminal.json'
    if output.exists():
        raise ValueError('preserve existing receipt rather than overwrite')
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(path=str(output), all_passed=result['all_passed'], checks_passed=result['checks_passed'],
                         checks=len(checks), scientific_worker_seconds=execution['cumulative_worker_seconds'],
                         numerical_seconds=result['numerical_seconds'])))


def baseline_preflight():
    began = time.monotonic()
    checks = []
    def need(name, passed):
        checks.append(dict(check=name, passed=bool(passed)))
    here = LATER / 'baseline'
    protocol_path = here / 'later_protocol.json'
    protocol = read(protocol_path)
    need('exact_frozen_baseline_protocol', sha(protocol_path) ==
         '14ba38b351db4b7c4e259126e674e6b93be29fc96079ed56a3a164cdad616fab')
    errors = bindings(protocol['input_bindings']) + bindings(protocol['source_bindings'])
    need('all_retained_source_and_owned_input_hashes', not errors)
    terminal = read(ROOT / 'audit/preparation_terminal.json')
    need('audited_terminal_preparation', terminal['all_passed'] and terminal['RF_seal_sha256'] ==
         sha(LATER / 'prepared/preparation_RF_seal.json'))
    cases = ['LATER4-%04d' % i for i in range(1, 5)]
    need('all_four_members_no_substitution', protocol['cases'] == cases and
         set(protocol['prepared_ready']) == set(cases) and all(protocol['prepared_ready'].values()))
    for path in protocol['input_bindings']:
        p = Path(path)
        if p.is_relative_to(here / 'work'):
            need('owned_copy_' + str(p.relative_to(here / 'work')),
                 sha(p) == sha(LATER / 'prepared' / p.relative_to(here / 'work')))
    for case in cases:
        stages = protocol['stages'][case]
        need(case + '_full_discovery_then_exact_engine', [s[0] for s in stages] == ['algo02', 'cavity'] and
             stages[0][1][1] == str(REPO / 'tools/algo02_scan.py') and stages[0][1][-2:] == ['--stage', 'all'] and
             stages[1][1][1] == '/srv/bulk/leo/research/ds25-20261024/engine/ds24_engine.py' and
             stages[0][1][3] == stages[1][1][3] == str(here / 'work') and
             stages[0][1][5] == stages[1][1][5] == case)
    replay = read(here / 'replay.json')
    runner_tests = read(here / 'later_runner_tests.json')
    selector_tests = read(here / 'selector_v2_tests.json')
    need('old_final_state_replay_passes_without_discovery_claim', replay['all_passed'] and
         replay['optimizer_calls'] == 0 and replay['new_scan_baselines'] == 0 and replay['equal_prior_adoption_exact'])
    need('runner_and_original_selector_oracle_tests_pass', runner_tests['returncode'] == selector_tests['returncode'] == 0 and
         '3 passed' in runner_tests['stdout'] and '4 passed' in selector_tests['stdout'])
    need('prospective_budget_fixed', protocol['per_case_cap'] == 180 and protocol['cumulative_cap'] == 840 and
         protocol['workers'] == 2 and protocol['BLAS_threads'] == 1 and protocol['no_retry'] and
         protocol['prior_replay_seconds'] == replay['cumulative_numerical_seconds'] and
         protocol['preparation_seconds'] <= 60 and
         protocol['prior_replay_seconds'] + protocol['preparation_seconds'] + 4 * 180 <= 840)
    need('no_new_baseline_already_executed', not (here / 'later_execution.json').exists() and
         not list(here.glob('LATER4-*_baseline_execution.json')))
    result = dict(all_passed=all(c['passed'] for c in checks), checks=checks,
        checks_passed=sum(c['passed'] for c in checks), binding_errors=errors,
        protocol_sha256=sha(protocol_path), input_bindings_verified=len(protocol['input_bindings']),
        source_bindings_verified=len(protocol['source_bindings']),
        static_review=dict(original_external_process_group_supervisor=True,
            aggregate_case_cap_does_not_reset_between_stages=True,
            exact_signed_then_equal_assignment_prior_retained_policy=True,
            original_replay_is_final_state_only_not_full_discovery_parity=True,
            original_selector_denominator_restored_in_separate_version=True,
            original_families_positions_or_GPS_not_used_to_seed_new_inputs=True),
        scope='four full retained baseline creations only; RF owner ranking/nomination is not executed by this runner',
        separate_root_GO_required=True, numerical_seconds=time.monotonic() - began,
        detector_optimizer_geometry_or_IQ_calls=0,
        files={str(p): sha(p) for p in [protocol_path, here / 'run_later.py', here / 'selector_v2.py',
               here / 'replay.json', here / 'replay_seal.json', ROOT / 'audit/preparation_terminal.json']})
    output = ROOT / 'audit/baseline_preflight.json'
    if output.exists():
        raise ValueError('preserve existing receipt rather than overwrite')
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(path=str(output), all_passed=result['all_passed'], checks_passed=result['checks_passed'],
                         checks=len(checks), source_bindings=result['source_bindings_verified'],
                         input_bindings=result['input_bindings_verified'], numerical_seconds=result['numerical_seconds'])))


def mechanism_terminal():
    import numpy as np
    began = time.monotonic()
    checks = []
    def need(name, passed):
        checks.append(dict(check=name, passed=bool(passed)))
    here = ROOT / 'mechanism'
    protocol_path = here / 'protocol.json'
    protocol = read(protocol_path)
    seal_path = here / 'RF_seal.json'
    seal = read(seal_path)
    execution = read(here / 'execution.json')
    errors = bindings(seal['files']) + bindings(protocol['files'])
    report_path = here / 'rf_report/seal.json'
    errors += bindings(read(report_path)['files'])
    need('all_scientific_source_endpoint_and_RF_report_bindings_exact', not errors)
    need('matching_preflight_GO_protocol', seal['protocol_sha256'] == sha(protocol_path) ==
         read(ROOT / 'audit/mechanism_preflight.json')['protocol_sha256'] ==
         read(ROOT / 'mechanism_go.json')['protocol_sha256'] and read(ROOT / 'mechanism_go.json')['approved'])
    slots = execution['all8_slots']
    expected = {(c, a, k) for c in protocol['cases'] for a in protocol['arms'] for k, _, _ in protocol['new_cells']}
    need('all_eight_exact_terminal_slots', execution['all_selected_terminal'] and seal['all_selected_terminal'] and
         len(slots) == 8 and {(s['case'], s['arm'], s['cell']) for s in slots} == expected and
         all(s['status'] == 'complete' for s in slots))
    need('frozen_budget_preserved', protocol['preparation_seconds'] + sum(c['seconds'] for c in execution['cases']) <=
         execution['cumulative_worker_seconds'] <= 360 and all(s['seconds'] <= 30 for s in slots))
    packets = read(here / 'packets.json')
    evidence = []
    for slot in slots:
        case, arm, cell = (slot[k] for k in ('case', 'arm', 'cell'))
        name = case + '_' + arm + '_' + cell
        path = here / case / arm / cell
        raw = read(path / 'raw_endpoint.json')
        gates = read(path / 'gates.json')
        summary = raw['summary']
        packet = packets[name]
        need(name + '_runtime_frozen_blocks_and_original_CFO', raw['noise_precision'] == packet['noise_precision'] and
             raw['coefficient_prior_precision'] == packet['coefficient_prior_precision'] and
             raw['precision_packet_sha256'] == digest(packet) and raw['CFO'] == 'original' and
             raw['Gamma_updated'] is False and raw['objective_kind'] == 'same_conditional_Gaussian_not_VI_ELBO')
        history = summary['history']
        valid_history = len(history) == 5
        previous_phase = np.zeros(len(packet['layout']['labels']))
        for index, h in enumerate(history):
            valid_history = valid_history and h['epoch'] == index and np.array_equal(h['reference'], previous_phase)
            change = float(np.max(np.abs(np.clip(h['unclipped_phase_s'], -15, 15) - np.asarray(h['reference']))))
            valid_history = valid_history and abs(change - h['phase_change_s']) <= 1e-14
            previous_phase = np.clip(h['unclipped_phase_s'], -15, 15)
            valid_history = valid_history and read(path / ('epoch%d.json' % index)) == h
        need(name + '_five_cold_phase_refreshes_and_checkpoints', valid_history and
             history[0]['fit']['history'][0]['parameters'] == [0., 0.] and
             all(len(h['fit']['history']) <= 49 for h in history) and
             summary['phase_reference'] == history[-1]['reference'] and
             summary['final_phase_change_s'] == history[-1]['phase_change_s'])
        phase = np.asarray(summary['state']['phases'])
        x = np.asarray(summary['endpoint_east_north_km'])
        tracks = summary['gates']['tracks'] + summary.get('linear_gates', [])
        single = bool(tracks and all(t['compatible'] for t in tracks) and x.shape == (2,) and
                      np.isfinite(x).all() and np.all(abs(x) <= 12.5 + 1e-8) and
                      summary['final_phase_change_s'] <= .01 and np.max(abs(phase)) <= 15.000001)
        need(name + '_original_record_gate_decision_recomputed', single == gates['original_single_arm_valid'] ==
             slot['original_single_arm_valid'] and np.max(abs(phase)) == gates['maximum_unclipped_phase_s'])
        membership = gates['membership']
        parent = read(Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership') / case / 'parent.json')['coverage'][arm]
        curved, predictive = (membership[k] for k in ('curved_observation_ids', 'predictive_observation_ids'))
        need(name + '_full_original_disjoint_likelihood', curved == parent['curved_observation_ids'] and
             predictive == parent['predictive_observation_ids'] and len(curved + predictive) == len(set(curved + predictive)) and
             len(predictive) == (615 if case == 'DS24-0010' else 0))
        lost = sorted(set(parent['accepted_observation_ids']) - set(membership['accepted_observation_ids']))
        need(name + '_accepted_ID_loss_exact_and_postfit_only', lost == gates['original_accepted_IDs_lost'] and
             len(lost) == slot['original_accepted_IDs_lost'] and not set(lost).intersection(curved + predictive))
        need(name + '_same_actual_posterior_gates', not gates['VI_rebuild'] and
             membership['posterior_kind'] == 'same_frozen_conditional_Gaussian_instance' and
             gates['frozen_Gamma_no_convergence_claim'] and raw['conditional_Gaussian_objective'] ==
             summary['negative_twice_elbo'] == slot['conditional_Gaussian_objective'])
        evidence.append(dict(case=case, arm=arm, cell=cell, complete=True, original_single_arm_valid=single,
                             original_postfit_IDs_lost=len(lost), fixed_likelihood_points=len(curved + predictive),
                             final_phase_change_s=summary['final_phase_change_s']))
    report = read(here / 'rf_report/summary.json')
    need('all_sixteen_new_and_reused_report_slots', len(report['rows']) == 16 and
         sum(r['new_fit'] for r in report['rows']) == 8)
    independently_derived = []
    for contrast in report['contrasts']:
        case, arm = contrast['case'], contrast['arm']
        rr = {r['cell']: r for r in report['rows'] if r['case'] == case and r['arm'] == arm}
        x = {k: np.array([r['east_km'], r['north_km']]) for k, r in rr.items()}
        vectors = dict(noise_at_original_prior=x['10']-x['00'], noise_at_refined_prior=x['11']-x['01'],
            prior_at_original_noise=x['01']-x['00'], prior_at_refined_noise=x['11']-x['10'],
            interaction=x['11']-x['10']-x['01']+x['00'], total=x['11']-x['00'])
        vectors.update(symmetric_noise=(vectors['noise_at_original_prior']+vectors['noise_at_refined_prior'])/2,
                       symmetric_prior=(vectors['prior_at_original_noise']+vectors['prior_at_refined_noise'])/2)
        need(case + '_' + arm + '_independent_signed_vectors_and_units', all(
            np.allclose(v, contrast['vectors_km'][k], rtol=0, atol=1e-14) and
            abs(np.linalg.norm(v)*1000-contrast['norms_m'][k]) <= 1e-10 for k, v in vectors.items()) and
            np.linalg.norm(vectors['symmetric_noise']+vectors['symmetric_prior']-vectors['total']) <= 1e-14)
        independently_derived.append(dict(case=case, arm=arm,
            symmetric_noise_m=float(np.linalg.norm(vectors['symmetric_noise'])*1000),
            symmetric_prior_m=float(np.linalg.norm(vectors['symmetric_prior'])*1000),
            interaction_m=float(np.linalg.norm(vectors['interaction'])*1000)))
    for row in report['rows']:
        pair = [r for r in report['rows'] if r['case'] == row['case'] and r['cell'] == row['cell']]
        expected_paired = len(pair) == 2 and all(r['status'] == 'complete' and r['original_single_arm_valid'] and
                          r['final_phase_change_s'] <= .01 and r['original_accepted_IDs_lost'] == 0 for r in pair)
        need(row['case'] + '_' + row['arm'] + '_' + row['cell'] + '_paired_guard_label',
             row['paired_research_guards_pass'] == expected_paired)
    result = dict(all_passed=all(c['passed'] for c in checks), checks=checks,
        checks_passed=sum(c['passed'] for c in checks), binding_errors=errors,
        protocol_sha256=sha(protocol_path), RF_seal_sha256=sha(seal_path),
        RF_ready_for_separate_geographic_evaluation=all(c['passed'] for c in checks),
        completion_evidence='sole session11694 explicitly exited0; all eight complete saved endpoints and five-round checkpoints present',
        per_slot=evidence, independent_original_CFO_contrasts=independently_derived,
        cumulative_worker_seconds=execution['cumulative_worker_seconds'],
        interpretation='conditional noise/prior block intervention only; no physical noise validation, Gamma convergence claim or operational adoption',
        numerical_seconds=time.monotonic() - began, detector_optimizer_geometry_or_IQ_calls=0,
        files={str(p): sha(p) for p in [seal_path, protocol_path, here / 'execution.json', report_path,
               ROOT / 'audit/mechanism_preflight.json']})
    output = ROOT / 'audit/mechanism_terminal.json'
    if output.exists():
        raise ValueError('preserve existing receipt rather than overwrite')
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(path=str(output), all_passed=result['all_passed'], checks_passed=result['checks_passed'],
                         checks=len(checks), numerical_seconds=result['numerical_seconds'])))


def geographic_readback():
    import math
    began = time.monotonic()
    here = ROOT / 'mechanism'
    seal_path = here / 'geographic/seal.json'
    geo = read(here / 'geographic/summary.json')
    rf = read(here / 'rf_report/summary.json')
    errors = bindings(read(seal_path)['files'])
    checks = []
    def need(name, passed):
        checks.append(dict(check=name, passed=bool(passed)))
    need('geographic_bindings_and_RF_terminal_immutable', not errors and
         read(ROOT / 'audit/mechanism_terminal.json')['all_passed'])
    need('all_sixteen_new_and_reused_geographic_rows', len(geo['rows']) == 16)
    lookup = {(r['case'], r['arm'], r['cell']): r for r in rf['rows']}
    reference = geo['reference_latlon']
    def latlon(x):
        return [37.906+x[1]/111., -122.545+x[0]/(111.32*math.cos(math.radians(37.906)))]
    def unit(ll):
        lat, lon = map(math.radians, ll)
        return [math.cos(lat)*math.cos(lon), math.cos(lat)*math.sin(lon), math.sin(lat)]
    def distance(x):
        a, b = unit(latlon(x)), unit(reference)
        cross = [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
        return 6371.0088*math.atan2(math.sqrt(sum(v*v for v in cross)), sum(u*v for u,v in zip(a,b)))
    maximum = 0.
    for row in geo['rows']:
        key = row['case'], row['arm'], row['cell']
        source = lookup[key]
        error = abs(distance([source['east_km'], source['north_km']])-row['raw_position_error_km'])
        maximum = max(maximum, error)
        original = read(Path('/srv/bulk/leo/research/ds24-complete-owner-refinement-r01/position') /
                        row['case'] / 'original' / row['arm'] / 'raw_endpoint.json')['summary']['endpoint_east_north_km']
        need('_'.join(key) + '_same_RF_endpoint_qualification_and_independent_distance', error < 1e-8 and
             row['east_km'] == source['east_km'] and row['north_km'] == source['north_km'] and
             row['paired_research_guards_pass'] == source['paired_research_guards_pass'] and
             abs(distance(original)-row['operational_reference_error_km']) < 1e-8 and
             row['operational_policy_error_km'] == row['operational_reference_error_km'])
    result = dict(all_passed=all(c['passed'] for c in checks), checks=checks,
        checks_passed=sum(c['passed'] for c in checks), binding_errors=errors,
        rows_checked=16, maximum_independent_raw_distance_error_km=maximum,
        root_geographic_release='A explicitly confirmed root release before this saved-only readback',
        operational_policy='exact_original_reference', scope='existing two development scans only; no later-four geographic read',
        numerical_seconds=time.monotonic()-began, new_fits_or_geometry=0,
        files={str(p):sha(p) for p in [seal_path, here / 'geographic/summary.json', ROOT / 'audit/mechanism_terminal.json']})
    output = ROOT / 'audit/geographic_readback.json'
    if output.exists():
        raise ValueError('preserve existing receipt rather than overwrite')
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(output), all_passed=result['all_passed'], checks_passed=result['checks_passed'],
                         checks=len(checks), maximum_error_km=maximum, numerical_seconds=result['numerical_seconds'])))


def baseline_terminal():
    import numpy as np
    began = time.monotonic()
    here = LATER / 'baseline'
    protocol_path = here / 'later_protocol.json'
    protocol = read(protocol_path)
    seal_path = here / 'later_RF_seal.json'
    seal = read(seal_path)
    execution = read(here / 'later_execution.json')
    errors = bindings(seal['files']) + bindings(protocol['source_bindings']) + bindings(protocol['input_bindings'])
    checks = []
    def need(name, passed):
        checks.append(dict(check=name, passed=bool(passed)))
    need('all_source_input_and_terminal_output_hashes_exact', not errors)
    need('actual_terminal_denominator_and_GO', execution['terminal'] and execution['all_four_slots_preserved'] and
         [r['case'] for r in execution['rows']] == protocol['cases'] and
         seal['protocol_sha256'] == execution['protocol_sha256'] == sha(protocol_path) ==
         read(ROOT / 'baseline_go.json')['protocol_sha256'] and read(ROOT / 'baseline_go.json')['authorized'])
    need('prospective_840_second_cumulative_cap', execution['budget_pass'] and
         execution['cumulative_worker_seconds'] == protocol['prior_replay_seconds'] + protocol['preparation_seconds'] +
         sum(r['seconds'] for r in execution['rows']) and execution['cumulative_worker_seconds'] <= 840)
    evidence = []
    for row in execution['rows']:
        case = row['case']
        need(case + '_full_two_stage_processes_terminal', row['status'] == 'complete' and row['seconds'] <= 180 and
             [s['stage'] for s in row['stages']] == ['algo02', 'cavity'] and
             all(s['returncode'] == 0 for s in row['stages']))
        d = read(row['result_path'])
        need(case + '_qualified_full_retained_policy', sha(row['result_path']) == row['result_sha256'] and
             d['status'] == 'complete' and d['reconstructed_fresh_reference'] and
             d['adoption'] == 'equal_assignment_priors_minimum_corrected_normalized_c0' and
             set(d['policy_arms']) == {'c0', 'fitted_c'})
        eligible = [t for t in d['trials'] if t['paired_valid']]
        best = min(eligible, key=lambda t: t['arms']['c0']['corrected_selection_loss']) if eligible else None
        accepted = bool(best and best['arms']['c0']['corrected_selection_loss'] < d['baseline_corrected_loss']['c0'])
        expected_arms = best['arms'] if accepted else d['baseline_arms']
        need(case + '_equal_assignment_adoption_independently_recomputed', accepted == d['accepted'] and
             d['selected'] == (best if accepted else None) and d['policy_arms'] == expected_arms)
        observation_ids = {o['observation_id'] for o in read(here / 'work' / case / 'observations.json')}
        arm_ids = []
        phase_eligible = []
        phase_maxima = {}
        for arm in ['c0', 'fitted_c']:
            p = d['policy_arms'][arm]
            x = np.asarray(p['endpoint_east_north_km'])
            tracks = p['gates']['tracks'] + p.get('linear_gates', [])
            ids = [oid for t in tracks for oid in t['observation_ids']]
            arm_ids.append(set(ids))
            phase_maxima[arm] = float(np.max(abs(np.asarray(p['state']['phases']))))
            phase_eligible.append(phase_maxima[arm] <= 15.000001)
            need(case + '_' + arm + '_producer_RF_region_and_refresh_gates', bool(tracks) and
                 all(t['compatible'] for t in tracks) and x.shape == (2,) and np.isfinite(x).all() and
                 np.all(abs(x) <= 12.5 + 1e-8) and
                 p['final_phase_change_s'] <= .01)
            need(case + '_' + arm + '_unique_native_likelihood_ownership', len(ids) == len(set(ids)) and
                 set(ids) <= observation_ids and all(t['points'] == len(t['observation_ids']) for t in tracks))
        need(case + '_matched_both_arm_likelihood_and_no_future_or_GPS', arm_ids[0] == arm_ids[1] and
             d['same_full_original_observations_and_physical_priors_in_all_trials'] and
             d['no_GPS_RF_future_TLE_or_point_deletion'])
        evidence.append(dict(case=case, status=row['status'], full_route_seconds=row['seconds'],
            equal_prior_alternative_adopted=accepted, family_trials=len(d['trials']),
            full_GLRT_points=len(observation_ids), matched_likelihood_points=len(arm_ids[0]),
            maximum_absolute_phase_s=phase_maxima, stricter_nomination_phase_guard_passes=all(phase_eligible)))
    result = dict(all_passed=all(c['passed'] for c in checks), checks=checks,
        checks_passed=sum(c['passed'] for c in checks), binding_errors=errors,
        protocol_sha256=sha(protocol_path), baseline_RF_seal_sha256=sha(seal_path),
        all_four_slots_preserved=True, per_case=evidence,
        full_producer_complete_count=len(evidence), stricter_phase_qualified_count=sum(
            r['stricter_nomination_phase_guard_passes'] for r in evidence),
        qualification_note='Producer completion is distinct from the fixed nomination absolute-phase guard; 0004 is retained but phase-unqualified, without waiver or replacement.',
        cumulative_worker_seconds=execution['cumulative_worker_seconds'],
        completion_evidence='root-owned session75078 explicitly exited0; all eight stage subprocesses returncode0',
        scope='full retained RF baselines only; no later geographic outcomes or CFO refinements read',
        ready_for_frozen_RF_owner_nomination=True, numerical_seconds=time.monotonic()-began,
        detector_optimizer_geometry_or_IQ_calls=0,
        files={str(p):sha(p) for p in [seal_path, protocol_path, here / 'later_execution.json', ROOT / 'audit/baseline_preflight.json']})
    output = ROOT / 'audit/baseline_terminal.json'
    if output.exists():
        raise ValueError('preserve existing receipt rather than overwrite')
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(output), all_passed=result['all_passed'], checks_passed=result['checks_passed'],
                         checks=len(checks), numerical_seconds=result['numerical_seconds'])))


def nomination_preflight():
    began = time.monotonic()
    here = LATER / 'baseline/nomination'
    protocol_path = here / 'protocol02.json'
    protocol = read(protocol_path)
    baseline_seal = LATER / 'baseline/later_RF_seal.json'
    checks = []
    def need(name, passed):
        checks.append(dict(check=name, passed=bool(passed)))
    need('exact_version02_protocol', sha(protocol_path) ==
         'f50e4d63ef815944eea722c97ab047e03bd289ce19ea242ceec5141f3798b614')
    errors = bindings(protocol['source_bindings']) + bindings(read(baseline_seal)['files'])
    need('all_frozen_sources_and_terminal_parents_exact', not errors)
    terminal = read(ROOT / 'audit/baseline_terminal.json')
    need('passing_exact_baseline_terminal', terminal['all_passed'] and
         terminal['baseline_RF_seal_sha256'] == sha(baseline_seal))
    smoke = read(here / 'actual_smoke02.json')
    first = read(here / 'actual_smoke.json')
    need('first_failed_prerequisite_smoke_preserved_without_scores', not first['all_passed'] and
         first['J_or_ranking_or_score_or_optimizer_calls'] == 0 and
         first['nomination_protocol_sha256'] == sha(here / 'protocol.json') and
         first['source_sha256'] == sha(here / 'actual_smoke.py'))
    need('actual_four_context_smoke_matches_final_source_and_seal', smoke['all_passed'] and
         smoke['source_sha256'] == sha(here / 'actual_smoke02.py') and
         smoke['nomination_protocol_sha256'] == sha(protocol_path) and
         smoke['baseline_RF_seal_sha256'] == sha(baseline_seal) and
         smoke['J_or_ranking_or_score_or_optimizer_calls'] == 0 and not smoke['GPS_read'])
    cases = ['LATER4-%04d' % i for i in range(1, 5)]
    need('all_four_cases_and_matched_arms_no_subset', protocol['cases'] == cases and
         protocol['arms'] == ['c0', 'fitted_c'] and [r['case'] for r in smoke['rows']] == cases)
    for row in smoke['rows']:
        case = row['case']
        parent_path = LATER / 'baseline/work/family_cavity/position' / (case + '.json')
        parent = read(parent_path)
        selected = parent['selected'] if parent['accepted'] else None
        entries = selected['entries'] if selected else parent['baseline_entries']
        need(case + '_exact_saved_retained_parent_and_predictive_joins', row['parent_sha256'] == sha(parent_path) and
             row['passed'] and row['whole_predictive_joins_exact'] and row['predictive_IDs'] ==
             sum(len(e['observation_ids']) for e in entries))
        for arm in ['c0', 'fitted_c']:
            need(case + '_' + arm + '_saved_phase_reference_and_unclipped_diagnostic',
                 row['phase_reference_lengths'][arm] == len(parent['policy_arms'][arm]['phase_reference']) and
                 row['absolute_phase_diagnostic'][arm]['maximum_unclipped_absolute_phase_s'] ==
                 max(map(abs, parent['policy_arms'][arm]['state']['phases'])))
    tests = read(here / 'test_receipt02.json')
    need('five_owned_fixtures_including_original_producer_prerequisite', tests['returncode'] == 0 and '5 passed' in tests['stdout'])
    baseline_protocol = read(LATER / 'baseline/later_protocol.json')
    need('all_failed_setup_and_successful_smoke_costs_charged',
         protocol['prior_failed_smoke_and_preparation_seconds'] >= first['seconds'] and
         abs(smoke['cumulative_baseline_preparation_seconds'] - (baseline_protocol['preparation_seconds'] +
             protocol['additional_preparation_seconds'] + smoke['seconds'])) < 1e-12 and
         smoke['cumulative_baseline_preparation_seconds'] <= 60)
    need('original_cumulative_cap_and_fixed_nomination_limits', protocol['original_baseline_cumulative_cap'] == 840 and
         protocol['maximum_nomination_seconds'] == 120 and protocol['workers'] == 1 and protocol['BLAS_threads'] == 1 and
         terminal['cumulative_worker_seconds'] + protocol['additional_preparation_seconds'] + smoke['seconds'] + 120 <= 840)
    need('unchanged_complete_owner_RF_rule', protocol['whole_curved_owner_minimum_points'] == 20 and
         protocol['no_fallback_family_or_owner'] and protocol['no_IQ_detector_correction_position_fit_or_GPS'] and
         protocol['producer_prerequisite'] == 'exact pair_passes(include_linear=True); absolute phases diagnostic only')
    need('no_nomination_scores_already_terminal', not (here / 'RF_seal.json').exists() and not (here / 'summary.json').exists())
    result = dict(all_passed=all(c['passed'] for c in checks), checks=checks,
        checks_passed=sum(c['passed'] for c in checks), binding_errors=errors,
        protocol_sha256=sha(protocol_path), baseline_RF_seal_sha256=sha(baseline_seal),
        source_bindings_verified=len(protocol['source_bindings']),
        static_review=dict(original_influence_rule_has_no_r_valid_prerequisite=True,
            versioned_fidelity_repair_before_any_scores_or_geography=True,
            phase15_overrun_retained_as_diagnostic_not_hidden=True,
            no_engine_context_or_optimizer_calls=True,
            same_shared_curved_and_predictive_information_and_susceptibility=True,
            original_selector_quartile_and_deterministic_ties_preserved=True,
            native_winner_CFO_margin_and_window_counter_reconciled=True,
            paired_receiver_windows_deduplicated_not_extra_independent_evidence=True),
        evaluator_source_review=dict(source_sha256=sha(ROOT / 'evaluate_later.py'),
            expected_sha256='d3ba288f57636c37f6594266df0d64b350e69ac05d544421b234a4481cdcafb7',
            fixed_four_denominator_and_phase_diagnostic_retained=True,
            separate_exact_RF_seals_terminal_audits_and_root_geographic_release_required=True),
        scope='RF-only complete-owner nomination for all four producer-complete parents; no physical phase qualification, CFO correction or position-policy adoption',
        numerical_seconds=time.monotonic()-began, detector_optimizer_geometry_or_IQ_calls=0,
        files={str(p):sha(p) for p in [protocol_path, here / 'nominate02.py', here / 'actual_smoke02.json',
               here / 'FIDELITY_ADDENDUM02.md', baseline_seal, ROOT / 'evaluate_later.py']})
    output = ROOT / 'audit/nomination_preflight.json'
    if output.exists():
        raise ValueError('preserve existing receipt rather than overwrite')
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(output), all_passed=result['all_passed'], checks_passed=result['checks_passed'],
                         checks=len(checks), numerical_seconds=result['numerical_seconds'])))


def nomination_terminal():
    import math
    began = time.monotonic()
    here = LATER / 'baseline/nomination'
    protocol_path = here / 'protocol02.json'
    protocol = read(protocol_path)
    seal_path = here / 'RF_seal.json'
    seal = read(seal_path)
    summary = read(here / 'summary.json')
    baseline_seal = LATER / 'baseline/later_RF_seal.json'
    errors = bindings(seal['files']) + bindings(protocol['source_bindings']) + bindings(read(baseline_seal)['files'])
    checks = []
    def need(name, passed):
        checks.append(dict(check=name, passed=bool(passed)))
    need('all_nomination_source_and_sealed_parent_bindings_exact', not errors)
    need('exact_final_protocol_parent_and_root_GO', seal['protocol_sha256'] == sha(protocol_path) ==
         read(ROOT / 'nomination_go.json')['protocol_sha256'] and
         seal['baseline_RF_seal_sha256'] == summary['baseline_RF_seal_sha256'] == sha(baseline_seal) ==
         read(ROOT / 'nomination_go.json')['baseline_RF_seal_sha256'] and read(ROOT / 'nomination_go.json')['approved'])
    need('all_four_terminal_slots_no_substitution', summary['all4_slots_terminal'] and
         [r['case'] for r in summary['rows']] == protocol['cases'])
    baseline_execution = read(LATER / 'baseline/later_execution.json')
    smoke = read(here / 'actual_smoke02.json')
    need('all_preparation_and_run_costs_within_original_baseline_cap',
         abs(summary['cumulative_baseline_seconds'] - (baseline_execution['cumulative_worker_seconds'] +
             protocol['additional_preparation_seconds'] + smoke['seconds'] + summary['run_seconds'])) < 1e-10 and
         summary['cumulative_baseline_seconds'] <= 840 and summary['run_seconds'] <= 120)
    allrequests = read(here / 'complete_requests.json')
    per_case = []
    for outcome in summary['rows']:
        case = outcome['case']
        directory = here / case
        need(case + '_saved_result_equals_terminal_summary', read(directory / 'result.json') == outcome)
        if outcome['status'] != 'complete':
            per_case.append(dict(case=case,status=outcome['status'],selected=False))
            continue
        selection = read(directory / 'selection.json')
        ownership = read(directory / 'ownership.json')
        families, owners = selection['families'], selection['owners']
        ranked = sorted((f for f in families if f['has_eligible_owner']), key=lambda f:(-f['paired_score'],f['family']))
        target = min((o for o in owners if o['eligible'] and o['family'] == ranked[0]['family']),
                     key=lambda o:(-o['paired_score'],o['owner'])) if ranked else None
        low = sorted((f for f in ranked if f['family'] != target['family'] and f['paired_score'] > 0),
                     key=lambda f:(f['paired_score'],f['family']))[:max(1,math.ceil(len(ranked)/4))] if target else []
        scores = {f['family']:f['paired_score'] for f in low}
        controls = sorted((o for o in owners if o['eligible'] and o['family'] in scores),
                          key=lambda o:(o['receiver'] == target['receiver'],scores[o['family']],o['paired_score'],o['owner']))
        control = controls[0] if controls else None
        need(case + '_original_selection_independently_recomputed', selection['target'] == target and
             selection['control'] == control and outcome['target'] == (target['owner'] if target else None) and
             outcome['control'] == (control['owner'] if control else None))
        need(case + '_paired_scores_exact', all(f['paired_score'] == min(f['arms'].values()) for f in families) and
             all(o['paired_score'] == min(o['arms'].values()) for o in owners if o['eligible']))
        cov = ownership['coverage']
        for owner in owners:
            ids = set(owner['observation_ids'])
            eligible = len(owner['observation_ids']) >= 20 and all(ids <= set(cov[a]['curved_observation_ids']) for a in ['c0','fitted_c'])
            need(case + '_' + owner['owner'] + '_complete_owner_eligibility',
                 len(ids) == len(owner['observation_ids']) and owner['eligible'] == eligible)
        requests = read(directory / 'complete_requests.json')
        selected_ids = [oid for owner in (target,control) if owner for oid in owner['observation_ids']]
        need(case + '_all_selected_native_IDs_once', sorted(r['native_observation_id'] for r in requests) == sorted(selected_ids) and
             len(selected_ids) == len(set(selected_ids)) and len(requests) == outcome['native_receiver_windows'])
        original = read(LATER / 'baseline/work' / case / 'observations.json')
        obs = {o['observation_id']:o for o in original}
        tracking = read(LATER / 'baseline/work' / case / 'tracking.json')
        source = tracking['source']; fs = source['sample_rate_hz']; origin = tracking['clock_anchor']['sample_counter']
        for request in requests:
            oid = request['native_observation_id']; o = obs[oid]
            probe = request['probe']
            matches = [p for p in source['probes'] if p['receiver_id'] == o['native_receiver_id'] and
                p['channel'] == o['channel'] and abs((p['valid_start_counter']-origin)/fs +
                p['probe_start_ms']/1000 + source['probe_ms']/2000-o['time_s']) < 1e-8]
            need(case + '_' + oid + '_unique_original_probe', len(matches) == 1)
            if len(matches) != 1:
                continue
            p = matches[0]
            passing = [c for c in p['candidates'] if c['passed_fractional_margin_gate']]
            winner = max(passing,key=lambda c:(c['fractional_margin'],-c['candidate_rank'])) if passing else None
            need(case + '_' + oid + '_exact_winner_and_CFO_gauge', winner is not None and
                 winner == request['original_candidate'] and winner['fractional_tracking_cfo_hz'] == o['measured_cfo_hz'] and
                 winner['fractional_margin'] == o['fractional_margin'] and request['original_observation'] == o and
                 request['acquired_cfo_hz'] is None and request['receiver_id'] == o['native_receiver_id'])
            need(case + '_' + oid + '_physical_window_counter_identity',
                 probe['window_start_counter'] == p['valid_start_counter'] + round(p['probe_start_ms']*fs/1000) and
                 request['duration_samples'] == round(source['probe_ms']*fs/1000) and
                 request['physical_probe_key'] == [request['recording_id'],request['source_session_id'],
                    p['visit_index'],p['probe_index'],p['channel'],probe['window_start_counter'],
                    request['duration_samples'],float(p['actual_rf_hz'])])
        need(case + '_phase_diagnostic_preserved', outcome['absolute_phase_diagnostic'] ==
             ownership['absolute_phase_diagnostic'] == next(r for r in smoke['rows'] if r['case'] == case)['absolute_phase_diagnostic'])
        parent_checks = read(directory / 'checks.json')
        need(case + '_shared_parent_replay_and_derivative_checks', len(parent_checks) == 2 and all(
             abs(c['parent_objective_difference']) <= 1e-3 and c['derivative_error'] <= 1e-5 and
             c['Schur_replay_max_error'] <= 1e-5 for c in parent_checks))
        per_case.append(dict(case=case,status=outcome['status'],target=outcome['target'],control=outcome['control'],
                             selected_native_IDs=len(selected_ids),deduplicated_physical_probes=outcome['deduplicated_physical_probes']))
    concatenated = [r for outcome in summary['rows'] if outcome['status'] == 'complete'
                    for r in read(here / outcome['case'] / 'complete_requests.json')]
    need('aggregate_request_ledger_and_physical_dedup_exact', concatenated == allrequests and
         len(allrequests) == summary['selected_native_receiver_windows'] and
         len({tuple(r['physical_probe_key']) for r in allrequests}) == summary['deduplicated_physical_probes'])
    result = dict(all_passed=all(c['passed'] for c in checks),checks=checks,
        checks_passed=sum(c['passed'] for c in checks),binding_errors=errors,
        protocol_sha256=sha(protocol_path),baseline_RF_seal_sha256=sha(baseline_seal),
        nomination_RF_seal_sha256=sha(seal_path),all_four_slots_preserved=True,per_case=per_case,
        cumulative_baseline_seconds=summary['cumulative_baseline_seconds'],
        scope='RF-only frozen complete owners; no new CFO corrections, position fits, raw payload reads or geographic selection',
        phase_overrun_is_diagnostic_not_an_extra_nomination_gate=True,
        numerical_seconds=time.monotonic()-began,detector_optimizer_geometry_or_IQ_calls=0,
        files={str(p):sha(p) for p in [protocol_path,seal_path,here/'summary.json',here/'complete_requests.json',
               ROOT/'audit/nomination_preflight.json',ROOT/'evaluate_later.py']})
    output = ROOT/'audit/nomination_terminal.json'
    if output.exists():raise ValueError('preserve existing receipt rather than overwrite')
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(output),all_passed=result['all_passed'],checks_passed=result['checks_passed'],
                         checks=len(checks),numerical_seconds=result['numerical_seconds'])))


def later_geographic_readback():
    import math
    import numpy as np
    began=time.monotonic()
    out=ROOT/'later_geographic'
    summary=read(out/'summary.json')
    seal_path=out/'seal.json'
    go=read(ROOT/'later_geography_go.json')
    checks=[]
    def need(name,passed):checks.append(dict(check=name,passed=bool(passed)))
    errors=bindings(read(seal_path)['files'])
    need('saved_evaluator_and_geographic_bindings_exact',not errors and sha(ROOT/'evaluate_later.py')==
         go['evaluator_sha256']=='d3ba288f57636c37f6594266df0d64b350e69ac05d544421b234a4481cdcafb7')
    need('exact_terminal_RF_release_before_geography',go['authorized'] and
         go['baseline_RF_seal_sha256']==read(ROOT/'audit/baseline_terminal.json')['baseline_RF_seal_sha256'] and
         go['nomination_RF_seal_sha256']==read(ROOT/'audit/nomination_terminal.json')['nomination_RF_seal_sha256'])
    need('eight_rows_all_four_matched_arms',len(summary['rows'])==8 and
         {(r['case'],r['arm'])for r in summary['rows']}=={('LATER4-%04d'%i,a)for i in range(1,5)for a in ['c0','fitted_c']})
    reference=summary['reference_latlon']
    def unit(ll):
        lat,lon=map(math.radians,ll)
        return np.array([math.cos(lat)*math.cos(lon),math.cos(lat)*math.sin(lon),math.sin(lat)])
    def distance(x):
        ll=[37.906+x[1]/111.,-122.545+x[0]/(111.32*math.cos(math.radians(37.906)))]
        a,b=unit(ll),unit(reference)
        return 6371.0088*math.atan2(np.linalg.norm(np.cross(a,b)),float(a@b))
    maximum=0.
    for row in summary['rows']:
        case,arm=row['case'],row['arm']
        p=read(LATER/'baseline/work/family_cavity/position'/(case+'.json'))['policy_arms'][arm]
        own=read(LATER/'baseline/nomination'/case/'ownership.json')['coverage'][arm]
        delta=abs(distance(p['endpoint_east_north_km'])-row['position_error_km']);maximum=max(maximum,delta)
        need(case+'_'+arm+'_exact_RF_endpoint_and_independent_distance',delta<1e-8 and
             [row['east_km'],row['north_km']]==p['endpoint_east_north_km'])
        need(case+'_'+arm+'_native_coverage_roles_exact',row['associated_points']==own['associated'] and
             row['associated_percent']==own['percent'] and row['likelihood_points']==own['likelihood_points'] and
             row['likelihood_percent']==own['likelihood_percent'] and row['GLRT_points']==own['total_GLRT'] and
             abs(100*row['likelihood_points']/row['GLRT_points']-row['likelihood_percent'])<1e-12)
    for arm in ['c0','fitted_c']:
        values=[r['position_error_km']for r in summary['rows']if r['arm']==arm]
        stats=summary['statistics'][arm]
        need(arm+'_all_four_summary_arithmetic',stats['successes']==stats['attempted']==4 and
             abs(stats['mean_km']-float(np.mean(values)))<1e-14 and
             abs(stats['median_km']-float(np.median(values)))<1e-14 and stats['max_km']==max(values))
    need('no_correction_or_new_fit_claim',summary['no_CFO_correction'] and summary['new_fits']==0 and
         summary['not_an_untouched_holdout'])
    result=dict(all_passed=all(c['passed']for c in checks),checks=checks,checks_passed=sum(c['passed']for c in checks),
        binding_errors=errors,rows_checked=8,maximum_independent_distance_error_km=maximum,
        statistics=summary['statistics'],root_release='saved exact evaluator/terminal-seal GO; root confirmed evaluator exit0',
        scope='later baseline position and coverage only; no refined-CFO results or transfer gains',
        numerical_seconds=time.monotonic()-began,new_fits_or_geometry=0,
        files={str(p):sha(p)for p in [seal_path,out/'summary.json',ROOT/'evaluate_later.py',ROOT/'later_geography_go.json']})
    target=ROOT/'audit/later_geographic_readback.json'
    if target.exists():raise ValueError('preserve existing receipt rather than overwrite')
    target.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(target),all_passed=result['all_passed'],checks_passed=result['checks_passed'],
                         checks=len(checks),maximum_error_km=maximum,numerical_seconds=result['numerical_seconds'])))


def frequency_readback():
    import math
    began=time.monotonic()
    here=LATER/'baseline'
    path=here/'frequency_readback.json'
    data=read(path)
    checks=[]
    def need(name,passed):checks.append(dict(check=name,passed=bool(passed)))
    need('same_terminal_baseline_and_source_helpers',data['baseline_RF_seal_sha256']==sha(here/'later_RF_seal.json') and
         data['source_helper_sha256']==sha(data['source_helper']) and
         data['predictive_source_helper_sha256']==sha(data['predictive_source_helper']))
    need('all_eight_case_arm_rows',len(data['rows'])==8 and
         len({(r['case'],r['arm'])for r in data['rows']})==8)
    for row in data['rows']:
        parent=read(row['source_parent_path'])
        p=parent['policy_arms'][row['arm']]
        entries=parent['selected']['entries']if parent['accepted']else parent['baseline_entries']
        need(row['case']+'_'+row['arm']+'_saved_curved_RMS_and_predictive_counts_exact',
             sha(row['source_parent_path'])==row['source_parent_sha256'] and
             p['RMS_hz']==row['saved_curved_conditional_RMS_hz'] and
             p['active_points']==row['active_curved_points'] and
             sum(len(e['observation_ids'])for e in entries)==row['predictive_points'] and
             p['negative_twice_elbo']==row['full_VI_objective'] and
             p['curved_negative_twice_elbo']==row['curved_VI_objective'] and
             row['full_likelihood_frequency_RMS_hz']is None)
    for arm in ['c0','fitted_c']:
        rows=[r for r in data['rows']if r['arm']==arm]
        count=sum(r['active_curved_points']for r in rows)
        mean=sum(r['saved_curved_conditional_RMS_hz']for r in rows)/4
        pooled=math.sqrt(sum(r['active_curved_points']*r['saved_curved_conditional_RMS_hz']**2 for r in rows)/count)
        s=data['summary'][arm]
        need(arm+'_independent_curved_only_aggregation',count==s['active_curved_points']==10514 and
             sum(r['predictive_points']for r in rows)==s['predictive_points']==1328 and
             mean==s['mean_scan_curved_conditional_RMS_hz'] and pooled==s['pooled_curved_conditional_RMS_hz'])
    selected=read(here/'nomination/LATER4-0004/selection.json')['target']
    need('flagged_0004_target_metadata_retained',selected['quality_status']=='structure_flagged')
    result=dict(all_passed=all(c['passed']for c in checks),checks=checks,checks_passed=sum(c['passed']for c in checks),
        source_review='Both bound summary helpers compute sqrt(mean(conditional_residual_hz[keep]**2)); aggregation is curved-only, not a profiled/predictive or weighted likelihood RMS.',
        no_new_residual_reconstruction_or_geometry=True,numerical_seconds=time.monotonic()-began,
        files={str(p):sha(p)for p in [path,here/'frequency_readback.py',Path(data['source_helper']),Path(data['predictive_source_helper'])]})
    target=ROOT/'audit/frequency_readback.json'
    if target.exists():raise ValueError('preserve existing receipt rather than overwrite')
    target.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(target),all_passed=result['all_passed'],checks_passed=result['checks_passed'],
                         checks=len(checks),numerical_seconds=result['numerical_seconds'])))


def final_seal():
    import importlib.util
    began=time.monotonic()
    receipts=['preparation_preflight.json','preparation_terminal.json','mechanism_preflight.json',
              'mechanism_terminal.json','geographic_readback.json','baseline_preflight.json','baseline_terminal.json',
              'nomination_preflight02.json','nomination_terminal.json','later_geographic_readback.json','frequency_readback.json']
    docs=[read(ROOT/'audit'/name)for name in receipts]
    if not all(d['all_passed']for d in docs):raise ValueError('required independent receipt failed')
    if (ROOT/'audit/nomination_preflight02.json').read_bytes()!=(ROOT/'audit/nomination_preflight.json').read_bytes():
        raise ValueError('canonical nomination gate differs from versioned PASS')
    path=ROOT/'publication/stage_report.py'
    spec=importlib.util.spec_from_file_location('publication_selection_only',path)
    stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
    mechanism=stage.manifest_paths(ROOT/'mechanism/lean_publication.json')
    baseline=stage.manifest_paths(LATER/'baseline/lean_publication.json')
    selected=set()
    for p in ROOT.rglob('*'):
        rel=p.relative_to(ROOT)
        if not p.is_file()or stage.SKIP.intersection(rel.parts):continue
        if p.name in {'publication_receipt.json','publication_checks.json','final_seal.json'}:continue
        include=p.resolve()in mechanism if rel.parts[0]=='mechanism'else p.suffix!='.npz'and p.stat().st_size<=stage.LIMIT
        if include:selected.add(p)
    selected.add(path)
    for branch in ['readiness','prepared','baseline']:
        base=LATER/branch
        for p in base.rglob('*'):
            rel=p.relative_to(base)
            if not p.is_file()or stage.SKIP.intersection(rel.parts):continue
            if branch=='readiness':include=p.suffix!='.npz'and p.stat().st_size<=stage.LIMIT
            elif branch=='prepared':include=((len(rel.parts)==1 and p.suffix in {'.json','.md','.stdout','.stderr'})or
                                            stage.case_receipt(rel))and p.stat().st_size<=stage.LIMIT
            else:include=p.resolve()in baseline
            if include:selected.add(p)
    required=[ROOT/'README.md',ROOT/'NEXT_EXPERIMENT.md',ROOT/'COORDINATOR_PLAN.md',ROOT/'EVALUATION_AUTHORITY.md',
              ROOT/'mechanism/lean_publication.json',LATER/'baseline/lean_publication.json',ROOT/'evaluate_later.py',path,
              ROOT/'audit/FINDINGS.md',Path(__file__)]
    if not all(p in selected for p in required):raise ValueError('final scientific/report source missing from package selection')
    hash_errors=[]
    for d in docs:hash_errors+=bindings(d.get('files',{}))
    if hash_errors:raise ValueError('audited artifact changed: '+str(hash_errors))
    diff=subprocess.check_output(['git','diff','--binary'],cwd=REPO)
    if hashlib.sha256(diff).hexdigest()!=DIRTY_SHA:raise ValueError('unrelated tracked diff changed')
    # The source review and all saved arithmetic above are independent of this packaging seal.
    # Exclude the seal itself, caches and future publication receipts from the hash closure.
    result=dict(all_passed=True,passed_receipts=len(receipts),receipt_names=receipts,
        files={str(p):sha(p)for p in sorted(selected)},
        source_claim_review=dict(all_four_baselines_and_RF_owner_choices_sealed_before_geography=True,
            baseline_errors_not_CFO_transfer_gains=True,noise_block_effect_not_physical_uncertainty_validation=True,
            absolute_phase_overrun_and_structure_flagged_owner_preserved=True,
            original_conditional_objective_distinct_from_VI=True,
            frequency_RMS_curved_only_and_postfit_coverage_distinct_from_likelihood=True,
            NEXT_EXPERIMENT_is_recommendation_not_execution=True),
        root_tracked_diff_sha256=DIRTY_SHA,
        audit_seconds=sum(d.get('numerical_seconds',0.)for d in docs)+1.0+time.monotonic()-began,
        preserved_failed_receipts=['mechanism_terminal_attempt01.json','nomination_preflight01_failed.json'],
        no_new_detector_optimizer_geometry_or_IQ_calls=True)
    output=ROOT/'audit/final_seal.json'
    if output.exists():raise ValueError('preserve existing final seal rather than overwrite')
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(output),all_passed=True,passed_receipts=len(receipts),bound_files=len(selected),
                         sha256=sha(output),audit_seconds=result['audit_seconds'])))


if __name__ == '__main__':
    {'preparation_preflight': preparation_preflight,
     'mechanism_preflight': mechanism_preflight,
     'preparation_terminal': preparation_terminal,
     'baseline_preflight': baseline_preflight,
     'mechanism_terminal': mechanism_terminal,
     'geographic_readback': geographic_readback,
     'baseline_terminal': baseline_terminal,
     'nomination_preflight': nomination_preflight,
     'nomination_terminal': nomination_terminal,
     'later_geographic_readback': later_geographic_readback,
     'frequency_readback': frequency_readback,
     'final_seal': final_seal}[sys.argv[1]]()
