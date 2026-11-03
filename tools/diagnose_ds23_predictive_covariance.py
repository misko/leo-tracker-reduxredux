"""Separate held-family predictive mean and covariance effects, RF only."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

from ds23_frequency_events import make_event_problem
from probe_ds23_frequency_events import cached
from probe_ds23_fft_grid_position import setup
from probe_ds23_multifamily_projection import OUT, SOURCE, ARMS, prepare
from run_algo01_ds23_sample import read, write, sha


def gaussian_cost(raw, covariance):
    raw, covariance = np.asarray(raw, float), np.asarray(covariance, float)
    if raw.ndim != 1 or covariance.shape != (len(raw), len(raw)):
        raise ValueError('matching predictive mean and covariance required')
    root = np.linalg.cholesky(covariance)
    white = np.linalg.solve(root, raw)
    return float(white@white + 2*np.log(np.diag(root)).sum() + len(raw)*np.log(2*np.pi))


def contributions(old_raw, old_covariance, new_raw, new_covariance):
    a, b = gaussian_cost(old_raw, old_covariance), gaussian_cost(new_raw, old_covariance)
    c, d = gaussian_cost(old_raw, new_covariance), gaussian_cost(new_raw, new_covariance)
    return dict(old_cost=a, new_cost=d, total_change=d-a,
        mean_only_change_at_old_covariance=b-a,
        mean_Shapley_change=.5*((b-a)+(d-c)),
        covariance_Shapley_change=.5*((c-a)+(d-b)))


def moments(scan, node, original, arm, powers, means, model, x, family, labels):
    train, test = original & (labels != family), original & (labels == family)
    reference = np.zeros(len(means))
    for _ in range(5):
        p = cached(make_event_problem(scan, node, train, arm, reference, powers, means, model, []))
        reference = np.clip(p.state(x)['phases'][p.labels], -15, 15)
    c = p.calculate(x)
    precision = c['coefficient_prior_precision'].copy()
    phase_begin = p.hardware.shape[1] + p.smooth.shape[1]
    precision[phase_begin + p.labels.index(int(family))] = 1.
    weights = powers[p.noise_groups[train]]*c['noise_precision'][p.noise_groups[train]]/p.point_noise[train]**2
    design = c['features']
    gram = np.diag(precision) + design[train].T@(design[train]*weights[:, None])
    root = np.linalg.cholesky((gram+gram.T)/2)
    u = np.linalg.solve(root, design[test].T)
    covariance = u.T@u + np.diag(2*p.point_noise[test]**2/powers[p.noise_groups[test]])
    return c['conditional_residual_hz'][test], (covariance+covariance.T)/2


def run(case):
    path = OUT / 'mean_covariance_decomposition' / (case + '.json')
    if path.exists():
        return dict(case=case, cached=True)
    record, base = read(OUT / (case+'.json')), read(SOURCE / (case+'.json'))
    scan, node, keep, p, _, _, _, model, powers, means, _ = setup(case)
    labels = np.asarray(p.labels)[p.flat_labels]
    result = {}
    for arm in ARMS:
        old = np.asarray(base['incumbent_arms'][arm]['endpoint_east_north_km'])
        new = np.asarray(record['policy_arms'][arm]['endpoint_east_north_km'])
        rows = []
        for family in np.unique(labels[keep]):
            a, b = moments(scan, node, keep, arm, powers, means, model, old, family, labels)
            c, d = moments(scan, node, keep, arm, powers, means, model, new, family, labels)
            rows.append(dict(norad=int(scan.norads[family]), points=len(a), **contributions(a, b, c, d)))
        expected_old = base['null_scores'][arm]['score']
        expected_new = (record['projected_scores'][arm] if record['accepted'] else
            next(t for t in base['trials'] if t['index']==base['selected_index'])['scores'][arm])['score']
        if abs(sum(r['old_cost'] for r in rows)-expected_old)>1e-6 or abs(sum(r['new_cost'] for r in rows)-expected_new)>1e-6:
            raise ValueError('direct dense Gaussian score does not reproduce source')
        result[arm] = dict(families=rows, **{k:sum(r[k] for r in rows) for k in
            ('total_change', 'mean_only_change_at_old_covariance', 'mean_Shapley_change', 'covariance_Shapley_change')})
    write(path, dict(case=case, arms=result, no_GPS_used=True,
        source_sha256=sha(OUT/(case+'.json')), direct_dense_covariances_replay_predictive_scores=True))
    receipt = dict(case=case, **{a:{k:result[a][k] for k in
        ('total_change', 'mean_only_change_at_old_covariance', 'mean_Shapley_change', 'covariance_Shapley_change')} for a in ARMS})
    print(receipt, flush=True)
    return receipt


if __name__ == '__main__':
    protocol = prepare()
    (OUT / 'mean_covariance_decomposition').mkdir(exist_ok=True)
    cases = [c for c in protocol['development_cases']+protocol['confirmation_cases']
        if read(OUT/(c+'.json'))['accepted'] or read(SOURCE/(c+'.json'))['accepted']]
    receipts = []
    with ProcessPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(run, c): c for c in cases}
        for f in as_completed(futures):
            try:
                receipts.append(f.result())
            except Exception as exc:
                receipts.append(dict(case=futures[f], error=repr(exc)))
    write(OUT / 'mean_covariance_execution.json', dict(all_terminal=True, receipts=receipts,
        errors=[r for r in receipts if 'error' in r], no_GPS_used=True))
    print('Terminal', len(receipts), 'errors', sum('error' in r for r in receipts), flush=True)
