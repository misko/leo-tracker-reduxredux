"""Independent final-reference quadrature and dense-node audit; no refits/GPS."""

import hashlib
import json
from pathlib import Path
import signal
import sys
import time

import numpy as np
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'scientific'))
import adapter as a
import execution03 as execution
import quadrature02 as q
from audit_quadrature02b import adaptive_integral, dense_node_check, write_new

PROTOCOL_SHA = 'b57bba7dab4616866354b185cf6d6415ace6ba513da906f74e082b7b496ee137'
SEAL_SHA = '642c438662bdb23503ce6aa1cc9adc33f6a0394ec8b0aa7c49fc5b95f73e7142'
H = .01


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scalar_decomposition(record):
    target = record['target_conditional']
    weights = np.asarray(target['phase_posterior_weights'])
    logprior = np.asarray(target['phase_log_prior_weights'])
    loglike = np.asarray(target['node_log_density'])
    quadratic = np.asarray(target['node_quadratic'])
    logdet = np.asarray(target['node_logdet'])
    logz = float(logsumexp(logprior + loglike))
    posterior = np.exp(logprior + loglike - logz)
    n = len(record['target_observation_ids'])
    normalization = n * np.log(2 * np.pi)
    positive = weights > 0
    kl = 2 * np.sum(weights[positive] * (np.log(weights[positive]) - logprior[positive]))
    expected = dict(quadratic=float(weights @ quadratic), logdet=float(weights @ logdet),
                    normalization=float(normalization))
    score = -2 * logz
    errors = [abs(score - target['objective']),
        abs(score - sum(expected.values()) - kl),
        abs(kl - target['phase_posterior_to_prior_quadrature_penalty']),
        abs(record['total_negative_twice_elbo'] - record['parent_negative_twice_elbo'] - score)]
    errors += [abs(expected[key] - target['expected_node_terms'][key]) for key in expected]
    assert max(errors) < 1e-6
    assert abs(weights.sum() - 1) < 1e-10
    assert np.max(abs(posterior - weights)) < 1e-10
    assert abs(np.exp(logsumexp(logprior)) - 1) < 1e-8
    return max(errors)


def gradient(records, rule):
    return np.array([(records[1][rule] - records[2][rule]) / (2 * H),
                     (records[3][rule] - records[4][rule]) / (2 * H)])


def main():
    began = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('240s fixed endpoint audit cap')))
    signal.alarm(240)
    seal_path = ROOT / 'scientific/RF_seal03.json'
    assert sha(seal_path) == SEAL_SHA
    seal = read(seal_path)
    assert seal['protocol_sha256'] == PROTOCOL_SHA
    assert sha(execution.PROTOCOL) == PROTOCOL_SHA
    execution.verify(require_go=True)
    assert seal['no_GPS'] and seal['all_attempts_terminal']
    for path, expected in seal['files'].items():
        assert sha(path) == expected, path
    profile_files = sorted((ROOT / 'scientific/profiles03').glob('*/*_predictive_shape_*.json'))
    endpoint_files = sorted((ROOT / 'scientific/fits03').glob('*/*/*/rf_diagnostics.json'))
    assert len(profile_files) == 88 and len(endpoint_files) == 8
    decomposition_max = max(scalar_decomposition(read(path)) for path in profile_files + endpoint_files)
    rows = []
    for case in a.CASES:
        d = a.load_context(case)
        for arm in a.ARMS:
            for branch in a.BRANCHES:
                directory = ROOT / 'scientific/fits03' / case / arm / branch
                raw = read(directory / 'raw_endpoint.json')
                diagnostics = read(directory / 'rf_diagnostics.json')
                saved = read(directory / 'endpoint_numerical_qualification.json')
                reference = np.asarray(raw['parent_phase_reference'])
                np.testing.assert_array_equal(reference, diagnostics['parent_phase_reference'])
                np.testing.assert_array_equal(reference, raw['history'][-1]['parent_phase_reference'])
                p = q.build(d, arm, reference, branch, 1281)
                x = np.asarray(raw['endpoint_east_north_km'])
                calculated = p.calculate(x)
                assert abs(calculated['negative_twice_elbo'] - raw['total_negative_twice_elbo']) < 1e-7
                assert abs(calculated['negative_twice_elbo'] - diagnostics['total_negative_twice_elbo']) < 1e-7
                points = [x, x + [H, 0], x - [H, 0], x + [0, H], x - [0, H]]
                records = []
                dense = None
                for index, point in enumerate(points):
                    np.testing.assert_array_equal(point, saved['records'][index]['position_east_north_km'])
                    components = q.conditional_components(d, p, point)
                    if index == 0:
                        dense = dense_node_check(d, p, point, components)
                    include_shape = branch == a.BRANCHES[1]
                    fixed = {str(count): q.integrate(d, components, count, include_shape)
                             for count in (1281, 2561)}
                    independent = adaptive_integral(d, components, include_shape)
                    for count, value in fixed.items():
                        assert abs(value['objective'] - saved['records'][index]['rules'][count]['objective']) < 1e-7
                    records.append(dict(position_east_north_km=point,
                        fixed1281=fixed['1281']['objective'], fixed2561=fixed['2561']['objective'],
                        independent=independent['objective'], independent_reference=independent,
                        saved_adaptive_objective=saved['records'][index]['adaptive']['objective'],
                        prior_mass_error=abs(fixed['1281']['quadrature_prior_mass'] - 1),
                        minimum_elevation_deg=min(fixed['1281']['minimum_node_elevation_deg'],
                            fixed['1281']['minimum_domain_endpoint_elevation_deg'])))
                gradients = {rule: gradient(records, rule) for rule in ('fixed1281', 'fixed2561', 'independent')}
                gradient_reference_bound = max((records[1]['independent_reference']['absolute_nll_error_bound']
                    + records[2]['independent_reference']['absolute_nll_error_bound']) / (2 * H),
                    (records[3]['independent_reference']['absolute_nll_error_bound']
                    + records[4]['independent_reference']['absolute_nll_error_bound']) / (2 * H))
                score_error_bound = max(abs(row['fixed1281'] - row['independent'])
                    + row['independent_reference']['absolute_nll_error_bound'] for row in records)
                gradient_error = float(np.max(abs(gradients['fixed1281'] - gradients['independent'])))
                dense_score_error = max(abs(row['fixed1281'] - row['fixed2561']) for row in records)
                dense_gradient_error = float(np.max(abs(gradients['fixed1281'] - gradients['fixed2561'])))
                passed = bool(score_error_bound <= .001 and gradient_error + gradient_reference_bound <= .001
                    and dense_score_error <= .001 and dense_gradient_error <= .001
                    and max(row['prior_mass_error'] for row in records) <= 1e-8
                    and min(row['minimum_elevation_deg'] for row in records) >= 0)
                assert passed and saved['passed']
                row = dict(case=case, arm=arm, branch=branch, all_passed=passed,
                    endpoint_east_north_km=x, final_actual_parent_phase_reference=reference,
                    point_records=records, gradients=gradients, independent_dense_node=dense,
                    maximum_score_error_with_reference_bound=score_error_bound,
                    maximum_gradient_error_per_km=gradient_error,
                    reference_gradient_error_bound_per_km=gradient_reference_bound,
                    maximum_score_error_vs_denser=dense_score_error,
                    maximum_gradient_error_vs_denser_per_km=dense_gradient_error)
                write_new(HERE / 'terminal03_points' / f'{case}_{arm}_{branch}.json', row)
                rows.append(row)
                print(case, arm, branch, 'PASS', round(time.monotonic() - began, 3), flush=True)
    for path, expected in seal['files'].items():
        assert sha(path) == expected, path
    execution.verify(require_go=True)
    assert sha(seal_path) == SEAL_SHA
    points = sorted((HERE / 'terminal03_points').glob('*.json'))
    result = dict(all_passed=True, execution_protocol_sha256=PROTOCOL_SHA,
        RF_seal_sha256=SEAL_SHA, source_sha256=sha(__file__),
        scientific_sources=read(execution.PROTOCOL)['source_sha256'],
        independent_reference_source_sha256=sha(HERE / 'audit_quadrature02b.py'),
        sealed_file_count=len(seal['files']), decomposition_records=96,
        maximum_saved_score_decomposition_error=decomposition_max,
        endpoint_count=len(rows), fixed_endpoint_probe_count=5 * len(rows),
        max_score_error_with_reference_bound=max(row['maximum_score_error_with_reference_bound'] for row in rows),
        max_gradient_error_including_reference_bound_per_km=max(row['maximum_gradient_error_per_km']
            + row['reference_gradient_error_bound_per_km'] for row in rows),
        max_dense_node_score_difference=max(row['independent_dense_node']['maximum_dense_node_score_difference'] for row in rows),
        minimum_checked_elevation_deg=min(point['minimum_elevation_deg'] for row in rows for point in row['point_records']),
        point_receipts_sha256={str(path): sha(path) for path in points},
        elapsed_seconds=time.monotonic() - began, position_fits=0, GPS_used=False,
        interpretation='numerical and conditional covariance audit only; target identities/associations and shape linearization remain unvalidated; baseline retained')
    write_new(HERE / 'terminal03_audit.json', result)
    signal.alarm(0)
    print(HERE / 'terminal03_audit.json', sha(HERE / 'terminal03_audit.json'), flush=True)


if __name__ == '__main__':
    main()
