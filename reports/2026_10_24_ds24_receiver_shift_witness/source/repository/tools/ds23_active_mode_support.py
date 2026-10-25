"""Preserve incumbent orbit support; simplify newly active one-owner families.

Do not retain three orbital-shape coordinates based only on masked-out owners.
All incumbent curved/predictive coordinates keep their original definition.
"""

import numpy as np

from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from investigate_algo01_ds23_0217 import problem
from probe_ds23_receiver_smooth_prior import scale_posterior


def disabled_families(supported, rows, slices, members, tracks, keep, protected):
    owners = {}
    for row, sl, i in zip(rows, slices, members, strict=True):
        if np.asarray(keep[sl]).any():
            owners.setdefault(row['candidate_index'], set()).add((tracks[i]['receiver'], tracks[i]['channel']))
    return [j for j in supported if j not in protected and 0 < len(owners.get(j, ())) < 2]


def make_problem(scan, node, keep, arm, reference, powers, means, model, protected):
    p = problem(scan, node, arm, keep, reference)
    disabled = disabled_families(p.supported, p.rows, p.slices, p.members, scan.tracks, keep, protected)
    p.supported = [j for j in p.supported if j not in disabled]
    p.supported_local = [p.labels.index(j) for j in p.supported]
    p.phase_sigma *= model['multiplier']
    begin = p.hardware.shape[1]+p.smooth.shape[1]
    width = begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean = np.zeros(width)
    mean[begin:begin+len(p.labels)] = means/p.phase_sigma
    groups = np.full(width, -1, int)
    if model['nu'] is not None:
        groups[begin:begin+len(p.labels)] = np.arange(len(p.labels))
    def calculate(x):
        result = JointMarginal.calculate(p, x)
        features = result['features']
        scale = np.ones(width)
        scale[-len(p.members):] = .3
        raw = p.values-p.q*result['intercept']-features@mean
        present = np.unique(p.noise_groups[keep])
        bound = hierarchical_bound(raw[keep], (features*scale)[keep], p.point_noise[keep], p.noise_groups[keep],
                                    powers=np.asarray(powers)[present], prior_groups=None if model['nu'] is None else groups,
                                    prior_nu=model['nu'] or 4.)
        bound = scale_posterior(bound, scale)
        bound['latent_coefficient'] = bound['coefficient'].copy()
        bound['coefficient'] += mean
        precision = np.zeros(len(p.members))
        precision[present] = bound['noise_precision']
        bound['noise_precision'] = precision
        bound['conditional_residual_hz'] = p.values-p.q*result['intercept']-features@bound['coefficient']
        volume = float(2*np.sum(np.asarray(powers)[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound['residual'] = np.r_[bound['residual'], np.sqrt(volume)]
        result.update(bound)
        return result
    p.calculate = calculate
    p.events = []
    p.disabled_new_one_owner_orbit_families = disabled
    return p
