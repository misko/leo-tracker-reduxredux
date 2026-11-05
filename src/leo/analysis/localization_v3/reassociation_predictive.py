"""Frozen grouped alias/phase predictive evidence for final reassociation."""

import numpy as np
from scipy.special import logsumexp

from leo.analysis.research.retained_track_likelihood import PERIOD

SCREEN_SEED = 20261103
GUARD_SEED = 20261111


def masks(times, groups, unique=False):
    blocks = np.floor(times / 5).astype(int)
    available = np.unique(blocks)
    rng = np.random.default_rng(SCREEN_SEED)
    result = []
    seen = set()
    for fold in range(5):
        for _retry in range(2000):
            held = np.sort(
                rng.choice(available, max(1, round(0.2 * len(available))), replace=False)
            )
            if unique and tuple(held) in seen:
                continue
            test = np.isin(blocks, held)
            train = ~np.isin(blocks, np.r_[held - 1, held, held + 1])
            if all(
                sum(train & (groups == g)) >= 5 and sum(test & (groups == g)) >= 2
                for g in np.unique(groups)
            ):
                break
        else:
            return []
        seen.add(tuple(held))
        result.append(dict(fold=fold, train=train, test=test, held_blocks=held, retries=_retry))
    return result


def fit_predict(raw, t, q, groups, train, test, phase):
    unique = np.unique(groups)
    lift = raw.copy()
    aliases = np.zeros((len(phase), len(unique)), int)
    for k, g in enumerate(unique):
        m = (groups == g) & train
        if not m.any():
            raise ValueError("every source needs training evidence for its alias")
        aliases[:, k] = np.rint(-raw[:, m].mean(axis=1) / PERIOD).astype(int)
        lift[:, groups == g] += aliases[:, k, None] * PERIOD
    design = (
        np.column_stack([(groups == g) * 300.0 for g in unique] + [q * (t - 150) * 0.5]) / 150.0
    )
    u = design[train]
    cov = np.linalg.inv(np.eye(u.shape[1]) + u.T @ u)
    beta = lift[:, train] / 150.0 @ u @ cov
    residual = lift / 150.0 - beta @ design.T
    train_cost = (
        np.sum(residual[:, train] ** 2, axis=1)
        + np.sum(beta**2, axis=1)
        + np.linalg.slogdet(np.eye(u.shape[1]) + u.T @ u)[1]
        + train.sum() * np.log(2 * np.pi * 150**2)
    )
    logprior = -0.5 * (phase / 5.0) ** 2
    logprior -= logsumexp(logprior)
    logpost = logprior - 0.5 * train_cost
    train_evidence = -2 * logsumexp(logpost)
    logpost -= logsumexp(logpost)
    v = design[test]
    vgram = np.eye(v.shape[1]) + cov @ v.T @ v
    a = residual[:, test]
    correction = np.linalg.solve(np.linalg.inv(cov) + v.T @ v, np.eye(cov.shape[0]))
    quad = np.sum(a * a, axis=1) - np.einsum("ij,jk,ik->i", a @ v, correction, a @ v)
    test_cost = quad + np.linalg.slogdet(vgram)[1] + test.sum() * np.log(2 * np.pi * 150**2)
    predictive = -2 * logsumexp(logpost - 0.5 * test_cost)
    k = int(np.argmax(logpost))
    return dict(
        training_score=float(train_evidence),
        predictive_score=float(predictive),
        phase_map_s=float(phase[k]),
        training_track_cost={
            int(g): float(np.sum(residual[k, (groups == g) & train] ** 2)) for g in unique
        },
        alias_by_group=dict(zip(map(int, unique), map(int, aliases[k]), strict=True)),
    )


def partitions(t, groups, count=10):
    """Unique synchronized 5 s groups, one adjacent group guarded each side."""
    blocks = np.floor(t / 5).astype(int)
    available = np.unique(blocks)
    rng = np.random.default_rng(GUARD_SEED)
    seen = set()
    splits = []
    for fold in range(count):
        for _retry in range(10000):
            held = np.sort(
                rng.choice(available, max(1, round(0.2 * len(available))), replace=False)
            )
            key = tuple(held)
            if key in seen:
                continue
            test = np.isin(blocks, held)
            guard = np.unique(np.r_[held - 1, held, held + 1])
            train = ~np.isin(blocks, guard)
            if all(
                np.sum(train & (groups == g)) >= 5 and np.sum(test & (groups == g)) >= 2
                for g in np.unique(groups)
            ):
                break
        else:
            break
        seen.add(key)
        splits.append(
            dict(
                fold=fold,
                held_blocks=held,
                guard_blocks=guard,
                train=train,
                test=test,
                retries=_retry,
            )
        )
    return splits


def predict(raw, t, q, groups, rx, train, test, phase, model, phase_sd):
    """Normalized Gaussian phase-mixture predictive score with fixed priors.

    track_offset matches the sealed reduced predictive discrepancy model.
    receiver_offset instead ties the constant across a receiver's tracks.
    frozen_radio has only the common rate discrepancy, no new constant.
    """
    lift = raw.copy()
    aliases = []
    for g in np.unique(groups):
        m = (groups == g) & train
        alias = np.rint(-raw[:, m].mean(axis=1) / PERIOD).astype(int)
        lift[:, groups == g] += alias[:, None] * PERIOD
        aliases.append(alias)
    if model == "track_offset":
        constants = [(groups == g) * 300.0 for g in np.unique(groups)]
    elif model == "receiver_offset":
        constants = [(rx == r) * 300.0 for r in np.unique(rx)]
    elif model == "frozen_radio":
        constants = []
    else:
        raise ValueError(model)
    design = np.column_stack(constants + [q * (t - 150.0) * 0.5]) / 150.0
    u = design[train]
    precision = np.eye(u.shape[1]) + u.T @ u
    cov = np.linalg.inv(precision)
    beta = lift[:, train] / 150.0 @ u @ cov
    residual = lift / 150.0 - beta @ design.T
    train_cost = (
        np.sum(residual[:, train] ** 2, axis=1)
        + np.sum(beta**2, axis=1)
        + np.linalg.slogdet(precision)[1]
        + train.sum() * np.log(2 * np.pi * 150**2)
    )
    logprior = -0.5 * (phase / phase_sd) ** 2
    logprior -= logsumexp(logprior)
    logpost = logprior - 0.5 * train_cost
    training = -2 * logsumexp(logpost)
    logpost -= logsumexp(logpost)
    v = design[test]
    a = residual[:, test]
    correction = np.linalg.inv(precision + v.T @ v)
    quad = np.sum(a * a, axis=1) - np.einsum("ij,jk,ik->i", a @ v, correction, a @ v)
    test_cost = (
        quad
        + np.linalg.slogdet(np.eye(v.shape[1]) + cov @ v.T @ v)[1]
        + test.sum() * np.log(2 * np.pi * 150**2)
    )
    best = int(np.argmax(logpost))
    return dict(
        training_score=float(training),
        predictive_score=float(-2 * logsumexp(logpost - 0.5 * test_cost)),
        phase_map_s=float(phase[best]),
        phase_edge_mass=float(np.exp(logpost[np.abs(phase) >= 29.6]).sum()),
        aliases=[int(x[best]) for x in aliases],
        coefficient=beta[best],
        held_rms_hz=float(np.sqrt(np.mean(residual[best, test] ** 2)) * 150.0),
    )
