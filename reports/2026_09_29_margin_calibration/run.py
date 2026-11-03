"""Cross-dataset calibration of a smooth-history CFO residual proxy."""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def interpolate(t, y, mask, i, max_gap=2.0):
    left = np.flatnonzero(mask & (t < t[i]))
    right = np.flatnonzero(mask & (t > t[i]))
    if not len(left) or not len(right):
        return None, 'unbracketed'
    a, b = left[np.argmax(t[left])], right[np.argmin(t[right])]
    if t[b] - t[a] > max_gap:
        return None, 'gap_over_2s'
    w = (t[i] - t[a]) / (t[b] - t[a])
    return ((1-w)*y[a] + w*y[b], math.sqrt(1+(1-w)**2+w**2)), 'eligible'


def objective(theta, x, e, weights):
    z = x @ theta
    q = e**2 * np.exp(-2*z)
    constant = math.lgamma(2.5)-math.lgamma(2)-0.5*math.log(4*math.pi)
    nll = -constant + z + 2.5*np.log1p(q/4)
    return float(weights @ nll), x.T @ (weights*(1-5*q/(4+q)))


def main():
    source = ROOT/'reports/2026_09_29_source_consistent_n8'
    manifest = json.loads((source/'manifest.json').read_text())
    seal = json.loads((source/'quality-seal.json').read_text())['hashes']
    rows, coverage, hashes = [], [], {}
    for scan in manifest['scans']:
        op, qp = Path(scan['observations']), Path(scan['quality_path'])
        for p in [op, qp]:
            hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
        assert hashes[str(qp.relative_to(ROOT))] == seal[str(qp.relative_to(ROOT))]
        expected = next(a['sha256'] for a in scan['input']['artifacts'] if a['kind']=='observations')
        assert hashes[str(op.relative_to(ROOT))] == expected.removeprefix('sha256:')
        obs, quality = json.loads(op.read_text()), json.loads(qp.read_text())
        assert obs['session_id'] == quality['session_id'] == scan['session_id']
        lookup = {(r['track_id'], r['index']): r for r in quality['rows']}
        assert len(lookup) == len(quality['rows'])
        counts = Counter()
        for track in obs['tracks']:
            t, y, mask = (np.asarray(track[k]) for k in ['times_s','measured_hz','training_mask'])
            mask = mask.astype(bool)
            if mask.sum()<2 or (~mask).sum()<1:
                counts['ineligible_tracks'] += 1
                continue
            for i in range(len(t)):
                q = lookup[track['track_id'], i]
                assert bool(mask[i]) == q['training']
                assert abs(y[i]-q['canonical_dealiased_cfo_hz']) < 1e-7
                if mask[i]:
                    continue
                result, reason = interpolate(t, y, mask, i)
                counts[reason] += 1
                if result is None:
                    continue
                assert q['margin'] > 0
                prediction, norm = result
                rows.append(dict(dataset=scan['real_dataset'], session_id=scan['session_id'],
                                 track_id=track['track_id'], index=i, margin=q['margin'],
                                 prediction_hz=prediction, residual_hz=float(y[i]-prediction),
                                 normalized_residual_hz=float((y[i]-prediction)/norm)))
        coverage.append(dict(dataset=scan['real_dataset'], session_id=scan['session_id'], counts=dict(counts)))
    results = []
    for target in ['DS7','DS8','DS9']:
        train = [r for r in rows if r['dataset'] != target]
        counts = Counter(r['session_id'] for r in train)
        weights = np.array([1/counts[r['session_id']]/len(counts) for r in train])
        e = np.array([r['normalized_residual_hz'] for r in train])
        x = np.column_stack([np.ones(len(train)), np.log([r['margin'] for r in train])])
        fits = []
        for n in [1,2]:
            fit = minimize(objective, [math.log(100)]+([0] if n==2 else []),
                           args=(x[:,:n],e,weights), jac=True, method='L-BFGS-B',
                           bounds=[(0,math.log(100000))]+([(-3,3)] if n==2 else []),
                           options=dict(maxiter=500, ftol=1e-14, gtol=1e-8))
            assert fit.success and np.max(np.abs(fit.jac))<1e-5, str(fit)
            fits.append(dict(theta=fit.x.tolist(), gradient=fit.jac.tolist(), success=bool(fit.success)))
        scans = []
        for sid in sorted({r['session_id'] for r in rows if r['dataset']==target}):
            test = [r for r in rows if r['session_id']==sid]
            tx = np.column_stack([np.ones(len(test)), np.log([r['margin'] for r in test])])
            te = np.array([r['normalized_residual_hz'] for r in test])
            scores = [-objective(np.array(f['theta']),tx[:,:j+1],te,np.ones(len(te))/len(te))[0] for j,f in enumerate(fits)]
            scans.append(dict(session_id=sid,n=len(test),constant_log_score=scores[0],margin_log_score=scores[1],gain=scores[1]-scores[0]))
        results.append(dict(target=target, fits=fits, scans=scans,
                            wins=sum(s['gain']>0 for s in scans),mean_gain=float(np.mean([s['gain'] for s in scans]))))
    (OUT/'results.json').write_text(json.dumps(dict(inputs=hashes,coverage=coverage,results=results),indent=2)+'\n')
    (OUT/'residuals.json').write_text(json.dumps(rows,separators=(',',':'))+'\n')
    print(json.dumps(results,indent=2))


if __name__ == '__main__':
    main()
