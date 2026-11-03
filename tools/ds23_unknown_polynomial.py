"""A proper observed-CFO polynomial alternative to a named satellite family.

Every original position factor is scored on its original, fixed alias branch.
Unknown curves are independent observed-frequency processes; they do not teach
receiver calibration. Fractional powers retain the incumbent generalized-
evidence interpretation. This is not a calibrated identity probability.
"""

import numpy as np
from scipy.special import logsumexp

from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_frozen_precision import conditional_gaussian
from ds23_height_problem import geometry_features
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_receiver_smooth_prior import scale_posterior
from leo.analysis.research.retained_track_likelihood import PERIOD

DEGREE_PRIOR = np.array([.5, .25, .125, .125])
COEFFICIENT_SIGMA_HZ = PERIOD * np.array([4., 4., 2., 1., 1.])
UNKNOWN_PROBABILITY = .05


def polynomial_density(times, values, sigma, power=1., predictive=False):
    """Normalized degree-mixture evidence with fixed scan-time coordinates.

    Noise matches the original channel: Gamma(2,2) for curved calibration
    factors; fixed sqrt(2) predictive noise for the original linear factors.
    Polynomial coefficients are integrated with zero-centered Gaussian priors.
    No fitted curve, measured CFO or GPS is used to center those priors.
    """
    t, y = np.asarray(times, float), np.asarray(values, float)
    s = np.broadcast_to(np.asarray(sigma, float), y.shape)
    if t.shape != y.shape or y.ndim != 1 or not len(y) or not np.isfinite(t).all():
        raise ValueError('nonempty matching finite times and frequencies required')
    if not np.isfinite(y).all() or not np.isfinite(s).all() or np.any(s <= 0):
        raise ValueError('finite values and positive noise required')
    if not np.isfinite(power) or not 0 < power <= 1 or (predictive and power != 1):
        raise ValueError('fixed curved power in (0,1], predictive power exactly one required')
    basis = np.polynomial.polynomial.polyvander((t-150.)/150., 4)*COEFFICIENT_SIGMA_HZ
    degrees = []
    for degree in range(1, 5):
        u = basis[:, :degree+1]
        if predictive:
            result = conditional_gaussian(y, u, s*np.sqrt(2), np.ones(len(y)),
                np.ones(len(y)), np.ones(degree+1), 1.)
        else:
            result = hierarchical_bound(y, u, s, np.zeros(len(y), int), powers=power)
        degrees.append(dict(degree=degree, negative_twice_elbo=result['negative_twice_elbo'],
            precision_change=result.get('final_log_precision_change', 0.),
            RMS_hz=float(np.sqrt(np.mean((y-u@result['coefficient'])**2)))))
    log_weights = np.log(DEGREE_PRIOR)-.5*np.array([r['negative_twice_elbo'] for r in degrees])
    return dict(negative_twice_elbo=float(-2*logsumexp(log_weights)), degrees=degrees,
        degree_posterior=(np.exp(log_weights-logsumexp(log_weights))).tolist(),
        points=len(y), predictive=predictive, power=float(power))


def phase_prior_groups(width, begin, count, active_local_labels, nu):
    """Unobserved independent priors integrate to one, with no mean-field gap."""
    groups = np.full(width, -1, int)
    active = np.asarray(active_local_labels, int)
    if np.any(active < 0) or np.any(active >= count):
        raise ValueError('phase index out of range')
    if nu is not None:
        groups[begin+active] = np.arange(len(active))
    return groups


def family_partition(p, original, entries, unknown):
    original = np.asarray(original, bool)
    labels = np.asarray(p.labels)[p.flat_labels]
    mask = original & ~np.isin(labels, list(unknown))
    known_entries = [e for e in entries if e['candidate_index'] not in unknown]
    return mask, known_entries


def unknown_ledger(p, original, entries, powers):
    """Score each potential unknown fragment once, independent of position."""
    result = {}
    original = np.asarray(original, bool)
    for k, (row, i, sl) in enumerate(zip(p.rows, p.members, p.slices, strict=True)):
        use = original[sl]
        if not use.any():
            continue
        t = p.scan.tracks[i]
        density = polynomial_density(t['times'][use], p.values[sl][use], p.point_noise[sl][use], powers[k])
        result.setdefault(row['candidate_index'], []).append(dict(component=t['key'], kind='curved',
            observation_ids=np.asarray(t['observation_ids'])[use].tolist(), **density))
    meta = p.scan.fixed_window_noise
    noise = meta['per_observation_noise_sigma_hz']
    for entry in entries:
        t = p.scan.tracks[entry['track_index']]
        if set(entry['observation_ids']) != set(t['observation_ids']) or entry['points'] != len(t['times']):
            raise ValueError('predictive fragment ownership differs from original track')
        sigma = np.array([noise[oid] if meta['extra_parameter_BIC_gain'] > 0 else p.scan.radio_sigma_hz
                          for oid in t['observation_ids']])
        density = polynomial_density(t['times'], t['values']+entry['alias']*PERIOD, sigma, predictive=True)
        result.setdefault(entry['candidate_index'], []).append(dict(component=t['key'], kind='predictive',
            observation_ids=list(t['observation_ids']), **density))
    ids = [oid for rows in result.values() for row in rows for oid in row['observation_ids']]
    if len(ids) != len(set(ids)):
        raise ValueError('original position evidence has repeated measurement ownership')
    return result


def make_unknown_problem(scan, node, original, arm, reference, powers, means, model,
                         entries, unknown, ledger):
    """Known satellite factors plus a proper density for every unknown point."""
    p = make_event_problem(scan,node,original,arm,reference,powers,means,model,[])
    unknown = set(unknown)
    keep, known_entries = family_partition(p,original,entries,unknown)
    if not keep.any():
        raise ValueError('unknown model needs retained physical observations')
    p.keep = keep
    begin = p.hardware.shape[1]+p.smooth.shape[1]
    width = begin+len(p.labels)+3*len(p.supported)+len(p.members)
    active = np.unique(p.flat_labels[keep])
    groups = phase_prior_groups(width,begin,len(p.labels),active,model['nu'])
    mean = np.zeros(width);mean[begin:begin+len(p.labels)] = means/p.phase_sigma
    scale = np.ones(width);scale[-len(p.members):] = .3
    unknown_rows = [r for j in sorted(unknown) for r in ledger[j]]
    unknown_cost = sum(r['negative_twice_elbo'] for r in unknown_rows)
    code = 2*len(unknown)*np.log((1-UNKNOWN_PROBABILITY)/UNKNOWN_PROBABILITY)
    def calculate(position):
        geometry = geometry_features(p,position,0.)
        features = geometry['features']
        raw = p.values-p.q*geometry['intercept']-features@mean
        present = np.unique(p.noise_groups[keep])
        bound = hierarchical_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=np.asarray(powers)[present],prior_groups=groups,prior_nu=4 if model['nu'] is None else model['nu'])
        bound = scale_posterior(bound,scale)
        bound['latent_coefficient'] = bound['coefficient'].copy();bound['coefficient'] += mean
        precision = np.zeros(len(p.members));precision[present] = bound['noise_precision'];bound['noise_precision'] = precision
        bound['conditional_residual_hz'] = p.values-p.q*geometry['intercept']-features@bound['coefficient']
        volume = float(2*np.sum(np.asarray(powers)[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound['residual'] = np.r_[bound['residual'],np.sqrt(volume)]
        # Constants do not affect position descent, but do enter every cross-
        # hypothesis comparison. This preserves the full observation measure.
        bound['normalization_constant'] += unknown_cost+code
        bound['negative_twice_elbo'] += unknown_cost+code
        geometry.update(bound, unknown_density_cost=unknown_cost, unknown_discrete_code=code)
        return geometry
    p.calculate = calculate
    attach_event_predictive(p,known_entries,powers)
    p.unknown_families = sorted(unknown)
    p.unknown_rows = unknown_rows
    p.known_entries = known_entries
    p.active_phase_local = active
    p.original_position_points = int(np.sum(original))+sum(e['points'] for e in entries)
    counted = int(np.sum(keep))+sum(e['points'] for e in known_entries)+sum(r['points'] for r in unknown_rows)
    if counted != p.original_position_points:
        raise ValueError('satellite/unknown model lost original evidence')
    return p


def unobserved_student_gap(nu):
    """Compute the old zero-design Gaussian/Gamma gap; no data are fitted."""
    if nu is None:
        return 0.
    args = (np.zeros(1), np.zeros((1,1)), np.ones(1), np.zeros(1,int))
    old = hierarchical_bound(*args,prior_groups=np.zeros(1,int),prior_nu=nu)
    collapsed = hierarchical_bound(*args,prior_nu=nu)
    return float(old['negative_twice_elbo']-collapsed['negative_twice_elbo'])
