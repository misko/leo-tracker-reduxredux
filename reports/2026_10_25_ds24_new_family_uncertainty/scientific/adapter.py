"""Predictive-only new-family covariance control, with no target calibration.

The parent curved posterior is exactly the frozen DS24 baseline construction.
Existing predictive entries and the new whole source are scored jointly under
that posterior. Target phase and physical shape uncertainty are target-local;
they never reuse dormant family slots in the parent posterior. No GPS is read.
"""

import copy
from pathlib import Path

import numpy as np
from scipy.linalg import solve_triangular

import recovery as original
from build_dsx01_orbit_modes import build_modes
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry
from dsx01_joint_marginal import integrated_gaussian
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
CASES = original.CASES
ARMS = original.ARMS
BRANCHES = ('predictive_shape_zero', 'predictive_shape_prior')


def load_context(case):
    """Safe original loader: causal TLE/prior reconstruction, no position fits."""
    if case not in CASES:
        raise ValueError('case outside frozen two-scan pilot')
    d = original.context(case)
    selected = original.read(original.HERE/'eligibility02'/case/'result.json')['selected']
    if len(selected['additions']) != 1:
        raise ValueError('one sealed whole source required')
    addition = copy.deepcopy(selected['additions'][0])
    i = next(i for i, t in enumerate(d['scan'].tracks) if t['key'] == addition['component'])
    k = next(k for k, row in enumerate(d['base'].rows) if row['component'] == addition['component'])
    j = addition['candidate_index']
    track = d['scan'].tracks[i]
    if d['keep'][d['base'].slices[k]].any():
        raise ValueError('new target already calibrates parent')
    if any(e['candidate_index'] == j for e in d['entries']):
        raise ValueError('target family already has parent predictive evidence')
    if any(row['candidate_index'] == j and d['keep'][sl].any()
           for row, sl in zip(d['base'].rows, d['base'].slices, strict=True)):
        raise ValueError('target family is not dormant in parent curved data')
    ids = list(track['observation_ids'])
    parent = original.read(original.HERE/case/'parent.json')['coverage']
    for arm in ARMS:
        if set(ids) & set(parent[arm]['accepted_observation_ids']):
            raise ValueError('target overlaps original accepted physical IDs')
    bank, metadata = build_modes(d['scan'], [j], [j], 'physical')
    sky = dict(time_s=d['scan'].sky['time_s'],
               position_km=d['scan'].sky['position_km'][[j]],
               velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
    target = dict(addition, track_index=i, row_index=k, points=len(ids),
                  observation_ids=ids, phase_mean_s=float(d['all_means'][j]),
                  phase_sd_s=float(d['widths'][j]),
                  phase_nu=d['model']['nu'],
                  phase_approximation='Gaussian with same causal Student mean and unit-marginal-variance scale',
                  target_local_shape_metadata=metadata, receiver=track['receiver'],
                  channel=track['channel'], rf_hz=track['rf_hz'])
    entry = dict(addition, track_index=i, observation_ids=ids, points=len(ids),
                 evidence_role='unqualified_experimental_predictive_factor')
    d.update(target=target, target_entry=entry, target_track=track,
             target_sky=sky, target_mode_bank=bank, saved_support=selected,
             parent_membership=parent)
    return d


def target_prediction(d, p, position):
    """Causal-mean target phase linearization; target values never enter it."""
    t, target = d['target_track'], d['target']
    times = np.asarray(t['times'])
    labels = np.zeros(len(times), int)
    phase = np.array([target['phase_mean_s']])
    coordinates = latlon(np.asarray(position)[:2])
    def frequency(offset):
        return paired_phase_frequency(d['target_sky'], times, labels,
                                      phase+offset, *coordinates)
    f, elevation = frequency(0.)
    derivative = (frequency(.01)[0]-frequency(-.01)[0])/.02
    q = t['rf_hz']/11.5e9
    shape = q*paired_frequency_modes(d['target_sky'], d['target_mode_bank'],
                                    times, labels, phase, *coordinates)
    # Reuse original hardware/smooth construction; discard every satellite and
    # fragment slot. The mean is evaluated at the causal phase mean directly.
    view, values, sigma, _, _ = linear_geometry(p, [d['target_entry']])
    radio_width = p.hardware.shape[1]+p.smooth.shape[1]
    hardware = view.hardware.copy()
    hardware[:, [4, 6]] *= 10
    shared = np.zeros((len(times), len(p.calculate_width)))
    shared[:, :radio_width] = np.column_stack((hardware, view.smooth*200))
    return dict(mean_orbit_hz=q*f, phase_column_hz=q*derivative*target['phase_sd_s'],
                shape_columns_hz=shape, elevation=elevation, shared_design=shared,
                values_hz=values, sigma_hz=sigma*np.sqrt(2),
                phase_reference_s=float(phase[0]), derivative_hz_per_s=q*derivative)


def gaussian_score(raw, features, sigma):
    """Exact normalized diagonal-plus-low-rank Gaussian objective."""
    y, u, s = np.asarray(raw, float), np.asarray(features, float), np.asarray(sigma, float)
    result = integrated_gaussian(y, u, s)
    noise_logdet = float(2*np.log(s).sum())
    normalization = float(len(y)*np.log(2*np.pi))
    result.update(noise_logdet=noise_logdet, normalization=normalization,
                  logdet=noise_logdet+result['logvolume'],
                  objective=result['quadratic']+result['logvolume']+noise_logdet+normalization,
                  normalization_constant=noise_logdet+normalization)
    return result


def joint_prediction(parent_raw, parent_design, parent_sigma, parent_groups,
                     target_raw, target_design, target_sigma, phase, shape,
                     posterior_precision, *, include_shape):
    """One shared predictive density; target is conditioned on existing entries.

    The low rank factor retains H_E V H_T' cross covariance. Original entry
    constants, target constant, phase and shape are mutually independent priors.
    The posterior of parent calibration is conditioned on curved data only.
    """
    ye, he, se, ge = (np.asarray(v) for v in
                      (parent_raw, parent_design, parent_sigma, parent_groups))
    yt, ht, st = (np.asarray(v) for v in (target_raw, target_design, target_sigma))
    root = np.linalg.cholesky(posterior_precision)
    h = np.vstack((he, ht))
    shared = solve_triangular(root, h.T, lower=True).T
    ng = int(ge.max())+1 if len(ge) else 0
    constants = np.zeros((len(h), ng+1))
    if len(ge):
        constants[np.arange(len(ge)), ge.astype(int)] = 300.
    constants[len(ye):, -1] = 300.
    local = np.zeros((len(h), 4))
    local[len(ye):, 0] = phase
    if include_shape:
        local[len(ye):, 1:] = shape
    u = np.column_stack((shared, constants, local))
    y, s = np.r_[ye, yt], np.r_[se, st]
    joint = gaussian_score(y, u, s)
    existing = (gaussian_score(ye, u[:len(ye)], se) if len(ye) else
                dict(quadratic=0., logdet=0., normalization=0., objective=0.))
    # The Schur conditional gives target diagnostics without pretending that
    # target and existing predictive factors are independent.
    covariance = np.diag(s*s)+u@u.T
    ne = len(ye)
    if ne:
        ee, et = covariance[:ne, :ne], covariance[:ne, ne:]
        re = np.linalg.cholesky(ee)
        solve_e = lambda b: solve_triangular(re.T, solve_triangular(re, b, lower=True), lower=False)
        conditional_mean = et.T@solve_e(ye)
        conditional_cov = covariance[ne:, ne:]-et.T@solve_e(et)
    else:
        conditional_mean = np.zeros(len(yt))
        conditional_cov = covariance.copy()
    conditional_cov = (conditional_cov+conditional_cov.T)/2
    rt = np.linalg.cholesky(conditional_cov)
    innovation = yt-conditional_mean
    white = solve_triangular(rt, innovation, lower=True)
    conditional = dict(quadratic=float(white@white),
                       logdet=float(2*np.log(np.diag(rt)).sum()),
                       normalization=float(len(yt)*np.log(2*np.pi)))
    conditional['objective'] = sum(conditional.values())
    closure = joint['objective']-existing['objective']-conditional['objective']
    if abs(closure) > 1e-5:
        raise ValueError('joint predictive factorization failed: '+str(closure))
    return dict(joint=joint, existing=existing, target_conditional=conditional,
                target_innovation_hz=innovation, target_whitened_innovation=white,
                target_conditional_covariance_hz2=conditional_cov,
                target_conditional_mean_update_hz=conditional_mean,
                covariance_hz2=covariance, features=u, raw_hz=y, sigma_hz=s,
                shared_design=h, posterior_precision=posterior_precision,
                target_local_design=local[ne:], closure=closure,
                parent_predictive_points=ne)


def build(d, arm, reference, branch):
    if arm not in ARMS or branch not in BRANCHES:
        raise ValueError('unfrozen arm or covariance branch')
    p = original.build(d, arm, np.asarray(reference))
    parent_calculate = p.calculate
    curved = p.curved_calculate if d['entries'] else p.calculate
    width = p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)+3*len(p.supported)+len(p.members)
    p.calculate_width = np.arange(width)
    if d['entries']:
        view, values, sigma, groups, slices = linear_geometry(p, d['entries'])
    else:
        view, values, sigma, groups, slices = None, np.empty(0), np.empty(0), np.empty(0, int), []
    p.original_parent_calculate = parent_calculate
    p.parent_curved_calculate = curved
    p.experimental_branch = branch
    p.experimental_target = d['target']
    def calculate(position):
        # Original 0095 has no predictive entries and uses an lru-cached dict.
        # Never mutate that parent object when appending a new likelihood term.
        c = dict(curved(position))
        g = p.noise_groups[p.keep]
        weights = d['powers'][g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        train = c['features'][p.keep]
        gram = np.diag(c['coefficient_prior_precision'])+train.T@(train*weights[:, None])
        if view is not None:
            geometry = geometry_features(view, position, 0.)
            he = geometry['features']
            mean = view.q*geometry['intercept']+he@c['coefficient']
            raw = values-mean
            existing_elevation = geometry['elevation']
        else:
            he, raw, existing_elevation = np.empty((0, width)), np.empty(0), np.empty(0)
        target = target_prediction(d, p, position)
        ht = target['shared_design']
        target_raw = target['values_hz']-target['mean_orbit_hz']-ht@c['coefficient']
        prediction = joint_prediction(raw, he, sigma*np.sqrt(2), groups,
            target_raw, ht, target['sigma_hz'], target['phase_column_hz'],
            target['shape_columns_hz'], gram, include_shape=branch==BRANCHES[1])
        old = prediction['existing']; joint = prediction['joint']
        c['curved_negative_twice_elbo'] = c['negative_twice_elbo']
        c['parent_negative_twice_elbo'] = c['negative_twice_elbo']+old['objective']
        c['negative_twice_elbo'] += joint['objective']
        c['normalization_constant'] += joint['normalization_constant']
        c['residual'] = np.r_[c['residual'], joint['residual']]
        c.update(linear_predictive_objective=joint['objective'],
                 linear_raw_prediction_residual_hz=raw, linear_elevation=existing_elevation,
                 target_raw_prediction_residual_hz=target_raw, target_elevation=target['elevation'],
                 target_prediction=target, predictive_decomposition=prediction,
                 target_phase_reference_frozen=True, target_never_calibrates=True)
        return c
    p.calculate = calculate
    # Original residual uses parent curved visibility; add the target's actual
    # visibility penalty explicitly. Existing entry gates remain reporter-owned.
    def residual(position):
        c = calculate(position)
        return np.r_[c['residual'], np.maximum(0., -c['elevation'][p.keep])/2,
                     np.maximum(0., -c['target_elevation'])/2]
    p.residual = residual
    return p


def shape_projection(columns, phase):
    b, phase = np.asarray(columns), np.asarray(phase)
    design = np.column_stack((np.ones(len(phase)), phase))
    centered = b-b.mean(axis=0)
    after = b-design@np.linalg.lstsq(design, b, rcond=None)[0]
    return dict(point_prior_sd_hz_min_median_max=np.quantile(np.linalg.norm(b, axis=1), [0, .5, 1]),
                path_mean_prior_sd_hz=float(np.linalg.norm(b.mean(axis=0))),
                centered_RMS_prior_sd_hz=float(np.sqrt(np.mean(np.sum(centered**2, axis=1)))),
                after_constant_phase_projection_RMS_prior_sd_hz=float(np.sqrt(np.mean(np.sum(after**2, axis=1)))),
                engineering_prior_only_not_measured_or_calibrated=True)


def diagnostic_record(p, position):
    """RF export only, with parent and target score contributions kept distinct."""
    x = np.asarray(position)
    c = p.calculate(x)
    pred = c['predictive_decomposition']
    target = c['target_prediction']
    visibility = float(np.sum((np.maximum(0., -c['elevation'][p.keep])/2)**2)
                       + np.sum((np.maximum(0., -c['target_elevation'])/2)**2))
    return dict(position_east_north_km=x,
                negative_twice_elbo=c['negative_twice_elbo'],
                curved_negative_twice_elbo=c['curved_negative_twice_elbo'],
                parent_negative_twice_elbo=c['parent_negative_twice_elbo'],
                actual_optimizer_scalar=float(c['residual']@c['residual'])+visibility,
                normalization_constant=c['normalization_constant'], visibility_penalty=visibility,
                joint_predictive={k:pred['joint'][k] for k in ('objective', 'quadratic', 'logdet', 'normalization')},
                existing_predictive={k:pred['existing'][k] for k in ('objective', 'quadratic', 'logdet', 'normalization')},
                target_conditional=pred['target_conditional'],
                target_raw_residual_hz=c['target_raw_prediction_residual_hz'],
                target_innovation_hz=pred['target_innovation_hz'],
                target_whitened_innovation=pred['target_whitened_innovation'],
                target_conditional_sd_hz=np.sqrt(np.diag(pred['target_conditional_covariance_hz2'])),
                target_covariance_hz2=pred['target_conditional_covariance_hz2'],
                target_orbit_mean_hz=target['mean_orbit_hz'],
                target_phase_column_hz=target['phase_column_hz'],
                target_shape_columns_hz=target['shape_columns_hz'],
                target_shape_prior_projection=shape_projection(target['shape_columns_hz'], target['phase_column_hz']),
                parent_noise_precision=c['noise_precision'],
                parent_coefficient=c['coefficient'],
                parent_prior_precision=c['coefficient_prior_precision'],
                final_log_precision_change=c['final_log_precision_change'],
                target_evidence_role='unqualified_experimental_predictive_factor',
                target_association_qualified=False, operational_policy='saved_baseline')
