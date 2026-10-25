"""Nonlinear target phase marginalization under amendment02.

Original Student location/marginal SD/nu are conditioned on [-15,+15] seconds
without recentering. Parent posterior and original predictive evidence remain
unchanged. Only target-local three-mode shape covariance differs by branch.
"""

import numpy as np
from scipy.integrate import quad
from scipy.linalg import solve_triangular
from scipy.special import logsumexp, roots_legendre
from scipy.stats import t as student

import adapter as a
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from prototype_dsx01_continuous_position import latlon

DOMAIN = (-15., 15.)
MAX_NODES = 2561
PREPARATION_SECONDS = 600.
FD_STEP_KM = .01


def prior(d):
    target = d['target']; nu = float(target['phase_nu'])
    if nu != 3.:
        raise ValueError('amendment fixes original Student nu=3')
    location, sd = target['phase_mean_s'], target['phase_sd_s']
    scale = sd*np.sqrt((nu-2)/nu)
    distribution = student(nu, loc=location, scale=scale)
    mass = float(distribution.cdf(DOMAIN[1])-distribution.cdf(DOMAIN[0]))
    moments = [quad(lambda phi: phi**k*distribution.pdf(phi)/mass,
                    *DOMAIN, epsabs=1e-11, epsrel=1e-11)[0] for k in (1, 2)]
    return dict(original_location_s=location, original_marginal_sd_s=sd,
                original_Student_scale_s=scale, nu=nu, domain_s=DOMAIN,
                interval_probability=mass, removed_mass=1-mass,
                conditional_mean_s=moments[0],
                conditional_variance_s2=moments[1]-moments[0]**2,
                conditional_sd_s=float(np.sqrt(moments[1]-moments[0]**2)),
                distribution=distribution)


def phase_nodes(d, count):
    """Common global phase-space Gauss-Legendre rule, no fitted recentering."""
    if not isinstance(count, int) or count < 2 or count > MAX_NODES:
        raise ValueError('fixed node count outside preparation hard cap')
    if 'phase_rule_cache02' not in d:
        d['phase_rule_cache02'] = {}
    if count not in d['phase_rule_cache02']:
        z, weight = roots_legendre(count)
        lo, hi = DOMAIN
        nodes = lo+(z+1)*(hi-lo)/2
        law = prior(d)
        log_weight = np.log(weight*(hi-lo)/2)+law['distribution'].logpdf(nodes)-np.log(law['interval_probability'])
        d['phase_rule_cache02'][count] = (nodes, log_weight)
    return d['phase_rule_cache02'][count]


def phase_geometry(d, position, phases):
    """Vectorized calls to original propagation; identical to scalar-node calls."""
    phases = np.asarray(phases, float)
    if phases.ndim != 1 or not len(phases) or np.any(phases < DOMAIN[0]) or np.any(phases > DOMAIN[1]):
        raise ValueError('finite nonempty phases inside frozen domain required')
    t = d['target_track']; times = np.asarray(t['times']); n = len(phases)
    sky = dict(time_s=d['target_sky']['time_s'])
    bank = dict(time_s=d['target_mode_bank']['time_s'])
    for key in ('position_km', 'velocity_km_s'):
        sky[key] = np.broadcast_to(d['target_sky'][key], (n, *d['target_sky'][key].shape[1:]))
        source = d['target_mode_bank'][key]
        bank[key] = np.broadcast_to(source[None], (n, *source.shape)).reshape(n*3, *source.shape[1:])
    labels = np.repeat(np.arange(n), len(times))
    flat_times = np.tile(times, n)
    coordinates = latlon(np.asarray(position)[:2])
    f, elevation = paired_phase_frequency(sky, flat_times, labels, phases, *coordinates)
    b = paired_frequency_modes(sky, bank, flat_times, labels, phases, *coordinates)
    q = t['rf_hz']/11.5e9
    # Both domain endpoints are also explicitly propagated by the caller's
    # visibility audit; no invalid node is clipped or discarded.
    return dict(frequency_hz=(q*f).reshape(n, -1),
                shape_columns_hz=(q*b).reshape(n, -1, 3),
                elevation_deg=elevation.reshape(n, -1))


def conditional_components(d, p, position):
    """Exact shared-posterior p(T|E,C) before target phase/shape integration.

    Conditioning on E here is predictive algebra only. It does not alter any
    parent coefficients, phase references or Gamma/noise learner.
    """
    x = np.asarray(position)
    parent = dict(p.original_parent_calculate(x))
    g = p.noise_groups[p.keep]
    weights = d['powers'][g]*parent['noise_precision'][g]/p.point_noise[p.keep]**2
    train = parent['features'][p.keep]
    gram = np.diag(parent['coefficient_prior_precision'])+train.T@(train*weights[:, None])
    root = np.linalg.cholesky(gram)
    target = a.target_prediction(d, p, x)
    ht = target['shared_design']
    ut = solve_triangular(root, ht.T, lower=True).T
    if d['entries']:
        view, values, sigma, groups, _ = linear_geometry(p, d['entries'])
        geometry = geometry_features(view, x, 0.)
        he = geometry['features']
        raw = values-view.q*geometry['intercept']-he@parent['coefficient']
        ue = solve_triangular(root, he.T, lower=True).T
        ng = int(groups.max())+1
        constants = np.eye(ng)[groups]*300.
        fe = np.column_stack((ue, constants))
        ft = np.column_stack((ut, np.zeros((len(ut), ng))))
        noise = sigma*np.sqrt(2)
        white = fe/noise[:, None]
        precision = np.eye(fe.shape[1])+white.T@white
        re = np.linalg.cholesky(precision)
        rhs = white.T@(raw/noise)
        m = solve_triangular(re.T, solve_triangular(re, rhs, lower=True), lower=False)
        conditional_mean = ft@m
        predictive_uncertainty = solve_triangular(re, ft.T, lower=True).T
        existing = a.gaussian_score(raw, fe, noise)
        if abs(existing['objective']-parent['linear_predictive_objective']) > 1e-5:
            raise ValueError('original predictive score does not replay')
    else:
        he, raw = np.empty((0, len(gram))), np.empty(0)
        conditional_mean = np.zeros(len(ut))
        predictive_uncertainty = ut
        existing = dict(objective=0., quadratic=0., logdet=0., normalization=0.)
    covariance = (np.diag(target['sigma_hz']**2)
                  + predictive_uncertainty@predictive_uncertainty.T+300.**2)
    covariance = (covariance+covariance.T)/2
    target_root = np.linalg.cholesky(covariance)
    base_raw = target['values_hz']-ht@parent['coefficient']-conditional_mean
    endpoint_elevation = phase_geometry(d, x, np.asarray(DOMAIN))['elevation_deg']
    return dict(position_east_north_km=x, parent=parent, existing=existing,
                base_raw_hz=base_raw, base_covariance_hz2=covariance,
                root=target_root, base_logdet=float(2*np.log(np.diag(target_root)).sum()),
                density_normalization=float(len(base_raw)*np.log(2*np.pi)),
                target_sigma_hz=target['sigma_hz'], target_shared_design=ht,
                conditional_parent_mean_update_hz=conditional_mean,
                parent_precision=gram, parent_predictive_design=he,
                parent_predictive_raw_hz=raw,
                domain_endpoint_min_elevation_deg=float(endpoint_elevation.min()),
                unchanged_target_phase_prior_parameters=d['target'])


def node_log_density(d, components, phases, include_shape):
    geometry = phase_geometry(d, components['position_east_north_km'], phases)
    raw = components['base_raw_hz'][None]-geometry['frequency_hz']
    w = solve_triangular(components['root'], raw.T, lower=True).T
    quadratic = np.sum(w*w, axis=1)
    logdet = np.full(len(raw), components['base_logdet'])
    if include_shape:
        b = geometry['shape_columns_hz']
        flat = b.transpose(1, 0, 2).reshape(b.shape[1], -1)
        wb = solve_triangular(components['root'], flat, lower=True).reshape(b.shape[1], len(b), 3).transpose(1, 0, 2)
        gram = np.eye(3)[None]+np.einsum('nki,nkj->nij', wb, wb)
        rhs = np.einsum('nki,nk->ni', wb, w)
        coefficient = np.linalg.solve(gram, rhs[..., None])[..., 0]
        quadratic -= np.sum(rhs*coefficient, axis=1)
        sign, extra_logdet = np.linalg.slogdet(gram)
        if np.any(sign <= 0):
            raise ValueError('shape covariance not positive definite')
        logdet += extra_logdet
    nll = quadratic+logdet+components['density_normalization']
    return dict(log_density=-nll/2, quadratic=quadratic, logdet=logdet,
                normalization=components['density_normalization'], geometry=geometry)


def integrate(d, components, count, include_shape):
    nodes, logweights = phase_nodes(d, count)
    values = node_log_density(d, components, nodes, include_shape)
    logterms = logweights+values['log_density']
    log_density = float(logsumexp(logterms))
    posterior = np.exp(logterms-log_density)
    mean = float(posterior@nodes)
    expected = dict(quadratic=float(posterior@values['quadratic']),
                    logdet=float(posterior@values['logdet']),
                    normalization=values['normalization'])
    phase_penalty = float(2*np.sum(posterior*(logterms-log_density-logweights)))
    score = -2*log_density
    closure = score-sum(expected.values())-phase_penalty
    if abs(closure) > 1e-6:
        raise ValueError('mixture score decomposition failed')
    return dict(objective=score, log_density=log_density, expected_node_terms=expected,
                phase_posterior_to_prior_quadrature_penalty=phase_penalty,
                decomposition_closure=closure, phase_nodes_s=nodes,
                phase_log_prior_weights=logweights, phase_posterior_weights=posterior,
                phase_conditional_mean_s=mean,
                phase_conditional_sd_s=float(np.sqrt(posterior@((nodes-mean)**2))),
                quadrature_prior_mass=float(np.exp(logsumexp(logweights))),
                minimum_node_elevation_deg=float(values['geometry']['elevation_deg'].min()),
                minimum_domain_endpoint_elevation_deg=components['domain_endpoint_min_elevation_deg'],
                node_log_density=values['log_density'], node_quadratic=values['quadratic'],
                node_logdet=values['logdet'], shape_covariance_enabled=bool(include_shape))


def build(d, arm, reference, branch, count):
    if branch not in a.BRANCHES:
        raise ValueError('unknown covariance branch')
    phase_nodes(d, count)
    # Reuse construction only, not first-order target likelihood evaluation.
    p = a.build(d, arm, reference, a.BRANCHES[0])
    p.experimental_branch = branch
    p.phase_quadrature_count = count
    def calculate(position):
        components = conditional_components(d, p, position)
        parent = dict(components['parent'])
        prediction = integrate(d, components, count, branch==a.BRANCHES[1])
        score = prediction['objective']
        if score < 0:
            raise ValueError('cannot represent negative target density cost as a residual')
        parent.update(parent_negative_twice_elbo=parent['negative_twice_elbo'],
                      parent_normalization_constant=parent['normalization_constant'],
                      nonlinear_target_prediction=prediction, nonlinear_components=components,
                      target_never_calibrates=True, target_phase_reference_frozen=True)
        parent['negative_twice_elbo'] += score
        # Complete target density is represented directly as a scalar residual;
        # its determinant and normalization are already inside score.
        parent['residual'] = np.r_[parent['residual'], np.sqrt(score)]
        return parent
    p.calculate = calculate
    def residual(position):
        c = calculate(position)
        pred = c['nonlinear_target_prediction']
        if min(pred['minimum_node_elevation_deg'], pred['minimum_domain_endpoint_elevation_deg']) < 0:
            raise ValueError('target phase-domain visibility failure; no truncation or repair authorized')
        return np.r_[c['residual'], np.maximum(0., -c['elevation'][p.keep])/2]
    p.residual = residual
    return p


def adaptive_reference(d, components, include_shape, reference_nodes=641):
    """Independent adaptive phase-space integration with likelihood-mode splits.

    Dense-rule modes only provide breakpoints and scaling. Adaptive integration
    evaluates direct propagation anew and includes every interval of the domain.
    """
    grid = np.linspace(*DOMAIN, reference_nodes)
    values = node_log_density(d, components, grid, include_shape)['log_density']
    law = prior(d); distribution = law['distribution']
    logprior = distribution.logpdf(grid)-np.log(law['interval_probability'])
    combined = values+logprior
    peaks = np.flatnonzero((combined[1:-1] >= combined[:-2]) & (combined[1:-1] >= combined[2:]))+1
    # Every coarse interval is integrated, including separated low-mass modes.
    # Nearby grid points prevent a narrow maximum from being missed by quad.
    points = sorted(set([float(grid[k]) for peak in peaks for k in
                         range(max(1, peak-2), min(len(grid)-1, peak+3))]))
    shift = float(combined.max())
    calls = [0]
    def density(phi):
        calls[0] += 1
        loglike = node_log_density(d, components, np.array([phi]), include_shape)['log_density'][0]
        return float(np.exp(loglike+distribution.logpdf(phi)-np.log(law['interval_probability'])-shift))
    integral, error, info = quad(density, *DOMAIN, points=points,
                                 epsabs=1e-10, epsrel=1e-10, limit=1000,
                                 full_output=1)[:3]
    if not integral > 0 or error/max(integral, 1e-300) > 1e-6:
        raise ValueError('adaptive reference failed tolerance')
    return dict(objective=float(-2*(shift+np.log(integral))),
                absolute_integral_error=float(error), relative_integral_error=float(error/integral),
                function_calls=calls[0], peak_phase_s=grid[peaks],
                maximum_log_integrand_shift=shift, initial_grid_points=reference_nodes,
                adaptive_subintervals=int(info['last']))
