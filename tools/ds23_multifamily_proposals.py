"""Multiple-family deletion proposals and fixed-position cross-family scoring.

The score is a sum of moment-matched Gaussian leave-family-out predictive
densities, not a joint likelihood or an identity posterior. No GPS enters here.
"""

import hashlib
import numpy as np

from ds23_family_predictive_selection import gaussian_predictive
from ds23_frequency_events import make_event_problem
from probe_ds23_frequency_events import cached


def subsets(case, families, count=6):
    labels = np.unique(np.asarray(families, int))
    if len(labels) < 6:
        return []
    seed = int.from_bytes(hashlib.sha256(('multifamily-v1/' + case).encode()).digest()[:8], 'little')
    rng = np.random.default_rng(seed)
    size = max(4, (len(labels) + 1) // 2)
    result = []
    for _ in range(500):
        candidate = sorted(rng.choice(labels, size, replace=False).tolist())
        if candidate not in result:
            result.append(candidate)
        if len(result) == count:
            return result
    raise ValueError('failed to construct the declared number of distinct subsets')


def family_masks(labels, original, training_families):
    labels, original = np.asarray(labels), np.asarray(original, bool)
    if labels.ndim != 1 or labels.shape != original.shape:
        raise ValueError('matching labels and original observation mask required')
    return original & np.isin(labels, np.asarray(training_families))


def prediction(p, x, train, test, family, powers):
    """Full coefficient covariance at fixed candidate position, with unseen noise."""
    if np.any(train & test) or not train.any() or not test.any():
        raise ValueError('nonempty disjoint train and test masks required')
    labels = np.asarray(p.labels)[p.flat_labels]
    if np.any(labels[train] == family) or np.any(labels[test] != family):
        raise ValueError('held satellite leaked into calibration or test family changed')
    c = p.calculate(x)
    precision = c['coefficient_prior_precision'].copy()
    begin = p.hardware.shape[1] + p.smooth.shape[1]
    # Restore the held Student phase's prior marginal variance, rather than
    # treat its unobserved variational expected precision as information.
    precision[begin + p.labels.index(family)] = 1.
    weights = np.asarray(powers)[p.noise_groups[train]] * c['noise_precision'][p.noise_groups[train]] / p.point_noise[train]**2
    result = gaussian_predictive(c['conditional_residual_hz'][test], c['features'][test],
        c['features'][train], weights, precision,
        p.point_noise[test] * np.sqrt(2 / np.asarray(powers)[p.noise_groups[test]]))
    result.update(position_covariance_included=False, position_is_fixed_candidate=True)
    return result


def score_position(scan, node, original, arm, powers, means, model, x):
    """Score every active curved observation once, outside its family training."""
    reference = np.zeros(len(means))
    base = cached(make_event_problem(scan, node, original, arm, reference, powers, means, model, []))
    labels = np.asarray(base.labels)[base.flat_labels]
    families = np.unique(labels[original])
    rows = []
    for family in families:
        train, test = original & (labels != family), original & (labels == family)
        reference = np.zeros(len(means))
        for _ in range(5):
            p = cached(make_event_problem(scan, node, train, arm, reference, powers, means, model, []))
            phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
            change = float(np.max(abs(phase - p.reference)))
            reference = phase
        predictive = prediction(p, x, train, test, int(family), powers)
        rows.append(dict(norad=int(scan.norads[family]), family=int(family), points=int(test.sum()),
            phase_change_s=change, negative_twice_log_density=predictive['negative_twice_log_density'],
            RMS_hz=predictive['RMS_hz'], maximum_sigma_hz=float(predictive['marginal_sigma_hz'].max())))
    if sum(r['points'] for r in rows) != int(original.sum()):
        raise ValueError('cross-family score did not cover every original curved point exactly once')
    return dict(score=float(sum(r['negative_twice_log_density'] for r in rows)), folds=rows,
        qualified=all(r['phase_change_s'] <= .01 for r in rows),
        scored_original_curved_points=int(original.sum()), no_held_family_in_calibration=True,
        approximation='local moment-matched Gaussian predictive composite score; fixed position, unseen Gamma noise')
