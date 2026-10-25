"""Versioned scientific kernel adapted from the sealed two-case movement witness.

The reported held density is a joint Gaussian moment approximation conditional
on the variational training posterior and fitted train-only position. It is not
the original Student/Gamma likelihood or an external identity validation.
"""
import argparse
import copy
import hashlib
import json
import signal
import time
from pathlib import Path

import numpy as np
from scipy.linalg import solve_triangular

from matched_controls import load_baseline, measurement_binding, canonical, digest, write
from probe_ds23_graph_seeded_paths import build as original_build
from adapter import expand
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from investigate_dsx01_localization_failures import fit

MODELS = ('baseline', 'sharedRF50')
ARMS = ('c0', 'fitted_c')
SCALES = (1., float(np.sqrt(2.)), 2.)


def family_partition(d, seed):
    """Three random disjoint whole-family groups; no target outcomes enter."""
    p = original_build(d, 'default', 'c0', np.zeros(len(d['means'])))
    active = {r['candidate_index'] for r, sl in zip(p.rows, p.slices, strict=True) if p.keep[sl].any()}
    active.update(e['candidate_index'] for e in d['entries'])
    labels = np.array(sorted(active), int)
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([int(seed), int(d['case'].split('-')[-1])])))
    permutation = rng.permutation(labels)
    groups = np.array_split(permutation, 3)
    return dict(active_family_indices=labels.tolist(), permutation=permutation.tolist(),
                folds=[sorted(map(int, g)) for g in groups])


def fold_assignment(d, seed):
    return family_partition(d, seed)['folds']


def training_data(d, held):
    """Rows remain for stable physical modes; factors, not only labels, vanish."""
    train = dict(d)
    p = original_build(d, 'default', 'c0', np.zeros(len(d['means'])))
    keep = np.asarray(d['keep']).copy()
    for row, sl in zip(p.rows, p.slices, strict=True):
        if row['candidate_index'] in held:
            keep[sl] = False
    train['keep'] = keep
    train['entries'] = [copy.deepcopy(e) for e in d['entries'] if e['candidate_index'] not in held]
    assert keep.any()
    assert not any(e['candidate_index'] in held for e in train['entries'])
    return train


def build(train, arm, reference, model):
    changed = expand(train, 'fast_rx1_rf50') if model == 'sharedRF50' else train
    return original_build(changed, 'default', arm, np.asarray(reference))


def causal_reference(d, held, reference=None):
    labels = sorted({r['candidate_index'] for r in d['node']['seed']['rows']})
    ref = np.zeros(len(labels)) if reference is None else np.asarray(reference).copy()
    select = np.isin(labels, held)
    ref[select] = np.asarray(d['means'])[select]
    return ref


def cold_fit(train, held, arm, model):
    reference = causal_reference(train, held)
    x = np.zeros(2)
    history = []
    for epoch in range(5):
        p = build(train, arm, reference, model)
        fitted = fit(p, x, iterations=48)
        x = np.asarray(fitted['parameters'])
        phase = np.clip(p.state(x)['phases'][p.labels], -15., 15.)
        phase = causal_reference(train, held, phase)
        history.append(dict(epoch=epoch, fit=fitted, phase_change_s=float(np.max(abs(phase-reference)))))
        reference = phase
    c = p.calculate(x)
    curved = p.curved_calculate(x) if train['entries'] else c
    if np.max(abs(curved['coefficient']-c['coefficient'])) > 1e-12:
        raise ValueError('predictive training observations updated calibration')
    return dict(endpoint_east_north_km=x, history=history, reference_used=p.reference,
                final_phase_change_s=history[-1]['phase_change_s'],
                training_objective=float(c['negative_twice_elbo']),
                training_curved_RMS_hz=float(np.sqrt(np.mean(curved['conditional_residual_hz'][p.keep]**2))),
                training_curved_points=int(p.keep.sum()), training_predictive_points=sum(e['points'] for e in train['entries']),
                training_final_log_precision_change=float(curved['final_log_precision_change']))


def fixed_position_posterior(train, held, arm, model, x):
    """Symmetric five train-only phase refreshes at each crossover endpoint."""
    reference = causal_reference(train, held)
    changes = []
    for _ in range(5):
        p = build(train, arm, reference, model)
        phase = causal_reference(train, held, np.clip(p.state(x)['phases'][p.labels], -15., 15.))
        changes.append(float(np.max(abs(phase-reference))))
        reference = phase
    c = p.curved_calculate(x) if train['entries'] else p.calculate(x)
    return p, c, changes


def held_posterior(p, c, train, held):
    """Full joint covariance; unused Student phase uses its unit variance."""
    u = c['features'][p.keep]
    g = p.noise_groups[p.keep]
    weights = train['powers'][g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
    prior = np.asarray(c['coefficient_prior_precision']).copy()
    begin = p.hardware.shape[1]+p.smooth.shape[1]
    held_phase = np.array([begin+k for k, j in enumerate(p.labels) if j in held], int)
    held_orbit = np.array([begin+len(p.labels)+3*k+m for k, j in enumerate(p.supported) if j in held for m in range(3)], int)
    held_constants = np.array([len(prior)-len(p.members)+k for k, row in enumerate(p.rows) if row['candidate_index'] in held], int)
    untouched = np.r_[held_phase, held_orbit, held_constants]
    if np.max(abs(u[:, untouched]), initial=0.) != 0.:
        raise ValueError('held local coordinates have training loadings')
    prior[held_phase] = 1.  # nu=3 Student marginal standardized variance; NOT E[tau].
    np.testing.assert_allclose(prior[held_orbit], 1., atol=1e-12)
    np.testing.assert_allclose(prior[held_constants], 1/.3**2, atol=1e-12)
    gram = np.diag(prior)+u.T@(u*weights[:, None])
    root = np.linalg.cholesky(gram)
    invroot = solve_triangular(root, np.eye(len(root)), lower=True)
    covariance = invroot.T@invroot
    trained = np.setdiff1d(np.arange(len(prior)), untouched)
    cross = float(np.max(abs(covariance[np.ix_(untouched, trained)]), initial=0.))
    if cross > 1e-12:
        raise ValueError('held local prior crosscovariance is contaminated')
    mean = np.asarray(c['coefficient']).copy()
    expected_phase = np.asarray(train['means'])/p.phase_sigma
    np.testing.assert_allclose(mean[held_phase], expected_phase[held_phase-begin], atol=1e-12)
    np.testing.assert_allclose(mean[np.r_[held_orbit, held_constants]], 0., atol=1e-12)
    np.testing.assert_allclose(np.diag(covariance)[held_phase], 1., atol=1e-12)
    return mean, root, dict(held_phase_indices=held_phase, held_orbit_indices=held_orbit,
        held_constant_indices=held_constants, maximum_held_training_loading=0.,
        maximum_held_trained_crosscovariance=cross, held_phase_variance=np.diag(covariance)[held_phase],
        held_phase_variational_precision_discarded=np.asarray(c['coefficient_prior_precision'])[held_phase])


def gaussian_score(raw, uncertainty, sigma):
    """Normalized density of diag(sigma²)+UU', retaining all correlations."""
    raw, uncertainty, sigma = map(np.asarray, (raw, uncertainty, sigma))
    a = uncertainty/sigma[:, None]
    b = raw/sigma
    gram = np.eye(a.shape[1])+a.T@a
    root = np.linalg.cholesky(gram)
    rhs = a.T@b
    coefficient = solve_triangular(root.T, solve_triangular(root, rhs, lower=True), lower=False)
    innovation = b-a@coefficient
    quadratic = float(innovation@innovation+coefficient@coefficient)
    logdet = float(2*np.log(sigma).sum()+2*np.log(np.diag(root)).sum())
    return dict(negative_twice_log_density=quadratic+logdet+len(raw)*np.log(2*np.pi),
                quadratic=quadratic, logdet=logdet, dimensions=len(raw),
                mean_prediction_RMS_hz=float(np.sqrt(np.mean(raw**2))))


def score_endpoint(d, train, held, arm, model, x, artifact):
    p, c, changes = fixed_position_posterior(train, held, arm, model, x)
    mean, root, audit = held_posterior(p, c, train, held)
    select = np.asarray(d['keep']) & np.isin(np.asarray(p.labels)[p.flat_labels], held)
    raw = [p.values[select]-p.q[select]*c['intercept'][select]-c['features'][select]@mean]
    design = [c['features'][select]]
    sigma = [p.point_noise[select]]
    families = [np.asarray(p.labels)[p.flat_labels[select]]]
    ids = [oid for i in p.members for oid in p.scan.tracks[i]['observation_ids']]
    held_ids = list(np.asarray(ids)[select])
    held_entries = [e for e in d['entries'] if e['candidate_index'] in held]
    extra = np.zeros((int(select.sum()), len(held_entries)))
    if held_entries:
        view, values, sigmas, groups, _ = linear_geometry(p, held_entries)
        geometry = geometry_features(view, x, 0.)
        raw.append(values-view.q*geometry['intercept']-geometry['features']@mean)
        design.append(geometry['features']);sigma.append(sigmas)
        families.append(np.asarray(p.labels)[view.flat_labels])
        extra = np.vstack((extra, np.eye(len(held_entries))[groups]*300.))
        held_ids.extend(oid for e in held_entries for oid in p.scan.tracks[e['track_index']]['observation_ids'])
    raw = np.concatenate(raw);design = np.vstack(design);sigma = np.concatenate(sigma);families = np.concatenate(families)
    if len(set(held_ids)) != len(held_ids):
        raise ValueError('held curved/predictive observation duplication')
    uncertainty = solve_triangular(root, design.T, lower=True).T
    uncertainty = np.column_stack((uncertainty, extra))
    scores = {str(scale): gaussian_score(raw, uncertainty, sigma*scale) for scale in SCALES}
    marginals = {str(j): gaussian_score(raw[families==j], uncertainty[families==j], sigma[families==j]*np.sqrt(2.)) for j in held if np.any(families==j)}
    for name, value in [('raw', raw), ('uncertainty', uncertainty), ('sigma', sigma), ('mean', mean), ('root', root)]:
        if not np.isfinite(value).all():
            raise ValueError('nonfinite held ' + name)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects partial artifacts from any accidental rerun.
    with artifact.open('xb') as stream:
        np.savez_compressed(stream, raw=raw, uncertainty=uncertainty, native_sigma=sigma,
            family=families, observation_ids=np.array(held_ids), position=np.asarray(x), reference=p.reference,
            held_design=design, posterior_mean=mean, posterior_precision_cholesky=root,
            predictive_fragment_constants=extra, coefficient_prior_precision=c['coefficient_prior_precision'],
            held_phase_indices=audit['held_phase_indices'], held_orbit_indices=audit['held_orbit_indices'],
            held_constant_indices=audit['held_constant_indices'],
            curved_noise_group=p.noise_groups[select], curved_likelihood_power=train['powers'][p.noise_groups[select]])
    return dict(scores=scores, family_marginals_nonadditive=marginals, prior_audit=audit,
        held_curved_points=int(select.sum()), held_predictive_points=sum(e['points'] for e in held_entries),
        native_sigma_range_hz=[float(sigma.min()), float(sigma.max())], phase_refresh_changes_s=changes,
        final_log_precision_change=float(c['final_log_precision_change']),
        predictive_fragment_group=groups.tolist() if held_entries else [],
        artifact=str(artifact), artifact_sha256=digest(artifact),
        observation_id_sha256=hashlib.sha256(canonical(held_ids)).hexdigest())


