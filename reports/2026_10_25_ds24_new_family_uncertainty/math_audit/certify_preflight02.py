"""Bind completed independent mathematical checks to the final execution freeze.

This script reads existing fixed-position audit evidence; it never fits positions.
"""

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path('/srv/bulk/leo/research/ds24-uncertain-new-family-r01')
HERE = ROOT / 'math_audit'
PROTOCOL = ROOT / 'scientific/protocol03.json'
EXPECTED = 'b57bba7dab4616866354b185cf6d6415ace6ba513da906f74e082b7b496ee137'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def main():
    assert digest(PROTOCOL) == EXPECTED
    protocol = read(PROTOCOL)
    audit = read(HERE / 'quadrature02b_audit.json')
    assert audit['status'] == 'pass'
    assert audit['position_fits'] == 0 and audit['GPS_used'] is False
    assert audit['fixed_global_orders_passing'] == [1281]
    assert audit['point_rows'] == 160
    assert protocol['fixed_common_phase_nodes'] == 1281
    assert protocol['maximum_position_fits'] == 8
    assert protocol['maximum_profile_branch_evaluations'] == 88
    assert protocol['per_arm_seconds'] == 180 and protocol['global_seconds'] == 1200
    assert protocol['numerical_workers'] == 2 and protocol['BLAS_threads_per_worker'] == 1
    assert protocol['no_GPS'] and protocol['RF_seal_precedes_GPS']
    assert protocol['operational_policy'] == 'saved_baseline for every outcome'
    endpoint = protocol['endpoint_numerical_qualification']
    assert endpoint['final_parent_phase_reference'] and endpoint['center_and_axis_offsets'] == 5
    assert endpoint['frozen_nodes'] == 1281 and endpoint['strictly_denser_nodes'] == 2561
    assert endpoint['score_absolute_tolerance'] == audit['score_tolerance'] == .001
    assert endpoint['gradient_absolute_tolerance_per_km'] == audit['gradient_tolerance_objective_per_km'] == .001
    assert endpoint['central_difference_step_km'] == audit['finite_difference_step_km'] == .01
    for path, expected in protocol['source_sha256'].items():
        assert digest(path) == expected, path
    for path, expected in audit['scientific_sources'].items():
        assert protocol['source_sha256'][path] == digest(path) == expected, path

    points = sorted((HERE / 'quadrature02b_points').glob('*.json'))
    assert len(points) == 160
    rows = [read(path) for path in points]
    centers = [next(v for v in row['orders'] if v['order'] == 1281)
               for row in audit['center_rows']]
    assert len(centers) == 32 and all(row['passes'] for row in centers)
    assert all(not row['adaptive_reference']['integrator_messages'] for row in rows)
    dense = [row['dense_node_audit'] for row in rows if row['dense_node_audit']]
    assert len(dense) == 32
    assert all(row['nonlinear_target_redaction_parent_invariant'] for row in dense)
    selected_mass = [abs(row['quadrature_prior_mass'] - 1)
                     for row in audit['prior_mass_rows'] if row['order'] == 1281]
    assert max(selected_mass) <= 1e-8
    sys.path.insert(0, str(ROOT / 'scientific'))
    import execution03
    execution03.verify(require_go=False)

    evidence = [HERE / name for name in ('gaussian_oracle.py', 'test_gaussian_oracle.py',
        'actual_gaussian_audit.json', 'phase_linearization.json', 'phase_domain.json',
        'quadrature02_audit.json', 'audit_quadrature02b.py', 'quadrature02b_audit.json')]
    receipt = dict(all_passed=True, execution_protocol_sha256=EXPECTED,
        execution_protocol_path=str(PROTOCOL), audit_scope='independent conditional covariance, normalized conditioned phase mixture, fixed-position score and derivative convergence',
        launch_scope='bounded protocol03 diagnostic run only; endpoint qualification and separate contract audit/coordinator go required',
        fixed_global_phase_nodes=1281, fixed_probe_rows=160, derivative_centers=32,
        direct_dense_contexts=16, direct_dense_branch_rows=32, prior_mass_error_max=max(selected_mass),
        max_score_error_vs_independent_adaptive=max(abs(row['fixed_order_scores']['1281'] - row['adaptive_reference']['objective']) for row in rows),
        max_adaptive_nll_error_bound=max(row['adaptive_reference']['absolute_nll_error_bound'] for row in rows),
        max_gradient_error_per_km=max(row['gradient_error'] for row in centers),
        max_reference_gradient_error_bound_per_km=max(row['reference_gradient_error_bound'] for row in centers),
        max_dense_node_score_difference=audit['max_dense_node_difference'],
        minimum_checked_elevation_deg=audit['minimum_visibility_deg'],
        maximum_detected_phase_integrand_modes=max(len(row['adaptive_reference']['refined_phase_peaks_s']) for row in rows),
        independent_numerical_audit_seconds=audit['elapsed_seconds'],
        tests=dict(independent_gaussian_oracles=4, execution03_regression_tests=7, all_passed=True),
        position_fits=0, GPS_used=False,
        retained_limitations=['domain conditioning alters the original Student prior moments and removes prior mass',
            'parent calibration remains conditional variational/Gaussian inference',
            'physical shape modes remain a first-order covariance model',
            'fixed-state convergence does not establish endpoint convergence; final-reference checks are mandatory',
            'target association and any new diagnostic position remain unqualified; baseline is operational'],
        evidence_sha256={str(path): digest(path) for path in evidence},
        point_artifacts_sha256={str(path): digest(path) for path in points},
        certificate_source_sha256=digest(__file__))
    out = HERE / 'preflight02.json'
    with out.open('x') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    print(out, digest(out))


if __name__ == '__main__':
    main()
