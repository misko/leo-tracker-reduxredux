"""Small, dense reference calculation for synthetic shared-intercept tests.

This deliberately does no pruning and imports no positioning implementation.
Candidate training logs include their priors; test logs do not.
"""

import numpy as np
from scipy.special import logsumexp

PERIOD_HZ = 1 / 4.4e-6


def dense_group_score(train, test, null_train, null_test, offsets, groups,
                      sigma=3000.0, outlier=0.05, size=512):
    grid = np.arange(size) * PERIOD_HZ / size
    training_rows, joint_rows = [], []
    for tr, te, nt, ne, means in zip(train, test, null_train, null_test, offsets, strict=True):
        difference = (np.asarray(means)[:, None] - grid + PERIOD_HZ / 2) % PERIOD_HZ
        difference -= PERIOD_HZ / 2
        # The explicit Gaussian density sum is independent of the production helper.
        radius = int(np.ceil(9 * sigma / PERIOD_HZ)) + 2
        density = sum(
            np.exp(-((difference + k * PERIOD_HZ) / sigma) ** 2 / 2)
            for k in range(-radius, radius + 1)
        ) / (np.sqrt(2 * np.pi) * sigma)
        factor = PERIOD_HZ * (1-outlier) * density + outlier
        signal = np.asarray(tr)[:, None] + np.log(factor)
        training_rows.append(np.logaddexp(logsumexp(signal, axis=0), nt))
        joint_rows.append(np.logaddexp(
            logsumexp(signal + np.asarray(te)[:, None], axis=0), nt + ne))
    training, joint = 0.0, 0.0
    groups = np.asarray(groups)
    for group in np.unique(groups):
        selected = groups == group
        training += logsumexp(np.sum(np.asarray(training_rows)[selected], axis=0)) - np.log(size)
        joint += logsumexp(np.sum(np.asarray(joint_rows)[selected], axis=0)) - np.log(size)
    return float(training), float(joint-training)


def synthetic_scene(position):
    """Eight tracks, two receiver offsets, three candidates; no real-site input."""
    truth = np.array([0.4, -0.7])
    times = np.linspace(-0.5, 0.5, 31)
    blocks = np.array_split(np.arange(len(times)), 5)
    mask = np.zeros(len(times), dtype=bool)
    mask[np.concatenate([blocks[k] for k in (0, 2, 4)])] = True
    train, test, null_train, null_test, offsets, groups = [], [], [], [], [], []
    for track in range(8):
        angle = (track % 4) * np.pi / 2
        direction = np.array([np.cos(angle), np.sin(angle)])
        group = track // 4
        intercept = [-38000., -31000.][group] + (track-4)*PERIOD_HZ

        def curve(point, direction=direction, angle=angle):
            projection = np.dot(point, direction)
            return 10000*projection + (3000*np.sin(angle+0.3)+80*projection)*times

        observed = curve(truth) + intercept
        prediction = curve(position)
        candidates = np.array([prediction, prediction+20000+2000*times,
                               prediction-30000-2000*times+500*times**2])
        residual = observed - candidates
        means = residual[:, mask].mean(axis=1)
        centered = residual-means[:, None]
        shape_train = -3*np.mean(centered[:, mask]**2, axis=1)/250**2-6*np.log(250)
        shape_test = -3*np.mean(centered[:, ~mask]**2, axis=1)/250**2-6*np.log(250)
        null_residual = observed-observed[mask].mean()
        train.append(shape_train + np.log(0.5/100))  # Full catalogue, three evaluated candidates.
        test.append(shape_test)
        null_train.append(-3*np.mean(null_residual[mask]**2)/30000**2-6*np.log(30000)+np.log(0.5))
        null_test.append(-3*np.mean(null_residual[~mask]**2)/30000**2-6*np.log(30000))
        offsets.append(means)
        groups.append(group)
    return train, test, null_train, null_test, offsets, groups
