"""Bounded nonlinear quadrature convergence/timing preparation; no fits."""

import argparse
from pathlib import Path
import signal
import time

import numpy as np

import adapter as a
import quadrature02 as q
import recovery as r

OUT = a.HERE/'preparation02'
COUNTS = (81, 161, 321, 641, 1281, 2561)
SCORE_TOLERANCE = 1e-3
GRADIENT_TOLERANCE = 1e-3
PRIOR_MASS_TOLERANCE = 1e-8


def freeze():
    protocol = dict(version='nonlinear phase preparation02', no_position_fits=True,
        cases=a.CASES, arms=a.ARMS, branches=a.BRANCHES,
        domain_s=q.DOMAIN, prior='original causal unit-marginal-variance Student nu3 conditioned on domain, no recenter/rescale',
        quadrature='global phase-space Gauss-Legendre; analytic truncated CDF normalization; no numerical renormalization',
        candidate_counts=COUNTS, hard_node_cap=q.MAX_NODES,
        score_absolute_tolerance=SCORE_TOLERANCE,
        position_gradient_absolute_tolerance_per_km=GRADIENT_TOLERANCE,
        central_difference_step_km=q.FD_STEP_KM, prior_mass_absolute_tolerance=PRIOR_MASS_TOLERANCE,
        centers='saved baseline, saved phase-only support, their midpoint, cold regional [0,0]; each c arm independently',
        offsets='center and +/-0.01km each east/north axis, all covariance branches',
        selection='ONE smallest count meeting score and FD-gradient tolerances against2561 and independent adaptive reference at every point; fixed before profiles/fits',
        independent_reference='adaptive scipy QUADPACK phase-space integration with denseuniform641point mode discovery and direct propagation, includes whole domain',
        preparation_seconds_cap=q.PREPARATION_SECONDS, preparation_single_worker=True,
        visibility='propagate domain endpoints and all nodes; no invalid node dropped/clipped; any unseen node aborts future fit instead of truncating density',
        target_association_gate='no newly calibrated gate; target is unqualified experimental predictive evidence, baseline operational',
        parent_gates='original parent curved/predictive/visibility/support gates unchanged',
        target_phase_refresh=False, target_noise_learning=False,
        optimizer_residual='original parent residual vector plus one sqrt(complete normalized target conditional mixture NLL); no average node NLL and no x-dependent clipping',
        optimizer_scalar='parent residual squared + target mixture NLL + original parent visibility; reported full objective differs only by original fixed parent normalization/noise offset',
        GN_curvature_limitation='new scalar mixture residual has different Gauss-Newton curvature from per-observation Gaussian factors; same bounded original solver is only an approximate optimizer of exact scalar',
        target_cost_positivity='target covariance >= diagonal fixed sigma^2; fixed predictive sigmas exceed1Hz and normalized prior implies positive complete density NLL; reject unexpected negative numerical cost',
        fit_launch_authorized=False,
        coordinator_plan_sha256=r.sha(a.STUDY/'COORDINATOR_PLAN.md'),
        amendment_sha256=r.sha(a.STUDY/'PHASE_INTEGRATION_AMENDMENT.md'),
        preparation01_seal_sha256=r.sha(a.HERE/'preparation01/preparation_seal.json'),
        source_sha256={str(p):r.sha(p) for p in (a.HERE/'adapter.py', a.HERE/'quadrature02.py',
            a.HERE/'test_adapter.py', a.HERE/'test_quadrature02.py', Path(__file__))})
    r.write_new(OUT/'protocol.json', protocol)
    r.write_new(OUT/'protocol_seal.json', dict(protocol_sha256=r.sha(OUT/'protocol.json')))


def verify():
    protocol = r.read(OUT/'protocol.json')
    if r.sha(OUT/'protocol.json') != r.read(OUT/'protocol_seal.json')['protocol_sha256']:
        raise ValueError('protocol changed')
    for path, digest in protocol['source_sha256'].items():
        if r.sha(path) != digest:
            raise ValueError('prepared source changed: '+path)
    return protocol


def run():
    protocol = verify()
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        if r.os.environ.get(key) != '1':
            raise ValueError('one numerical thread required')
    if (OUT/'execution_start.json').exists():
        raise FileExistsError('preserve preparation, no automatic restart')
    began = time.monotonic()
    r.write_new(OUT/'execution_start.json', dict(started_utc_ns=time.time_ns(), protocol_sha256=r.sha(OUT/'protocol.json')))
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('600s nonlinear preparation cap')))
    signal.alarm(int(q.PREPARATION_SECONDS))
    rows, laws = [], {}
    try:
        for case in a.CASES:
            d = a.load_context(case)
            laws[case] = {k:v for k,v in q.prior(d).items() if k != 'distribution'}
            for arm in a.ARMS:
                saved = d['arms'][arm]
                p = q.build(d, arm, saved['phase_reference'], a.BRANCHES[0], 81)
                baseline = np.asarray(saved['endpoint_east_north_km'])
                support = np.asarray(d['saved_support']['arms'][arm]['endpoint_east_north_km'])
                centers = dict(baseline=baseline, support=support, midpoint=(baseline+support)/2,
                               cold_regional_start=np.zeros(2))
                for name, center in centers.items():
                    points = [center]
                    for axis in range(2):
                        step = np.zeros(2); step[axis] = q.FD_STEP_KM
                        points += [center+step, center-step]
                    values = []
                    for point_index, x in enumerate(points):
                        t0 = time.monotonic()
                        components = q.conditional_components(d, p, x)
                        component_seconds = time.monotonic()-t0
                        for include_shape in (False, True):
                            branch = a.BRANCHES[int(include_shape)]
                            rule_results = {}
                            for count in COUNTS:
                                t0 = time.monotonic()
                                result = q.integrate(d, components, count, include_shape)
                                rule_results[str(count)] = {k:result[k] for k in ('objective',
                                    'phase_conditional_mean_s', 'phase_conditional_sd_s', 'quadrature_prior_mass',
                                    'minimum_node_elevation_deg', 'minimum_domain_endpoint_elevation_deg')}
                                rule_results[str(count)]['seconds'] = time.monotonic()-t0
                            t0 = time.monotonic()
                            adaptive = q.adaptive_reference(d, components, include_shape)
                            adaptive['seconds'] = time.monotonic()-t0
                            record = dict(case=case, arm=arm, center=name, point_index=point_index,
                                position_east_north_km=x, branch=branch,
                                parent_component_seconds=component_seconds,
                                rules=rule_results, adaptive=adaptive)
                            values.append(record)
                            r.write_new(OUT/'points'/f'{case}_{arm}_{name}_{point_index}_{branch}.json', record)
                    for branch in a.BRANCHES:
                        selected = [v for v in values if v['branch'] == branch]
                        gradients = {str(n):[(selected[1]['rules'][str(n)]['objective']-selected[2]['rules'][str(n)]['objective'])/(2*q.FD_STEP_KM),
                                              (selected[3]['rules'][str(n)]['objective']-selected[4]['rules'][str(n)]['objective'])/(2*q.FD_STEP_KM)] for n in COUNTS}
                        adaptive_gradient = [(selected[1]['adaptive']['objective']-selected[2]['adaptive']['objective'])/(2*q.FD_STEP_KM),
                                             (selected[3]['adaptive']['objective']-selected[4]['adaptive']['objective'])/(2*q.FD_STEP_KM)]
                        checks = {}
                        for count in COUNTS:
                            key = str(count)
                            score_error = max(abs(v['rules'][key]['objective']-v['adaptive']['objective']) for v in selected)
                            score_error_dense = max(abs(v['rules'][key]['objective']-v['rules'][str(q.MAX_NODES)]['objective']) for v in selected)
                            gradient_error = float(np.max(abs(np.asarray(gradients[key])-adaptive_gradient)))
                            dense_gradient_error = float(np.max(abs(np.asarray(gradients[key])-gradients[str(q.MAX_NODES)])))
                            mass_error = max(abs(v['rules'][key]['quadrature_prior_mass']-1) for v in selected)
                            checks[key] = dict(score_error_vs_adaptive=score_error,
                                score_error_vs_denser=score_error_dense,
                                gradient_error_vs_adaptive_per_km=gradient_error,
                                gradient_error_vs_denser_per_km=dense_gradient_error,
                                prior_mass_error=mass_error,
                                passed=bool(score_error <= SCORE_TOLERANCE and score_error_dense <= SCORE_TOLERANCE
                                    and gradient_error <= GRADIENT_TOLERANCE and dense_gradient_error <= GRADIENT_TOLERANCE
                                    and mass_error <= PRIOR_MASS_TOLERANCE))
                        rows.append(dict(case=case, arm=arm, center=name, branch=branch,
                            gradients=gradients, adaptive_gradient=adaptive_gradient, checks=checks))
                        print(case, arm, name, branch, 'passing', [n for n in COUNTS if checks[str(n)]['passed']], flush=True)
        eligible = [n for n in COUNTS[:-1] if all(row['checks'][str(n)]['passed'] for row in rows)]
        chosen = min(eligible) if eligible else None
        result = dict(status='complete', global_fixed_node_count=chosen,
            all_passed=chosen is not None, rows=rows, phase_laws=laws,
            seconds=time.monotonic()-began, position_fits=0,
            protocol_sha256=r.sha(OUT/'protocol.json'), fit_launch_authorized=False)
    except Exception as exc:
        import traceback
        result = dict(status='failed', error=repr(exc), traceback=traceback.format_exc(), rows=rows,
                      phase_laws=laws, seconds=time.monotonic()-began, position_fits=0,
                      protocol_sha256=r.sha(OUT/'protocol.json'), fit_launch_authorized=False)
    finally:
        signal.alarm(0)
    r.write_new(OUT/'result.json', result)
    print(result['status'], result.get('global_fixed_node_count'), result['seconds'], result.get('error', ''), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('freeze', 'run'), required=True)
    args = parser.parse_args()
    {'freeze':freeze, 'run':run}[args.stage]()
