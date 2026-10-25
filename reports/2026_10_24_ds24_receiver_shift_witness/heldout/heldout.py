"""Bounded train-only family holdout; no geographic reference is imported.

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

HERE = Path(__file__).resolve().parent
CASES = ('DS24-0017', 'DS24-0095')
MODELS = ('baseline', 'sharedRF50')
ARMS = ('c0', 'fitted_c')
SEED = 2026102503
SCALES = (1., float(np.sqrt(2.)), 2.)


def fold_assignment(d):
    """Three random disjoint whole-family groups; no target outcomes enter."""
    p = original_build(d, 'default', 'c0', np.zeros(len(d['means'])))
    active = {r['candidate_index'] for r, sl in zip(p.rows, p.slices, strict=True) if p.keep[sl].any()}
    active.update(e['candidate_index'] for e in d['entries'])
    labels = np.array(sorted(active), int)
    rng = np.random.default_rng(SEED + int(d['case'].split('-')[-1]))
    groups = np.array_split(rng.permutation(labels), 3)
    return [sorted(map(int, g)) for g in groups]


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
    artifact.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(artifact, raw=raw, uncertainty=uncertainty, native_sigma=sigma,
                        family=families, observation_ids=np.array(held_ids), position=np.asarray(x), reference=p.reference)
    return dict(scores=scores, family_marginals_nonadditive=marginals, prior_audit=audit,
        held_curved_points=int(select.sum()), held_predictive_points=sum(e['points'] for e in held_entries),
        native_sigma_range_hz=[float(sigma.min()), float(sigma.max())], phase_refresh_changes_s=changes,
        artifact=str(artifact), artifact_sha256=digest(artifact),
        observation_id_sha256=hashlib.sha256(canonical(held_ids)).hexdigest())


def one(case, fold):
    protocol = json.loads((HERE/'protocol.json').read_text())
    protocol_digest = digest(HERE/'protocol.json')
    def verify_seal():
        if digest(HERE/'protocol.json') != protocol_digest:
            raise ValueError('protocol changed during execution')
        if protocol['source_sha256'] != digest(__file__):
            raise ValueError('source changed after protocol freeze')
        if protocol['input_manifest_sha256'] != digest(HERE/'input_manifest.json'):
            raise ValueError('input manifest changed after protocol freeze')
        for item in protocol['dependencies']:
            if digest(item['path']) != item['sha256']:
                raise ValueError('dependency changed after protocol freeze: '+item['path'])
    verify_seal()
    sealed_input = json.loads((HERE/'input_manifest.json').read_text())[case]
    destination = HERE/'results'/f'{case}_fold{fold}.json'
    if destination.exists():
        raise ValueError('refuse to overwrite existing fold evidence')
    began = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('240s case/fold cap')))
    signal.alarm(240)
    result = dict(case=case, fold=fold, GPS_used=False, protocol_sha256=digest(HERE/'protocol.json'), source_sha256=digest(__file__))
    try:
        d = load_baseline(case);binding = measurement_binding(d)
        groups = fold_assignment(d);held = groups[fold];train = training_data(d, held)
        if d['baseline_sha256'] != sealed_input['baseline_sha256'] or binding != sealed_input['measurement_binding_sha256']:
            raise ValueError('loaded data differ from prefit sealed inputs')
        if groups != [f['held_families'] for f in sealed_input['folds']]:
            raise ValueError('folds differ from prefit sealed assignment')
        audit_p = build(train, 'c0', causal_reference(train, held), 'baseline')
        original_curved_ids = [oid for i in audit_p.members for oid in audit_p.scan.tracks[i]['observation_ids']]
        train_ids = np.asarray(original_curved_ids)[train['keep']].tolist()
        train_ids.extend(oid for e in train['entries'] for oid in e['observation_ids'])
        if hashlib.sha256(canonical(train_ids)).hexdigest() != sealed_input['folds'][fold]['training_ids_sha256']:
            raise ValueError('training IDs differ from prefit sealed membership')
        result.update(held_families=held, held_norads=[int(d['scan'].norads[j]) for j in held],
            folds=groups, input_binding_sha256=binding, baseline_sha256=d['baseline_sha256'], arms={})
        for arm in ARMS:
            fits = {model: cold_fit(train, held, arm, model) for model in MODELS}
            scores = {}
            for predictor in MODELS:
                scores[predictor] = {}
                for endpoint in MODELS:
                    artifact = HERE/'arrays'/f'{case}_fold{fold}_{arm}_{predictor}_at_{endpoint}.npz'
                    scores[predictor][endpoint] = score_endpoint(d, train, held, arm, predictor,
                        fits[endpoint]['endpoint_east_north_km'], artifact)
                    if scores[predictor][endpoint]['observation_id_sha256'] != sealed_input['folds'][fold]['held_ids_sha256']:
                        raise ValueError('held IDs differ from prefit sealed membership')
            result['arms'][arm] = dict(fits=fits, crossover=scores)
        if measurement_binding(d) != binding:
            raise ValueError('frozen data mutated')
        if digest(d['baseline_path']) != sealed_input['baseline_sha256']:
            raise ValueError('frozen baseline changed during execution')
        verify_seal()
        result['status'] = 'complete'
    except Exception as exc:
        import traceback
        result.update(status='failed', error=repr(exc), traceback=traceback.format_exc())
    finally:
        signal.alarm(0)
    result['seconds'] = time.monotonic()-began
    write(destination, result)
    print(case, fold, result['status'], round(result['seconds'], 2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--fold', type=int, choices=range(3), required=True)
    args = parser.parse_args()
    one(args.case, args.fold)
