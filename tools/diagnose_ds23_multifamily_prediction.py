"""RF-only decomposition of the failed prediction-selected position policies."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

from ds23_multifamily_proposals import prediction
from ds23_frequency_events import make_event_problem
from probe_ds23_frequency_events import cached
from probe_ds23_fft_grid_position import setup
from probe_ds23_multifamily_projection import OUT, SOURCE, ARMS, prepare
from run_algo01_ds23_sample import read, write, sha


def detail(scan, node, original, arm, powers, means, model, x):
    p = make_event_problem(scan, node, original, arm, np.zeros(len(means)), powers, means, model, [])
    labels = np.asarray(p.labels)[p.flat_labels]
    rows = []
    for family in np.unique(labels[original]):
        train, test = original & (labels != family), original & (labels == family)
        reference = np.zeros(len(means))
        for _ in range(5):
            p = cached(make_event_problem(scan, node, train, arm, reference, powers, means, model, []))
            phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
            change = float(np.max(abs(phase-p.reference)))
            reference = phase
        d = prediction(p, x, train, test, int(family), powers)
        n = int(test.sum())
        rows.append(dict(norad=int(scan.norads[family]), points=n,
            quadratic=d['quadratic'], logdet=d['negative_twice_log_density']-d['quadratic']-n*np.log(2*np.pi),
            total=d['negative_twice_log_density'], raw_MSE_hz2=d['RMS_hz']**2,
            mean_predictive_variance_hz2=float(np.mean(d['marginal_sigma_hz']**2)),
            final_phase_change_s=change))
    return rows


def run(case):
    path = OUT / 'RF_score_decomposition' / (case + '.json')
    if path.exists():
        return dict(case=case, cached=True)
    r, base = read(OUT / (case + '.json')), read(SOURCE / (case + '.json'))
    scan, node, keep, _, _, _, _, model, powers, means, _ = setup(case)
    result = {}
    for arm in ARMS:
        null = detail(scan, node, keep, arm, powers, means, model,
            np.asarray(base['incumbent_arms'][arm]['endpoint_east_north_km']))
        chosen = detail(scan, node, keep, arm, powers, means, model,
            np.asarray(r['policy_arms'][arm]['endpoint_east_north_km']))
        if abs(sum(s['total'] for s in null)-base['null_scores'][arm]['score']) > 1e-6:
            raise ValueError('null predictive decomposition does not replay')
        source = r['projected_scores'][arm] if r['accepted'] else next(t for t in base['trials'] if t['index']==base['selected_index'])['scores'][arm]
        if abs(sum(s['total'] for s in chosen)-source['score']) > 1e-6:
            raise ValueError('chosen predictive decomposition does not replay')
        pairs = []
        for a, b in zip(null, chosen, strict=True):
            if a['norad'] != b['norad'] or a['points'] != b['points']:
                raise ValueError('decomposition changed held-family observations')
            pairs.append(dict(norad=a['norad'], points=a['points'],
                quadratic_change=b['quadratic']-a['quadratic'], logdet_change=b['logdet']-a['logdet'],
                total_change=b['total']-a['total'], raw_MSE_change_hz2=b['raw_MSE_hz2']-a['raw_MSE_hz2'],
                predictive_variance_ratio=b['mean_predictive_variance_hz2']/a['mean_predictive_variance_hz2']))
        count = sum(p['points'] for p in pairs)
        result[arm] = dict(null=null, chosen=chosen, changes=pairs,
            quadratic_change=sum(p['quadratic_change'] for p in pairs),
            logdet_change=sum(p['logdet_change'] for p in pairs),
            total_change=sum(p['total_change'] for p in pairs),
            point_weighted_raw_MSE_change_hz2=sum(p['points']*p['raw_MSE_change_hz2'] for p in pairs)/count,
            families_with_increased_predictive_variance=sum(p['predictive_variance_ratio']>1 for p in pairs),
            family_count=len(pairs))
    write(path, dict(case=case, arms=result, no_GPS_used=True,
        policy_sha256=sha(OUT / (case+'.json')), base_sha256=sha(SOURCE / (case+'.json'))))
    row = dict(case=case, **{a: {k:result[a][k] for k in ('quadratic_change', 'logdet_change', 'point_weighted_raw_MSE_change_hz2')} for a in ARMS})
    print(row, flush=True)
    return row


if __name__ == '__main__':
    protocol = prepare()
    cases = []
    for c in protocol['development_cases'] + protocol['confirmation_cases']:
        r, base = read(OUT / (c+'.json')), read(SOURCE / (c+'.json'))
        if r['accepted'] or base['accepted']:
            cases.append(c)
    (OUT / 'RF_score_decomposition').mkdir(exist_ok=True)
    receipts = []
    with ProcessPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(run, c): c for c in cases}
        for f in as_completed(futures):
            try:
                receipts.append(f.result())
            except Exception as exc:
                receipts.append(dict(case=futures[f], error=repr(exc)))
    write(OUT / 'RF_score_decomposition_execution.json', dict(all_terminal=True,
        receipts=receipts, errors=[r for r in receipts if 'error' in r], no_GPS_used=True))
    print('Terminal', len(receipts), 'errors', sum('error' in r for r in receipts), flush=True)
