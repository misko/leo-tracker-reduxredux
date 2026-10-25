"""Read sealed RF outputs only; no propagation, fitting or geographic input."""

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def run():
    seal = read(HERE/'RF_seal03.json')
    for path, digest in seal['files'].items():
        if sha(path) != digest:
            raise ValueError('RF seal changed: '+path)
    execution = read(HERE/'execution_result03.json')
    rows, profiles, contrasts = [], [], []
    for result in sorted(execution['fits'], key=lambda r:(r['case'], r['arm'], r['branch'])):
        case, arm, branch = result['case'], result['arm'], result['branch']
        directory = HERE/'fits03'/case/arm/branch
        gates = read(directory/'parent_gates.json')
        numerical = read(directory/'endpoint_numerical_qualification.json')
        diagnostics = read(directory/'rf_diagnostics.json')
        pred = diagnostics['target_conditional']
        row = {key:result[key] for key in ('case', 'arm', 'branch', 'status',
            'endpoint_east_north_km', 'numerical_qualified', 'parent_qualified',
            'seconds', 'final_parent_phase_change_s')}
        row.update(total_negative_twice_elbo=result['total_negative_twice_elbo'],
            target_negative_twice_log_density=pred['objective'],
            expected_node_terms=pred['expected_node_terms'],
            phase_posterior_quadrature_penalty=pred['phase_posterior_to_prior_quadrature_penalty'],
            posterior_phase_mean_s=pred['phase_conditional_mean_s'],
            posterior_phase_sd_s=pred['phase_conditional_sd_s'],
            posterior_phase_mass_abs_gt14=diagnostics['phase_posterior_mass_abs_gt14'],
            posterior_phase_max_node_mass=diagnostics['phase_posterior_maximum_node_mass'],
            parent_absolute_posterior_phase_max_s=gates['absolute_parent_posterior_phase_max_s'],
            original_parent_accepted_IDs_preserved=gates['original_parent_accepted_IDs_preserved'],
            exact_original_parent_likelihood_IDs=gates['exact_original_parent_likelihood_IDs'],
            original_parent_curved_points=diagnostics['original_parent_curved_points'],
            original_parent_predictive_points=diagnostics['original_parent_predictive_points'],
            experimental_predictive_target_points=diagnostics['experimental_predictive_target_points'],
            target_accepted_association_points=0,
            minimum_phase_domain_sample_elevation_deg=min(pred['minimum_node_elevation_deg'], pred['minimum_domain_endpoint_elevation_deg']),
            maximum_endpoint_score_error_vs_adaptive=numerical['maximum_score_error_vs_adaptive'],
            maximum_endpoint_score_error_vs_denser=numerical['maximum_score_error_vs_denser'],
            maximum_endpoint_gradient_error_vs_adaptive_per_km=numerical['maximum_gradient_error_vs_adaptive_per_km'],
            maximum_endpoint_gradient_error_vs_denser_per_km=numerical['maximum_gradient_error_vs_denser_per_km'],
            target_association_qualified=False, operational_policy='saved_baseline')
        rows.append(row)
        left = read(HERE/'profiles03'/case/f'{arm}_{branch}_00.json')
        right = read(HERE/'profiles03'/case/f'{arm}_{branch}_10.json')
        first, last = left['target_conditional'], right['target_conditional']
        profile = dict(case=case, arm=arm, branch=branch,
            kind='fixed parent phase-reference baseline-to-saved-support endpoint comparison',
            parent_objective_change=right['parent_negative_twice_elbo']-left['parent_negative_twice_elbo'],
            target_objective_change=last['objective']-first['objective'],
            total_objective_change=right['total_negative_twice_elbo']-left['total_negative_twice_elbo'],
            target_expected_node_term_changes={key:last['expected_node_terms'][key]-first['expected_node_terms'][key]
                                              for key in ('quadratic', 'logdet', 'normalization')},
            target_phase_quadrature_penalty_change=last['phase_posterior_to_prior_quadrature_penalty']-first['phase_posterior_to_prior_quadrature_penalty'])
        profiles.append(profile)
    for case in ('DS24-0095', 'DS24-0087'):
        for arm in ('c0', 'fitted_c'):
            same = [r for r in rows if r['case']==case and r['arm']==arm]
            zero = next(r for r in same if r['branch']=='predictive_shape_zero')
            prior = next(r for r in same if r['branch']=='predictive_shape_prior')
            baseline = read(HERE/'profiles03'/case/f'{arm}_predictive_shape_zero_00.json')['position_east_north_km']
            contrasts.append(dict(case=case, arm=arm,
                zero_prior_endpoint_separation_km=float(np.linalg.norm(np.asarray(zero['endpoint_east_north_km'])-prior['endpoint_east_north_km'])),
                zero_shift_from_saved_baseline_km=float(np.linalg.norm(np.asarray(zero['endpoint_east_north_km'])-baseline)),
                prior_shift_from_saved_baseline_km=float(np.linalg.norm(np.asarray(prior['endpoint_east_north_km'])-baseline))))
    result = dict(RF_seal_sha256=sha(HERE/'RF_seal03.json'),
        source_sha256=sha(Path(__file__)), no_propagation=True, no_fits=True, no_GPS=True,
        run_elapsed_wall_seconds=execution['elapsed_wall_seconds'],
        profile_branch_positions=88, fits=rows, fixed_profile_endpoint_changes=profiles,
        RF_endpoint_contrasts=contrasts,
        active_fit_seconds_sum=sum(r['seconds'] for r in rows),
        operational_policy='saved_baseline', target_association_qualified=False)
    write_new(HERE/'RF_summary03.json', result)
    write_new(HERE/'RF_summary03_seal.json', dict(RF_summary03_sha256=sha(HERE/'RF_summary03.json'),
        summary_source_sha256=sha(Path(__file__)), original_RF_seal_sha256=sha(HERE/'RF_seal03.json')))
    print(json.dumps(dict(run_elapsed_wall_seconds=result['run_elapsed_wall_seconds'],
        active_fit_seconds_sum=result['active_fit_seconds_sum'], contrasts=contrasts,
        maximum_endpoint_score_error=max(r['maximum_endpoint_score_error_vs_adaptive'] for r in rows),
        maximum_endpoint_gradient_error_per_km=max(r['maximum_endpoint_gradient_error_vs_adaptive_per_km'] for r in rows),
        maximum_phase_edge_mass=max(r['posterior_phase_mass_abs_gt14'] for r in rows)), indent=2))


if __name__ == '__main__':
    run()
