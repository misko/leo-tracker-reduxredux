"""Frozen nonlinear fixed profiles and at most eight bounded diagnostic fits.

All target factors remain unqualified associations. Original saved baseline is
the operational policy. Geographic evaluation is external and follows RF seal.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from pathlib import Path
import signal
import time
import traceback

import numpy as np

import adapter as a
import prepare02 as prep
import quadrature02 as q
import recovery as r
from investigate_dsx01_localization_failures import fit

PROTOCOL = a.HERE/'protocol02.json'
ARM_SECONDS = 180.
GLOBAL_SECONDS = 1200.


def required_receipts():
    return (a.STUDY/'math_audit/preflight02.json', a.STUDY/'audit/preflight02.json',
            a.STUDY/'coordinator_go.json')


def verify(require_go=False):
    protocol = r.read(PROTOCOL)
    if r.sha(PROTOCOL) != r.read(a.HERE/'protocol02_seal.json')['protocol_sha256']:
        raise ValueError('execution protocol changed')
    for path, digest in protocol['source_sha256'].items():
        if r.sha(path) != digest:
            raise ValueError('execution source changed: '+path)
    prep.verify()
    base = r.read(a.HERE/'preparation01/preparation_seal.json')
    for path, digest in base['source_sha256'].items():
        if r.sha(path) != digest:
            raise ValueError('original input/source changed: '+path)
    for case, binding in r.read(a.HERE/'preparation01/input_bindings.json').items():
        for path, digest in binding['source_hashes'].items():
            if r.sha(path) != digest:
                raise ValueError('frozen input changed: '+path)
    if require_go:
        for path in required_receipts():
            receipt = r.read(path)
            if receipt.get('all_passed') is not True or receipt.get('execution_protocol_sha256') != r.sha(PROTOCOL):
                raise ValueError('independent receipt/coordinator go missing or mismatched: '+str(path))
    return protocol


def freeze():
    numerical = r.read(prep.OUT/'result.json')
    if numerical.get('all_passed') is not True or numerical['global_fixed_node_count'] != 1281:
        raise ValueError('complete RF-only numerical selection required')
    files = (a.HERE/'adapter.py', a.HERE/'quadrature02.py', a.HERE/'prepare02.py',
             a.HERE/'test_adapter.py', a.HERE/'test_quadrature02.py',
             Path(__file__), a.HERE/'test_execution02.py')
    protocol = dict(version='uncertain new-family nonlinear execution02',
        cases=a.CASES, arms=a.ARMS, branches=a.BRANCHES,
        target_bindings_sha256=r.sha(a.HERE/'preparation01/input_bindings.json'),
        preparation01_sha256=r.sha(a.HERE/'preparation01/preparation_seal.json'),
        preparation02_protocol_sha256=r.sha(prep.OUT/'protocol.json'),
        preparation02_result_sha256=r.sha(prep.OUT/'result.json'),
        amendment_sha256=r.sha(a.STUDY/'PHASE_INTEGRATION_AMENDMENT.md'),
        source_sha256={str(p):r.sha(p) for p in files},
        fixed_common_phase_nodes=1281, quadrature='phase-space Gauss-Legendre with analytic conditioned Student prior; no per-position rule changes',
        phase_domain_s=q.DOMAIN,
        phase_prior='original causal location, unit-marginal-variance Student scale, nu3 conditioned[-15,+15]; no recenter/shrink',
        phase_posterior='diagnostic inference under marginalization; no optimized/calibration target phase coordinate and no target Gamma learning',
        covariance='p(E|C)*integral p(T|E,C,phi)p(phi|domain)dphi; one shared parent posterior, target radio-only shared design, no dormant doublecount',
        shape_only_branch_difference=True, target_constant_sigma_hz=300.,
        target_noise='existing predictive fixed-window sigma times sqrt2 unseen-Gamma convention; no target power or variance fitting',
        profile_positions_per_case_arm=11, maximum_profile_branch_evaluations=88,
        profile_phase_reference='saved original parent arm reference fixed across segment; parent nuisance/Gamma recomputed at every fixed position',
        profile_segment='saved baseline to saved phase-only support, equal fractions0..1; no global-minimum or profile-CI claim',
        maximum_position_fits=8, numerical_workers=2, BLAS_threads_per_worker=1,
        per_arm_seconds=ARM_SECONDS, global_seconds=GLOBAL_SECONDS,
        start_east_north_km=[0., 0.], regional_center_latlon=[37.906, -122.545], regional_width_km=25.,
        phase_rounds=5, position_iterations_per_round=48,
        solver='unchanged bounded_gauss_newton through existing fit helper; scalar target mixture residual changes GN curvature, exact objective retained',
        initial_parent_phase_reference='zero, as original ordinary cold fit',
        parent_phase_refresh='parent curved posterior only; clip original parent phase references to[-15,+15] between fixed five rounds',
        target_phase_reference_refresh=False, multistart=False, constrained_rescue=False,
        unexpected_failure='visible failure/timeout row; no retry, new proposal, budget extension or alternative optimizer',
        optimizer_scalar='original parent residual squared + complete normalized target conditional mixture NLL + original parent visibility; target NLL appended once as sqrt(score)',
        target_density_positivity='fixed sigmas>1Hz and covariance>=diag(sigma^2), normalized conditioned prior; unexpected negative score raises, never clipped',
        phase_visibility='all frozen quadrature nodes and both domain endpoints directly propagated; any negative elevation/invalid propagation fails arm, no dropped nodes or visibility truncation',
        parent_gates='all original retained curved/predictive/visibility/support gates, final parent phase change<=.01s and Gamma logchange<=1e-5',
        parent_IDs='original accepted and likelihood IDs protected; postfit compatibility evaluated by original parent-only construction; explicitly exclude all targetIDs from accepted coverage',
        target_gate='no calibrated experimental target association gate; target remains unqualified even if parents and numerical checks pass',
        target_likelihood_membership='49/43 additional experimental predictive inputs, never new accepted associations or calibrated orbit family',
        operational_policy='saved_baseline for every outcome',
        endpoint_numerical_qualification=dict(
            final_parent_phase_reference=True, center_and_axis_offsets=5,
            central_difference_step_km=q.FD_STEP_KM,
            frozen_nodes=1281, strictly_denser_nodes=2561,
            independent_reference='adaptive phase-space QUADPACK over full domain with direct propagation',
            score_absolute_tolerance=prep.SCORE_TOLERANCE,
            gradient_absolute_tolerance_per_km=prep.GRADIENT_TOLERANCE,
            prior_mass_absolute_tolerance=prep.PRIOR_MASS_TOLERANCE,
            budget='all time charged to same180s/arm and1200s global; raw fitted endpoint checkpoint precedes qualification',
            failure='numerically unqualified diagnostic endpoint, no refinement/retry, saved baseline fallback'),
        diagnostic_edge_mass='posterior quadrature mass for abs(phi)>14s, no prior-domain tuning',
        RF_seal_precedes_GPS=True, no_GPS=True, no_new_IQ_RF_catalogue_or_candidates=True,
        required_receipts=[str(p) for p in required_receipts()])
    r.write_new(PROTOCOL, protocol)
    r.write_new(a.HERE/'protocol02_seal.json', dict(protocol_sha256=r.sha(PROTOCOL)))
    print(r.sha(PROTOCOL))


def alarm(deadline, message):
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise TimeoutError(message)
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError(message)))
    signal.setitimer(signal.ITIMER_REAL, remaining)


def predictive_record(d, p, position):
    c = p.calculate(np.asarray(position))
    prediction = c['nonlinear_target_prediction']
    nodes = prediction['phase_nodes_s']; posterior = prediction['phase_posterior_weights']
    geometry = q.phase_geometry(d, np.asarray(position), nodes)
    phase_marginal_orbit_mean = posterior@geometry['frequency_hz']
    record = dict(position_east_north_km=np.asarray(position),
        total_negative_twice_elbo=c['negative_twice_elbo'],
        parent_negative_twice_elbo=c['parent_negative_twice_elbo'],
        target_conditional=prediction,
        parent_phase_reference=p.reference,
        parent_noise_precision=c['noise_precision'], parent_prior_precision=c['coefficient_prior_precision'],
        parent_coefficient=c['coefficient'], final_log_precision_change=c['final_log_precision_change'],
        phase_posterior_mass_abs_gt14=float(posterior[abs(nodes)>14].sum()),
        phase_posterior_maximum_node_mass=float(posterior.max()),
        phase_posterior_effective_weighted_nodes=float(1/np.sum(posterior**2)),
        target_shared_mean_update_from_E_hz=c['nonlinear_components']['conditional_parent_mean_update_hz'],
        target_conditional_base_covariance_hz2=c['nonlinear_components']['base_covariance_hz2'],
        target_base_raw_hz=c['nonlinear_components']['base_raw_hz'],
        target_phase_marginal_mean_orbit_hz=phase_marginal_orbit_mean,
        target_phase_marginal_mean_residual_hz=c['nonlinear_components']['base_raw_hz']-phase_marginal_orbit_mean,
        target_residual_semantics='source values minus parent radio/E-conditional mean and target phase-posterior orbit mean; shape corrections are integrated covariance, not a reported calibrated mean',
        target_observation_ids=d['target']['observation_ids'],
        original_parent_curved_points=int(p.keep.sum()),
        original_parent_predictive_points=sum(e['points'] for e in d['entries']),
        experimental_predictive_target_points=d['target']['points'],
        target_accepted_association_points=0, target_association_qualified=False,
        operational_policy='saved_baseline')
    return record


def profiles(case, deadline_ns):
    began = time.monotonic(); out = a.HERE/'profiles02'/case
    try:
        alarm(began+max(0., (deadline_ns-time.time_ns())/1e9), 'global propagation budget exhausted during fixed profiles')
        d = a.load_context(case); rows = []
        for arm in a.ARMS:
            saved = d['arms'][arm]
            x0 = np.asarray(saved['endpoint_east_north_km'])
            x1 = np.asarray(d['saved_support']['arms'][arm]['endpoint_east_north_km'])
            for branch in a.BRANCHES:
                p = q.build(d, arm, saved['phase_reference'], branch, 1281)
                for index, fraction in enumerate(np.linspace(0, 1, 11)):
                    x = x0+fraction*(x1-x0)
                    record = dict(case=case, arm=arm, branch=branch, fraction=float(fraction),
                                  **predictive_record(d, p, x))
                    r.write_new(out/f'{arm}_{branch}_{index:02d}.json', record)
                    rows.append(dict(arm=arm, branch=branch, index=index,
                        position_east_north_km=x,
                        parent_negative_twice_elbo=record['parent_negative_twice_elbo'],
                        target_negative_twice_log_density=record['target_conditional']['objective'],
                        total_negative_twice_elbo=record['total_negative_twice_elbo']))
        result = dict(case=case, status='complete', rows=rows, profile_branch_evaluations=len(rows),
                      seconds=time.monotonic()-began, position_fits=0)
    except Exception as exc:
        result = dict(case=case, status='failed', error=repr(exc), traceback=traceback.format_exc(),
                      seconds=time.monotonic()-began, position_fits=0)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    r.write_new(out/'result.json', result)
    return result


def endpoint_qualification(d, p, position):
    x = np.asarray(position); points = [x]
    for axis in range(2):
        step = np.zeros(2); step[axis] = q.FD_STEP_KM
        points += [x+step, x-step]
    records = []
    include_shape = p.experimental_branch == a.BRANCHES[1]
    for at in points:
        components = q.conditional_components(d, p, at)
        values = {str(n):q.integrate(d, components, n, include_shape) for n in (1281, 2561)}
        adaptive = q.adaptive_reference(d, components, include_shape)
        records.append(dict(position_east_north_km=at,
            rules={n:{k:v[k] for k in ('objective', 'quadrature_prior_mass', 'minimum_node_elevation_deg',
                                        'minimum_domain_endpoint_elevation_deg')} for n,v in values.items()},
            adaptive=adaptive))
    gradient = lambda key: np.array([(records[1][key]['objective']-records[2][key]['objective'])/(2*q.FD_STEP_KM),
                                     (records[3][key]['objective']-records[4][key]['objective'])/(2*q.FD_STEP_KM)])
    gradients = {n:np.array([(records[1]['rules'][n]['objective']-records[2]['rules'][n]['objective'])/(2*q.FD_STEP_KM),
                             (records[3]['rules'][n]['objective']-records[4]['rules'][n]['objective'])/(2*q.FD_STEP_KM)]) for n in ('1281', '2561')}
    adaptive_gradient = gradient('adaptive')
    score_error = max(abs(v['rules']['1281']['objective']-v['adaptive']['objective']) for v in records)
    dense_score_error = max(abs(v['rules']['1281']['objective']-v['rules']['2561']['objective']) for v in records)
    gradient_error = float(max(abs(gradients['1281']-adaptive_gradient)))
    dense_gradient_error = float(max(abs(gradients['1281']-gradients['2561'])))
    mass_error = max(abs(v['rules']['1281']['quadrature_prior_mass']-1) for v in records)
    visible = all(min(rule['minimum_node_elevation_deg'], rule['minimum_domain_endpoint_elevation_deg']) >= 0
                  for v in records for rule in v['rules'].values())
    passed = bool(score_error <= prep.SCORE_TOLERANCE and dense_score_error <= prep.SCORE_TOLERANCE
        and gradient_error <= prep.GRADIENT_TOLERANCE and dense_gradient_error <= prep.GRADIENT_TOLERANCE
        and mass_error <= prep.PRIOR_MASS_TOLERANCE and visible)
    return dict(passed=passed, records=records, gradients=gradients, adaptive_gradient=adaptive_gradient,
        maximum_score_error_vs_adaptive=score_error, maximum_score_error_vs_denser=dense_score_error,
        maximum_gradient_error_vs_adaptive_per_km=gradient_error,
        maximum_gradient_error_vs_denser_per_km=dense_gradient_error,
        maximum_prior_mass_error=mass_error, phase_domain_visible=visible)


def parent_gates(d, arm, p, x, c):
    # Replay original construction at the new position/reference. Experimental
    # target IDs are explicitly removed from the reporter's extension ledger.
    saved = dict(endpoint_east_north_km=x, phase_reference=p.reference,
                 negative_twice_elbo=c['parent_negative_twice_elbo'])
    membership = r.membership(d, arm, saved)
    target_ids = set(d['target']['observation_ids'])
    accepted = set(membership['accepted_observation_ids'])-target_ids
    old = d['parent_membership'][arm]
    curved = membership['curved_observation_ids']; predictive = membership['predictive_observation_ids']
    same_likelihood = (curved == old['curved_observation_ids'] and predictive == old['predictive_observation_ids'])
    preservation = set(old['accepted_observation_ids']) <= accepted
    p0 = r.build(d, arm, p.reference)
    summary = r.summary(p0, x, d['entries'])
    curved_pass = all(row['compatible'] for row in summary['gates']['tracks'])
    predictive_pass = all(row['compatible'] for row in summary['linear_gates'])
    return dict(original_summary=summary, original_parent_membership=membership,
        explicit_target_ID_exclusion=sorted(target_ids & set(membership['accepted_observation_ids'])),
        endpoint_compatible_IDs_after_target_exclusion=sorted(accepted),
        original_parent_accepted_IDs_preserved=preservation,
        exact_original_parent_likelihood_IDs=same_likelihood,
        original_parent_curved_gates_pass=curved_pass,
        original_parent_predictive_gates_pass=predictive_pass,
        passed=bool(curved_pass and predictive_pass and preservation and same_likelihood))


def one_fit(case, arm, branch, deadline_ns):
    began = time.monotonic(); out = a.HERE/'fits02'/case/arm/branch
    history = []
    try:
        remaining_global = max(0., (deadline_ns-time.time_ns())/1e9)
        alarm(began+min(ARM_SECONDS, remaining_global), '180s arm or1200s global propagation budget exhausted')
        d = a.load_context(case); reference = np.zeros(len(d['means'])); x = np.zeros(2)
        for epoch in range(5):
            p = q.build(d, arm, reference, branch, 1281)
            fitted = fit(p, x, iterations=48)
            x = np.asarray(fitted['parameters'])
            phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
            change = float(max(abs(phase-reference)))
            round_record = dict(epoch=epoch, fit=fitted, parent_phase_reference=reference,
                                parent_posterior_phase_s=phase, phase_change_s=change)
            r.write_new(out/f'round_{epoch:02d}.json', round_record)
            history.append(round_record); reference = phase
        # Freeze the actual fitted endpoint before any diagnostics/qualification.
        c = p.calculate(x)
        raw = dict(case=case, arm=arm, branch=branch, endpoint_east_north_km=x,
            parent_phase_reference=p.reference, history=history,
            final_parent_phase_change_s=history[-1]['phase_change_s'],
            total_negative_twice_elbo=c['negative_twice_elbo'],
            seconds_to_raw_endpoint=time.monotonic()-began,
            target_association_qualified=False, operational_policy='saved_baseline')
        r.write_new(out/'raw_endpoint.json', raw)
        numerical = endpoint_qualification(d, p, x)
        r.write_new(out/'endpoint_numerical_qualification.json', numerical)
        gates = parent_gates(d, arm, p, x, c)
        r.write_new(out/'parent_gates.json', gates)
        diagnostics = predictive_record(d, p, x)
        r.write_new(out/'rf_diagnostics.json', diagnostics)
        result = dict(raw, status='complete', numerical_qualified=numerical['passed'],
            parent_qualified=bool(gates['passed'] and history[-1]['phase_change_s'] <= .01
                                  and c['final_log_precision_change'] <= 1e-5),
            target_association_qualified=False, scientific_adoption=False,
            seconds=time.monotonic()-began)
    except Exception as exc:
        result = dict(case=case, arm=arm, branch=branch, status='failed', error=repr(exc),
            traceback=traceback.format_exc(), completed_rounds=len(history),
            raw_endpoint_checkpoint_exists=(out/'raw_endpoint.json').exists(),
            seconds=time.monotonic()-began, target_association_qualified=False,
            scientific_adoption=False, operational_policy='saved_baseline')
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    r.write_new(out/'result.json', result)
    print(case, arm, branch, result['status'], round(result['seconds'], 3), result.get('error', ''), flush=True)
    return result


def run():
    protocol = verify(require_go=True)
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        if r.os.environ.get(name) != '1':
            raise ValueError('one numerical thread perworker required')
    started = time.time_ns(); deadline = started+int(GLOBAL_SECONDS*1e9)
    r.write_new(a.HERE/'execution_start02.json', dict(started_utc_ns=started,
        deadline_utc_ns=deadline, protocol_sha256=r.sha(PROTOCOL), maximum_fits=8,
        preflight_and_go_hashes={str(p):r.sha(p) for p in required_receipts()}))
    context = multiprocessing.get_context('spawn')
    with ProcessPoolExecutor(max_workers=2, mp_context=context) as pool:
        profile_rows = [future.result() for future in as_completed(
            [pool.submit(profiles, case, deadline) for case in a.CASES])]
    r.write_new(a.HERE/'profiles_execution02.json', dict(rows=profile_rows,
        attempted_branch_positions=sum(row.get('profile_branch_evaluations', 0) for row in profile_rows)))
    tasks = [(case, arm, branch) for case in a.CASES for arm in a.ARMS for branch in a.BRANCHES]
    with ProcessPoolExecutor(max_workers=2, mp_context=context) as pool:
        fit_rows = [future.result() for future in as_completed(
            [pool.submit(one_fit, *task, deadline) for task in tasks])]
    result = dict(status='terminal', protocol_sha256=r.sha(PROTOCOL),
        profiles=profile_rows, fits=fit_rows, attempted_fits=len(fit_rows),
        maximum_profile_branch_evaluations=88,
        elapsed_wall_seconds=(time.time_ns()-started)/1e9,
        scientific_adoption=False, operational_policy='saved_baseline', no_GPS=True)
    r.write_new(a.HERE/'execution_result02.json', result)
    # Seal every new RF result before any geographic reporter is authorized.
    files = [p for directory in ('profiles02', 'fits02') for p in (a.HERE/directory).rglob('*.json')]
    files += [a.HERE/'execution_start02.json', a.HERE/'profiles_execution02.json',
              a.HERE/'execution_result02.json', PROTOCOL, a.HERE/'protocol02_seal.json']
    r.write_new(a.HERE/'RF_seal02.json', dict(protocol_sha256=r.sha(PROTOCOL),
        files={str(p):r.sha(p) for p in sorted(files)}, no_GPS=True,
        all_attempts_terminal=True, target_association_qualified=False,
        scientific_adoption=False, operational_policy='saved_baseline'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('freeze', 'run'), required=True)
    args = parser.parse_args()
    {'freeze':freeze, 'run':run}[args.stage]()
