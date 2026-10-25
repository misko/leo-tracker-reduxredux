"""Independent dense-node and adaptive-integral audit; no position fitting.

The adapter's physical node density is independently checked in observation
space. Integration then uses a separate uniform discovery grid, bounded scalar
peak refinement and adaptive phase-space quadrature with its own prior density.
"""
import copy
import hashlib
import json
from pathlib import Path
import signal
import sys
import time
import warnings

import numpy as np
from scipy.integrate import IntegrationWarning, quad
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp
from scipy.stats import t

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'scientific'))
import adapter as a
import quadrature02 as q
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from prototype_dsx01_continuous_position import latlon
from gaussian_oracle import dense_nll

ORDERS = (81, 161, 321, 641, 1281, 2561)
H = .01
SCORE_TOLERANCE = 1e-3
GRADIENT_TOLERANCE = 1e-3


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, data):
    def encode(v):
        if isinstance(v, np.ndarray): return v.tolist()
        if isinstance(v, np.generic): return v.item()
        raise TypeError(type(v).__name__)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(data, stream, default=encode, indent=2, allow_nan=False)
        stream.write('\n')


def independent_components(d, p, x):
    c = p.original_parent_calculate(x)
    u = c['features'][p.keep]
    g = p.noise_groups[p.keep]
    weights = d['powers'][g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
    precision = np.diag(c['coefficient_prior_precision'])+u.T@(u*weights[:, None])
    covariance = np.linalg.solve(precision, np.eye(len(precision)))
    target = a.target_prediction(d, p, x)
    ht = target['shared_design']
    base_covariance = np.diag(target['sigma_hz']**2)+ht@covariance@ht.T+300.**2
    base_raw = target['values_hz']-ht@c['coefficient']
    if d['entries']:
        view, values, sigma, groups, _ = linear_geometry(p, d['entries'])
        geometry = geometry_features(view, x, 0.)
        he = geometry['features']
        raw = values-view.q*geometry['intercept']-he@c['coefficient']
        existing_covariance = np.diag(2*sigma**2)+he@covariance@he.T
        existing_covariance += 300.**2*(groups[:, None] == groups[None, :])
        cross = he@covariance@ht.T
        base_raw -= cross.T@np.linalg.solve(existing_covariance, raw)
        base_covariance -= cross.T@np.linalg.solve(existing_covariance, cross)
    return base_raw, (base_covariance+base_covariance.T)/2


def dense_node_check(d, p, x, components):
    raw, covariance = independent_components(d, p, x)
    raw_error = float(np.max(abs(raw-components['base_raw_hz'])))
    covariance_error = float(np.max(abs(covariance-components['base_covariance_hz2'])))
    if raw_error > 1e-6 or covariance_error > 1e-5:
        raise ValueError(f'independent conditional input mismatch: {raw_error}, {covariance_error}')
    phases = np.unique(np.r_[[-15., -7.5, 0., 7.5, 15.], d['target']['phase_mean_s']])
    coordinates = latlon(x)
    times = np.asarray(d['target_track']['times'])
    labels = np.zeros(len(times), int)
    ratio = d['target_track']['rf_hz']/11.5e9
    maximum_error = 0.
    minimum_elevation = float('inf')
    for include_shape in (False, True):
        implementation = q.node_log_density(d, components, phases, include_shape)
        for index, phase in enumerate(phases):
            frequency, elevation = phase_frequency_grid(d['target_sky'], times, *coordinates, phase_seconds=phase)
            shape = ratio*paired_frequency_modes(d['target_sky'], d['target_mode_bank'], times,
                labels, np.array([phase]), *coordinates)
            prior_covariance = shape@shape.T if include_shape else 0.
            reference = dense_nll(raw-ratio*frequency[0], covariance+prior_covariance)
            difference = abs(reference['negative_twice_log_density']+2*implementation['log_density'][index])
            maximum_error = max(maximum_error, difference)
            minimum_elevation = min(minimum_elevation, float(elevation.min()))
    if maximum_error > 1e-5:
        raise ValueError('independent dense-node score failed: '+str(maximum_error))
    changed = dict(d)
    changed['scan'] = copy.copy(d['scan'])
    changed['scan'].tracks = list(d['scan'].tracks)
    index = d['target']['track_index']
    changed['scan'].tracks[index] = dict(d['scan'].tracks[index],
        values=np.asarray(d['scan'].tracks[index]['values'])+12345.)
    changed['target_track'] = changed['scan'].tracks[index]
    redacted_problem = q.build(changed, 'fitted_c' if p.fitted_c else 'c0', p.reference, a.BRANCHES[0], 81)
    redacted = q.conditional_components(changed, redacted_problem, x)
    for key in ('coefficient', 'noise_precision', 'coefficient_prior_precision'):
        np.testing.assert_array_equal(components['parent'][key], redacted['parent'][key])
    for key in ('base_covariance_hz2', 'parent_precision', 'conditional_parent_mean_update_hz'):
        np.testing.assert_array_equal(components[key], redacted[key])
    np.testing.assert_array_equal(p.reference, redacted_problem.reference)
    np.testing.assert_allclose(redacted['base_raw_hz']-components['base_raw_hz'], 12345., atol=2e-10, rtol=0.)
    return dict(conditional_raw_difference_hz=raw_error, conditional_covariance_difference_hz2=covariance_error,
        maximum_dense_node_score_difference=maximum_error, minimum_checked_elevation_deg=minimum_elevation,
        nonlinear_target_redaction_parent_invariant=True)


def adaptive_integral(d, components, include_shape):
    target = d['target']
    scale = target['phase_sd_s']*np.sqrt((target['phase_nu']-2)/target['phase_nu'])
    distribution = t(target['phase_nu'], loc=target['phase_mean_s'], scale=scale)
    mass = float(distribution.cdf(15)-distribution.cdf(-15))
    calls = 0
    def log_integrand(phase):
        nonlocal calls
        calls += 1
        likelihood = q.node_log_density(d, components, np.array([phase]), include_shape)['log_density'][0]
        return float(likelihood+distribution.logpdf(phase)-np.log(mass))
    grid = np.linspace(-15., 15., 1025)
    values = q.node_log_density(d, components, grid, include_shape)
    combined = values['log_density']+distribution.logpdf(grid)-np.log(mass)
    peaks = (np.flatnonzero((combined[1:-1] >= combined[:-2]) & (combined[1:-1] >= combined[2:]))+1).tolist()
    if combined[0] >= combined[1]: peaks.insert(0, 0)
    if combined[-1] >= combined[-2]: peaks.append(len(grid)-1)
    if len(peaks) > 32:
        raise ValueError('too many unresolved phase peaks for bounded independent reference')
    refined = []
    for index in peaks:
        if index in (0, len(grid)-1):
            refined.append((float(grid[index]), float(combined[index])))
        else:
            fitted = minimize_scalar(lambda phase: -log_integrand(phase),
                bounds=(float(grid[index-1]), float(grid[index+1])), method='bounded',
                options=dict(xatol=1e-9, maxiter=80))
            if not fitted.success:
                raise ValueError('phase integration peak bracket did not resolve')
            refined.append((float(fitted.x), float(-fitted.fun)))
    if not refined:
        raise ValueError('no finite phase integration maximum found')
    shift = max(max(v for _, v in refined), float(combined.max()))
    step = float(grid[1]-grid[0])
    points = sorted(set([phase for peak, _ in refined for phase in
        (peak-4*step, peak-step, peak, peak+step, peak+4*step) if -15 < phase < 15]))
    def density(phase):
        return float(np.exp(log_integrand(phase)-shift))
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter('always', IntegrationWarning)
        output = quad(density, -15., 15., points=points, epsabs=1e-10, epsrel=1e-8,
            limit=600, full_output=1)
    integral, error, information = output[:3]
    if len(output) != 3 or recorded or not integral > 0 or error/integral > 1e-6:
        raise ValueError('independent adaptive integration did not reach error bound: '+str(output[3:] or recorded))
    return dict(objective=float(-2*(shift+np.log(integral))), relative_integral_error=float(error/integral),
        function_calls=calls, initial_uniform_grid_count=1025,
        refined_phase_peaks_s=[phase for phase, _ in refined], maximum_log_integrand=shift,
        initial_grid_max_log_integrand=float(combined.max()),
        adaptive_intervals=int(information['last']), minimum_grid_elevation_deg=float(values['geometry']['elevation_deg'].min()))


def main():
    started = time.monotonic()
    hashes = {a.__file__: sha(a.__file__), q.__file__: sha(q.__file__)}
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('600-second independent numerical preparation cap')))
    signal.alarm(600)
    rows, centers, prior_rows = [], [], []
    out = HERE/'quadrature02_points'
    out.mkdir(exist_ok=True)
    try:
        for case in a.CASES:
            d = a.load_context(case)
            for order in ORDERS:
                _, logweights = q.phase_nodes(d, order)
                prior_rows.append(dict(case=case, order=order, quadrature_prior_mass=float(np.exp(logsumexp(logweights)))))
            for arm in a.ARMS:
                reference = np.asarray(d['arms'][arm]['phase_reference'])
                p = q.build(d, arm, reference, a.BRANCHES[0], 81)
                baseline = np.asarray(d['arms'][arm]['endpoint_east_north_km'])
                support = np.asarray(d['saved_support']['arms'][arm]['endpoint_east_north_km'])
                locations = dict(baseline=baseline, support=support, midpoint=(baseline+support)/2, regional_start=np.zeros(2))
                for label, x in locations.items():
                    evaluations = {}
                    for offset_label, offset in [('center', np.zeros(2)), ('east_minus', [-H, 0.]),
                        ('east_plus', [H, 0.]), ('north_minus', [0., -H]), ('north_plus', [0., H])]:
                        point = x+np.asarray(offset)
                        components = q.conditional_components(d, p, point)
                        dense = dense_node_check(d, p, point, components) if offset_label == 'center' else None
                        for branch_index, branch in enumerate(a.BRANCHES):
                            numerical_start = time.monotonic()
                            reference_integral = adaptive_integral(d, components, bool(branch_index))
                            scores, diagnostic = {}, None
                            for order in ORDERS:
                                integral = q.integrate(d, components, order, bool(branch_index))
                                scores[str(order)] = integral['objective']
                                if order == ORDERS[-1]:
                                    weights = integral['phase_posterior_weights']
                                    diagnostic = dict(phase_conditional_mean_s=integral['phase_conditional_mean_s'],
                                        phase_conditional_sd_s=integral['phase_conditional_sd_s'],
                                        largest_posterior_node_mass=float(weights.max()),
                                        effective_weighted_node_count=float(1/(weights@weights)),
                                        posterior_mass_by_5s_intervals=[float(weights[(integral['phase_nodes_s'] >= low)
                                            & (integral['phase_nodes_s'] <= low+5)].sum()) for low in (-15, -10, -5, 0, 5, 10)],
                                        total_phase_posterior_mass=float(weights.sum()),
                                        conditional_diagnostic_not_calibrated_phase_truth=True)
                            row = dict(case=case, arm=arm, location=label, offset=offset_label, branch=branch,
                                position_east_north_km=point, adaptive_reference=reference_integral,
                                fixed_order_scores=scores, posterior_phase=diagnostic, dense_node_audit=dense,
                                seconds=time.monotonic()-numerical_start)
                            write_new(out/f'{case}_{arm}_{label}_{offset_label}_{branch}.json', row)
                            rows.append(row)
                            evaluations[(offset_label, branch)] = row
                    for branch in a.BRANCHES:
                        check = dict(case=case, arm=arm, location=label, branch=branch, orders=[])
                        for order in ORDERS:
                            center = evaluations[('center', branch)]
                            score_error = abs(center['fixed_order_scores'][str(order)]-center['adaptive_reference']['objective'])
                            reference_gradient, fixed_gradient = [], []
                            for axis in ('east', 'north'):
                                lo, hi = [evaluations[(axis+'_'+direction, branch)] for direction in ('minus', 'plus')]
                                reference_gradient.append((hi['adaptive_reference']['objective']-lo['adaptive_reference']['objective'])/(2*H))
                                fixed_gradient.append((hi['fixed_order_scores'][str(order)]-lo['fixed_order_scores'][str(order)])/(2*H))
                            gradient_error = float(np.max(abs(np.asarray(fixed_gradient)-reference_gradient)))
                            check['orders'].append(dict(order=order, score_error=score_error, gradient_error=gradient_error,
                                reference_gradient=reference_gradient, fixed_gradient=fixed_gradient,
                                passes=score_error <= SCORE_TOLERANCE and gradient_error <= GRADIENT_TOLERANCE))
                        centers.append(check)
                    print('independent quadrature', case, arm, label, 'seconds', round(time.monotonic()-started, 2), flush=True)
        eligible = [order for order in ORDERS[:-1] if all(abs(r['quadrature_prior_mass']-1) <= 1e-8 for r in prior_rows if r['order'] == order)
            and all(abs(row['fixed_order_scores'][str(order)]-row['adaptive_reference']['objective']) <= SCORE_TOLERANCE for row in rows)
            and all(next(v for v in center['orders'] if v['order'] == order)['passes'] for center in centers)]
        for path, expected in hashes.items():
            if sha(path) != expected:
                raise ValueError('scientific source changed during independent audit: '+path)
        status = 'pass' if eligible else 'no_go'
        result = dict(status=status, position_fits=0, GPS_used=False, elapsed_seconds=time.monotonic()-started,
            source_sha256=sha(__file__), scientific_sources=hashes, fixed_global_orders_passing=eligible,
            score_tolerance=SCORE_TOLERANCE, gradient_tolerance_objective_per_km=GRADIENT_TOLERANCE,
            finite_difference_step_km=H, point_rows=len(rows), center_rows=centers, prior_mass_rows=prior_rows,
            max_dense_node_difference=max(r['dense_node_audit']['maximum_dense_node_score_difference']
                for r in rows if r['dense_node_audit']),
            minimum_visibility_deg=min(r['adaptive_reference']['minimum_grid_elevation_deg'] for r in rows),
            note='jointconditional Gaussian plus domain-conditioned nonlinear target phase only; parent variational and first-order physical shape approximations remain')
        write_new(HERE/'quadrature02_audit.json', result)
        print('independent quadrature audit', status, 'eligible_orders', eligible, 'seconds', round(result['elapsed_seconds'], 2), flush=True)
    except Exception as exc:
        import traceback
        write_new(HERE/'quadrature02_audit.json', dict(status='no_go', position_fits=0, GPS_used=False,
            elapsed_seconds=time.monotonic()-started, completed_point_rows=len(rows),
            error=repr(exc), traceback=traceback.format_exc(), scientific_sources=hashes, source_sha256=sha(__file__)))
        raise
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    main()
