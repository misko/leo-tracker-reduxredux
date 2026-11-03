"""Uncertainty-aware catalogue proposals after excluding entire family sets.

These are conditional Gaussian proposal densities, not final identity odds.
Shared radio covariance is learned without any proposed family's observations.
"""

import copy
import numpy as np

from leo.analysis.research.orbit_phase_geometry import phase_shifted_states
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.sky.frames import geodetic_to_ecef_km


def gaussian_candidates(raw, modes, covariance):
    """Exact C + UU' Gaussian integration, batched over candidate satellites."""
    r, u, covariance = map(lambda a: np.asarray(a, float), (raw, modes, covariance))
    if r.ndim != 2 or u.ndim != 3 or u.shape[:2] != r.shape or covariance.shape != (r.shape[1], r.shape[1]):
        raise ValueError('matching candidate residuals, modes and common covariance required')
    if not all(np.isfinite(a).all() for a in (r, u, covariance)):
        raise ValueError('finite Gaussian proposal arrays required')
    count, points = r.shape
    root = np.linalg.cholesky((covariance+covariance.T)/2)
    white = np.linalg.solve(root, r.T).T
    transform = np.linalg.solve(root, u.transpose(1, 0, 2).reshape(points, -1))
    transform = transform.reshape(points, count, u.shape[2]).transpose(1, 0, 2)
    gram = np.eye(u.shape[2])[None] + np.einsum('cni,cnj->cij', transform, transform)
    rhs = np.einsum('cni,cn->ci', transform, white)
    factor = np.linalg.cholesky(gram)
    coefficient = np.linalg.solve(factor.swapaxes(-1, -2), np.linalg.solve(factor, rhs[..., None]))[..., 0]
    cost = (np.sum(white**2, axis=1) - np.sum(rhs*coefficient, axis=1) +
        2*np.log(np.diagonal(factor, axis1=-2, axis2=-1)).sum(axis=1) +
        2*np.log(np.diag(root)).sum() + points*np.log(2*np.pi))
    return dict(cost=cost, coefficient=coefficient)


def propose_aliases(observed, predicted, groups, covariance):
    y, f, groups = np.asarray(observed), np.asarray(predicted), np.asarray(groups)
    if y.ndim != 1 or f.ndim != 2 or f.shape[1] != len(y) or groups.shape != y.shape:
        raise ValueError('matching track groups and candidate predictions required')
    aliases = np.zeros((len(f), int(groups.max())+1), int)
    weights = 1/np.diag(covariance)
    for k in range(aliases.shape[1]):
        use = groups == k
        aliases[:, k] = np.rint(((f[:, use]-y[use])@weights[use])/weights[use].sum()/PERIOD).astype(int)
    return aliases, y[None]+PERIOD*aliases[:, groups]-f


def orbit_frequency_modes(bank, mode_bank, times, phases, location):
    """Same physical Doppler derivative as paired_frequency_modes, all candidates."""
    phases = np.asarray(phases)
    position, velocity = phase_shifted_states(bank, times, phases)
    dp, dv = phase_shifted_states(mode_bank, times, np.repeat(phases, 3))
    count, points = position.shape[:2]
    dp = dp.reshape(count, 3, points, 3).transpose(0, 2, 1, 3)
    dv = dv.reshape(count, 3, points, 3).transpose(0, 2, 1, 3)
    line = position-geodetic_to_ecef_km(*location, 0.)
    distance = np.linalg.norm(line, axis=2)
    direction = line/distance[..., None]
    rate = np.sum(direction*velocity, axis=2)
    gradient = (velocity-rate[..., None]*direction)/distance[..., None]
    return -11.5e9/299792.458*(np.einsum('cni,cnki->cnk', gradient, dp)+
        np.einsum('cni,cnki->cnk', direction, dv))


def choose_families(p, position, minimum_points=24, maximum=2):
    c = p.calculate(position)
    phase_begin = p.hardware.shape[1]+p.smooth.shape[1]
    orbit_begin = phase_begin+len(p.labels)
    rows = []
    for local, j in enumerate(p.labels):
        owners, points = set(), 0
        for row, i, sl in zip(p.rows, p.members, p.slices, strict=True):
            if row['candidate_index'] == j and p.keep[sl].any():
                t = p.scan.tracks[i]
                owners.add((t['receiver'], t['channel']))
                points += int(p.keep[sl].sum())
        if points < minimum_points or len(owners) < 2:
            continue
        pull = float(c['latent_coefficient'][phase_begin+local]**2)
        if j in p.supported:
            k = p.supported.index(j)
            pull += float(np.sum(c['coefficient'][orbit_begin+3*k:orbit_begin+3*k+3]**2))
        rows.append(dict(candidate_index=j, norad=int(p.scan.norads[j]),
            prior_pull=pull, points=points, lanes=sorted(owners)))
    return sorted(rows, key=lambda r: (-r['prior_pull'], r['candidate_index']))[:maximum]


def apply_changes(node, entries, choices):
    """Apply every nomination simultaneously; labels must never cascade."""
    changed, predictive = copy.deepcopy(node), copy.deepcopy(entries)
    seen = set()
    for choice in choices:
        for change in choice['changes']:
            kind, k = change['kind'], int(change['index'])
            key = (kind, k)
            if kind not in ('curve', 'linear') or key in seen:
                raise ValueError('unknown or overlapping nomination changes')
            seen.add(key)
            original = node['seed']['rows'][k] if kind == 'curve' else entries[k]
            if original['candidate_index'] != change['original_index']:
                raise ValueError('nomination does not match the original family')
            target = changed['seed']['rows'][k] if kind == 'curve' else predictive[k]
            target['candidate_index'] = int(change['candidate_index'])
            if kind == 'curve':
                target['candidate_norad'] = int(change['norad'])
                changed['aliases'][k] = int(change['alias'])
            else:
                target.update(norad=int(change['norad']), alias=int(change['alias']))
    return changed, predictive
