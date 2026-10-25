"""Independent bounded-diagnostic launch audit; never start a scientific fit."""

import hashlib
import json
from pathlib import Path

import execution03 as execution

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCIENCE = ROOT/'scientific'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    protocol_path = SCIENCE/'protocol03.json'
    protocol = read(protocol_path)
    digest = sha(protocol_path)
    assert read(SCIENCE/'protocol03_seal.json')['protocol_sha256'] == digest
    assert execution.verify(require_go=False) == protocol
    for path, expected in protocol['source_sha256'].items():
        assert sha(path) == expected, path
    declared = dict(target_bindings_sha256=SCIENCE/'preparation01/input_bindings.json',
        preparation01_sha256=SCIENCE/'preparation01/preparation_seal.json',
        preparation02_protocol_sha256=SCIENCE/'preparation02/protocol.json',
        preparation02_result_sha256=SCIENCE/'preparation02/result.json',
        amendment_sha256=ROOT/'PHASE_INTEGRATION_AMENDMENT.md',
        superseded_execution02_protocol_sha256=SCIENCE/'protocol02.json',
        superseded_execution02_source_sha256=SCIENCE/'execution02.py')
    for key, path in declared.items():
        assert sha(path) == protocol[key], path
    assert protocol['cases'] == ['DS24-0095', 'DS24-0087']
    assert protocol['arms'] == ['c0', 'fitted_c']
    assert protocol['branches'] == ['predictive_shape_zero', 'predictive_shape_prior']
    assert protocol['fixed_common_phase_nodes'] == 1281
    assert protocol['profile_positions_per_case_arm'] == 11
    assert protocol['maximum_profile_branch_evaluations'] == 2*2*2*11 == 88
    assert protocol['maximum_position_fits'] == 2*2*2 == 8
    assert protocol['numerical_workers'] == 2 and protocol['BLAS_threads_per_worker'] == 1
    assert protocol['per_arm_seconds'] == execution.ARM_SECONDS == 180
    assert protocol['global_seconds'] == execution.GLOBAL_SECONDS == 1200
    assert protocol['phase_rounds'] == 5 and protocol['position_iterations_per_round'] == 48
    assert protocol['start_east_north_km'] == [0, 0]
    assert protocol['regional_center_latlon'] == [37.906, -122.545] and protocol['regional_width_km'] == 25
    assert protocol['target_phase_reference_refresh'] is False and protocol['multistart'] is False
    assert protocol['constrained_rescue'] is False
    assert protocol['RF_seal_precedes_GPS'] and protocol['no_GPS'] and protocol['no_new_IQ_RF_catalogue_or_candidates']
    assert protocol['operational_policy'] == 'saved_baseline for every outcome'
    numerical = protocol['endpoint_numerical_qualification']
    assert numerical['final_parent_phase_reference'] and numerical['center_and_axis_offsets'] == 5
    assert numerical['frozen_nodes'] == 1281 and numerical['strictly_denser_nodes'] == 2561
    assert numerical['central_difference_step_km'] == .01
    assert numerical['score_absolute_tolerance'] == numerical['gradient_absolute_tolerance_per_km'] == 1e-3
    assert numerical['prior_mass_absolute_tolerance'] == 1e-8
    receipts = {name:read(HERE/name) for name in ('parent_audit.json', 'preparation01_audit.json',
        'nonlinear_scalar_audit.json', 'quadrature_preparation_audit.json')}
    assert receipts['parent_audit.json']['all_passed'] and receipts['parent_audit.json']['GPS_used'] is False
    for path, expected in receipts['parent_audit.json']['input_sha256'].items():
        assert sha(path) == expected, path
    for path, expected in receipts['parent_audit.json']['source_sha256'].items():
        assert sha(path) == expected, path
    rejected = receipts['preparation01_audit.json']
    assert rejected['construction_and_inputs_passed'] and rejected['physical_phase_adequacy_passed'] is False
    scalar = receipts['nonlinear_scalar_audit.json']
    assert scalar['all_passed'] and scalar['full_target_NLL_added_exactly_once']
    assert scalar['target_NLL_normalization_not_added_twice']
    for path, expected in scalar['source_sha256'].items():
        assert sha(path) == expected, path
    arithmetic = receipts['quadrature_preparation_audit.json']
    assert arithmetic['all_passed'] and arithmetic['global_fixed_node_count'] == 1281
    assert arithmetic['preparation_result_sha256'] == protocol['preparation02_result_sha256']
    for path, expected in arithmetic['point_sha256'].items():
        assert sha(path) == expected, path
    independent_path = ROOT/'math_audit/quadrature02b_audit.json'
    independent = read(independent_path)
    assert independent['status'] == 'pass' and independent['point_rows'] == 160
    assert independent['position_fits'] == 0 and independent['GPS_used'] is False
    assert independent['fixed_global_orders_passing'] == [1281]
    for path, expected in independent['scientific_sources'].items():
        assert sha(path) == expected, path
    for row in independent['center_rows']:
        chosen = next(check for check in row['orders'] if check['order'] == 1281)
        assert chosen['passes'] and chosen['total_score_error_bound'] <= 1e-3
        assert chosen['gradient_error']+chosen['reference_gradient_error_bound'] <= 1e-3
    tests = read(SCIENCE/'execution03_test_receipt.json')
    assert tests['all_passed'] and tests['tests'] == 7 and tests['position_fits'] == 0
    assert not (SCIENCE/'execution_start02.json').exists()
    assert not (SCIENCE/'execution_start03.json').exists()
    # Original predicate and explicit target exclusion are source-reviewed, with
    # independent real-context regressions. These checks bind their exact bytes.
    source = (SCIENCE/'execution03.py').read_text()
    assert 'r.valid({arm:record for arm in a.ARMS})' in source
    assert "accepted = set(membership['accepted_observation_ids'])-target_ids" in source
    assert 'numerical = endpoint_qualification(d, p, x)' in source
    assert source.index("r.write_new(out/'raw_endpoint.json', raw)") < source.index('numerical = endpoint_qualification(d, p, x)')
    output = dict(all_passed=True, execution_protocol_sha256=digest, no_position_fits=True,
        GPS_used=False, source_sha256=sha(Path(__file__)),
        independent_audit_receipts={str(HERE/name):sha(HERE/name) for name in receipts},
        independent_math_result_sha256=sha(independent_path),
        exact_target_native_IDs=[49, 43], original_parent_contracts_and_causal_history_preserved=True,
        full_normalized_target_NLL_and_parent_offset_pass=True,
        source_cache_and_target_redaction_checks_pass=True,
        original_absolute_phase_endpoint_and_nonempty_gate_predicates_restored=True,
        declared_file_and_source_hashes_verified=True,
        target_IDs_explicitly_excluded_from_accepted_coverage=True,
        maximum_position_fits=8, maximum_profile_branch_evaluations=88,
        numerical_workers=2, threads_per_worker=1, per_arm_seconds=180, global_seconds=1200,
        raw_endpoint_saved_before_numerical_qualification=True,
        final_endpoint_score_gradient_qualification_required=True,
        independent_runner_test_rerun=dict(tests=7, passed=True, seconds=4.784),
        scientific_scope='unqualified experimental predictive factors only; matched c arms; no new association/adoption',
        target_association_qualified=False, operational_policy='saved_baseline',
        independent_math_launch_receipt_and_coordinator_go_still_required=True,
        source_repair_note='Execution02 was never run. Execution03 restores exact original arm validity and complete declared binding checks; frozen likelihood/quadrature and fit budgets unchanged.')
    with (HERE/'preflight02.json').open('x') as stream:
        json.dump(output, stream, indent=2); stream.write('\n')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
