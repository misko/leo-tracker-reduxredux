"""Independent sealed-output arithmetic, ownership and gate audit; no propagation."""

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCIENCE = ROOT/'scientific'
OLD = Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')
CASES = ('DS24-0095', 'DS24-0087')
ARMS = ('c0', 'fitted_c')
BRANCHES = ('predictive_shape_zero', 'predictive_shape_prior')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mixture(record):
    prediction = record['target_conditional']
    nodes = np.asarray(prediction['phase_nodes_s'])
    logprior = np.asarray(prediction['phase_log_prior_weights'])
    loglike = np.asarray(prediction['node_log_density'])
    posterior = np.asarray(prediction['phase_posterior_weights'])
    assert nodes.shape == logprior.shape == loglike.shape == posterior.shape == (1281,)
    assert np.isfinite(logprior).all() and np.isfinite(loglike).all()
    assert np.all(posterior >= 0) and abs(posterior.sum()-1) < 1e-12
    np.testing.assert_allclose(prediction['quadrature_prior_mass'], np.exp(logprior).sum(), rtol=0, atol=1e-12)
    assert abs(np.exp(logprior).sum()-1) < 1e-8
    # Independent stable sum, without calling the implementation's integrator.
    logterms = logprior+loglike
    maximum = float(np.max(logterms))
    score = float(-2*(maximum+np.log(np.exp(logterms-maximum).sum())))
    np.testing.assert_allclose(score, prediction['objective'], atol=1e-9, rtol=0)
    np.testing.assert_allclose(loglike, -.5*(np.asarray(prediction['node_quadratic'])+
        np.asarray(prediction['node_logdet'])+prediction['expected_node_terms']['normalization']), atol=1e-10, rtol=0)
    selected = posterior > 0
    kl = float(2*np.sum(posterior[selected]*(np.log(posterior[selected])-logprior[selected])))
    expected = prediction['expected_node_terms']
    np.testing.assert_allclose(posterior@np.asarray(prediction['node_quadratic']), expected['quadratic'], atol=1e-8, rtol=0)
    np.testing.assert_allclose(posterior@np.asarray(prediction['node_logdet']), expected['logdet'], atol=1e-9, rtol=0)
    np.testing.assert_allclose(kl, prediction['phase_posterior_to_prior_quadrature_penalty'], atol=1e-8, rtol=0)
    np.testing.assert_allclose(score, sum(expected.values())+kl, atol=1e-8, rtol=0)
    np.testing.assert_allclose(record['total_negative_twice_elbo'], record['parent_negative_twice_elbo']+score, atol=1e-8, rtol=0)
    mean = float(posterior@nodes)
    np.testing.assert_allclose(mean, prediction['phase_conditional_mean_s'], atol=1e-12, rtol=0)
    np.testing.assert_allclose(np.sqrt(posterior@((nodes-mean)**2)), prediction['phase_conditional_sd_s'], atol=1e-12, rtol=0)
    assert min(prediction['minimum_node_elevation_deg'], prediction['minimum_domain_endpoint_elevation_deg']) >= 0
    assert record['target_accepted_association_points'] == 0 and record['target_association_qualified'] is False
    assert record['operational_policy'] == 'saved_baseline'
    return abs(score-prediction['objective'])


def numerical_qualification(record):
    points = record['records']
    assert len(points) == 5
    x = np.asarray(points[0]['position_east_north_km'])
    for index, step in enumerate(([.01, 0], [-.01, 0], [0, .01], [0, -.01]), 1):
        np.testing.assert_allclose(np.asarray(points[index]['position_east_north_km'])-x, step, atol=1e-14, rtol=0)
    def scores(key):
        return np.array([point['adaptive']['objective'] if key == 'adaptive' else point['rules'][key]['objective'] for point in points])
    def gradient(values):
        return np.array([(values[1]-values[2])/.02, (values[3]-values[4])/.02])
    fixed, dense, adaptive = scores('1281'), scores('2561'), scores('adaptive')
    checks = dict(maximum_score_error_vs_adaptive=float(max(abs(fixed-adaptive))),
        maximum_score_error_vs_denser=float(max(abs(fixed-dense))),
        maximum_gradient_error_vs_adaptive_per_km=float(max(abs(gradient(fixed)-gradient(adaptive)))),
        maximum_gradient_error_vs_denser_per_km=float(max(abs(gradient(fixed)-gradient(dense)))),
        maximum_prior_mass_error=max(abs(point['rules']['1281']['quadrature_prior_mass']-1) for point in points))
    visible = all(min(rule['minimum_node_elevation_deg'], rule['minimum_domain_endpoint_elevation_deg']) >= 0
        for point in points for rule in point['rules'].values())
    passed = bool(visible and all(value <= (1e-8 if name == 'maximum_prior_mass_error' else 1e-3) for name, value in checks.items()))
    assert record['passed'] == passed and record['phase_domain_visible'] == visible
    for name, value in checks.items():
        np.testing.assert_allclose(value, record[name], atol=1e-14, rtol=0)
    return passed, checks


def main():
    seal_path = SCIENCE/'RF_seal03.json'
    seal = read(seal_path)
    for path, digest in seal['files'].items():
        assert sha(path) == digest, path
    protocol_path = SCIENCE/'protocol03.json'
    assert seal['protocol_sha256'] == sha(protocol_path)
    protocol = read(protocol_path)
    for path, digest in protocol['source_sha256'].items():
        assert sha(path) == digest, path
    assert seal['no_GPS'] and seal['all_attempts_terminal'] and seal['scientific_adoption'] is False
    result = read(SCIENCE/'execution_result03.json')
    start = read(SCIENCE/'execution_start03.json')
    assert start['deadline_utc_ns']-start['started_utc_ns'] == int(1200e9)
    for path, digest in start['preflight_and_go_hashes'].items():
        assert sha(path) == digest
        receipt = read(path)
        assert receipt['all_passed'] and receipt['execution_protocol_sha256'] == sha(protocol_path)
    assert result['elapsed_wall_seconds'] < 1200 and result['attempted_fits'] == 8
    expected_fits = {(case, arm, branch) for case in CASES for arm in ARMS for branch in BRANCHES}
    assert {(row['case'], row['arm'], row['branch']) for row in result['fits']} == expected_fits
    expected_profiles = {(case, arm, branch, index) for case in CASES for arm in ARMS for branch in BRANCHES for index in range(11)}
    seen_profiles, score_errors, profile_pairs = set(), [], {}
    for case in CASES:
        parent = read(OLD/case/'parent.json')
        support = read(OLD/'eligibility02'/case/'result.json')['selected']
        for arm in ARMS:
            x0 = np.asarray(parent['arms'][arm]['endpoint_east_north_km'])
            x1 = np.asarray(support['arms'][arm]['endpoint_east_north_km'])
            for branch in BRANCHES:
                for index in range(11):
                    path = SCIENCE/'profiles03'/case/f'{arm}_{branch}_{index:02d}.json'
                    record = read(path)
                    assert str(path) in seal['files']
                    assert record['case'] == case and record['arm'] == arm and record['branch'] == branch
                    np.testing.assert_allclose(record['position_east_north_km'], x0+(index/10)*(x1-x0), atol=1e-14, rtol=0)
                    np.testing.assert_array_equal(record['parent_phase_reference'], parent['arms'][arm]['phase_reference'])
                    score_errors.append(mixture(record))
                    seen_profiles.add((case, arm, branch, index))
                    profile_pairs.setdefault((case, arm, index), {})[branch] = record
    assert seen_profiles == expected_profiles
    for pair in profile_pairs.values():
        zero, prior = (pair[branch] for branch in BRANCHES)
        for field in ('parent_negative_twice_elbo', 'parent_phase_reference', 'parent_noise_precision',
            'parent_prior_precision', 'parent_coefficient', 'target_observation_ids', 'target_base_raw_hz',
            'target_shared_mean_update_from_E_hz', 'target_conditional_base_covariance_hz2'):
            np.testing.assert_array_equal(zero[field], prior[field])
        for field in ('phase_nodes_s', 'phase_log_prior_weights'):
            np.testing.assert_array_equal(zero['target_conditional'][field], prior['target_conditional'][field])
    rows = []
    for fit in result['fits']:
        case, arm, branch = (fit[key] for key in ('case', 'arm', 'branch'))
        directory = SCIENCE/'fits03'/case/arm/branch
        assert fit['status'] == 'complete' and fit['seconds'] <= 180
        assert read(directory/'result.json') == fit
        raw = read(directory/'raw_endpoint.json')
        assert len(raw['history']) == len(fit['history']) == 5
        assert raw['seconds_to_raw_endpoint'] <= fit['seconds']
        reference = np.zeros(len(fit['parent_phase_reference']))
        for epoch, record in enumerate(fit['history']):
            assert record == read(directory/f'round_{epoch:02d}.json')
            np.testing.assert_array_equal(record['parent_phase_reference'], reference)
            posterior = np.asarray(record['parent_posterior_phase_s'])
            np.testing.assert_allclose(max(abs(posterior-reference)), record['phase_change_s'], atol=1e-14, rtol=0)
            reference = posterior
        np.testing.assert_array_equal(fit['parent_phase_reference'], fit['history'][-1]['parent_phase_reference'])
        diagnostic = read(directory/'rf_diagnostics.json')
        score_errors.append(mixture(diagnostic))
        gates = read(directory/'parent_gates.json')
        summary = gates['original_summary']
        original = read(OLD/case/'parent.json')['coverage'][arm]
        target_ids = set(read(HERE/(case+'_target_binding.json'))['observation_ids'])
        compatible = set(gates['endpoint_compatible_IDs_after_target_exclusion'])
        membership = gates['original_parent_membership']
        assert compatible == set(membership['accepted_observation_ids'])-target_ids
        assert not compatible&target_ids
        preserved = set(original['accepted_observation_ids']) <= compatible
        identical = membership['curved_observation_ids'] == original['curved_observation_ids'] and membership['predictive_observation_ids'] == original['predictive_observation_ids']
        tracks = summary['gates']['tracks']+summary['linear_gates']
        x = np.asarray(summary['endpoint_east_north_km'])
        absolute_phase = float(np.max(abs(np.asarray(summary['state']['phases']))))
        original_valid = bool(tracks and all(row['compatible'] for row in tracks)
            and summary['final_phase_change_s'] <= .01 and x.shape == (2,) and np.isfinite(x).all()
            and np.all(abs(x) <= 12.5+1e-8) and absolute_phase <= 15.000001)
        assert gates['original_single_arm_valid'] == original_valid
        assert gates['passed'] == bool(original_valid and preserved and identical)
        assert gates['original_parent_accepted_IDs_preserved'] == preserved
        assert gates['exact_original_parent_likelihood_IDs'] == identical
        numerical, errors = numerical_qualification(read(directory/'endpoint_numerical_qualification.json'))
        parent_valid = gates['passed'] and fit['final_parent_phase_change_s'] <= .01 and diagnostic['final_log_precision_change'] <= 1e-5
        assert fit['numerical_qualified'] == numerical and fit['parent_qualified'] == parent_valid
        assert numerical and parent_valid
        assert fit['target_association_qualified'] is False and fit['scientific_adoption'] is False
        assert fit['operational_policy'] == 'saved_baseline'
        np.testing.assert_allclose(diagnostic['total_negative_twice_elbo'], fit['total_negative_twice_elbo'], atol=1e-8, rtol=0)
        rows.append(dict(case=case, arm=arm, branch=branch, numerical_qualified=numerical,
            parent_qualified=bool(parent_valid), original_parent_IDs_preserved=preserved,
            phase_change_s=fit['final_parent_phase_change_s'], maximum_absolute_parent_phase_s=absolute_phase,
            Gamma_log_change=diagnostic['final_log_precision_change'],
            total_negative_twice_elbo=diagnostic['total_negative_twice_elbo'],
            parent_negative_twice_elbo=diagnostic['parent_negative_twice_elbo'],
            target_conditional_NLL=diagnostic['target_conditional']['objective'],
            seconds=fit['seconds'], endpoint_numerical_errors=errors,
            target_accepted_points=0, scientific_adoption=False))
    for pair in result['paired_controls']:
        matching = [row for row in rows if row['case'] == pair['case'] and row['branch'] == pair['branch']]
        assert len(matching) == 2
        assert pair['both_arms_completed'] and pair['both_arms_parent_qualified'] and pair['both_arms_numerically_qualified']
        assert pair['target_association_qualified'] is False and pair['scientific_adoption'] is False
    output = dict(status='passed', RF_seal_sha256=sha(seal_path), execution_protocol_sha256=sha(protocol_path),
        source_sha256=sha(Path(__file__)), no_position_fits=True, no_new_propagation=True, GPS_used=False,
        sealed_files_verified=len(seal['files']), profile_records_verified=len(seen_profiles), fit_records_verified=len(rows),
        rows=rows, maximum_saved_mixture_score_reconstruction_error=max(score_errors),
        matched_profile_parent_states_and_phase_priors=True, all_target_IDs_excluded_from_accepted_coverage=True,
        final_numerical_and_original_gate_predicate_arithmetic_passed=True,
        raw_endpoints_and_all_round_checkpoints_preserved=True,
        elapsed_wall_seconds=result['elapsed_wall_seconds'], summed_arm_seconds=sum(row['seconds'] for row in rows),
        original_operational_policy='saved_baseline', target_association_qualified=False,
        caveat='Audit reconstructs saved normalized mixture and gate/numerical decisions without propagation; independent math reviewer replays actual final-node densities and phase integration.')
    with (HERE/'terminal_audit.json').open('x') as stream:
        json.dump(output, stream, indent=2); stream.write('\n')
    print(json.dumps({k:v for k,v in output.items() if k!='rows'}, indent=2))


if __name__ == '__main__':
    main()
