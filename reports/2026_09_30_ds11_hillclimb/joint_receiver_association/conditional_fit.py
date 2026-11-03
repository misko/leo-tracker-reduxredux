"""Frozen conditional calibration/transfer screen on compatible earlier scans."""
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from scipy.optimize import minimize
from conditional_receiver import design, score_gradient

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dataset(doc, frequencies, permutation=False):
    lanes = doc['lanes']
    alternate = list(range(len(lanes)))
    if permutation:
        rng = np.random.default_rng(20260930)
        for rf in frequencies:
            indices = [i for i, lane in enumerate(lanes) if lane['rf_hz'] == rf]
            for i, j in zip(indices, rng.permutation(indices)):
                alternate[i] = int(j)
    rows = []
    for i, lane in enumerate(lanes):
        bits = np.asarray(lane['bits'])
        known_hit = (bits >= 0).all(axis=1) & (bits.sum(axis=1) > 0)
        other = lanes[alternate[i]]
        assert other['times_s'] == lane['times_s']
        for j in np.flatnonzero(known_hit):
            rows.append((other['los_enu'][j], frequencies.index(lane['rf_hz']), int(bits[j, 0] + 2 * bits[j, 1]), bool(lane['training_mask'][j]), i))
    return dict(los=np.array([r[0] for r in rows]), rf=np.array([r[1] for r in rows]), states=np.array([r[2] for r in rows]), train=np.array([r[3] for r in rows]), source=np.array([r[4] for r in rows]))


def main():
    start = time.monotonic()
    sources = {}
    donors = []
    for index in (0, 1):
        path = HERE / f'donor-{index}.json'
        donors.append(json.loads(path.read_text()))
        sources[str(path)] = digest(path)
        for p, h in donors[-1]['sources'].items():
            assert digest(p) == h, p
    frequencies = sorted({l['rf_hz'] for l in donors[0]['lanes']})
    data = [dataset(d, frequencies) for d in donors]
    arms = {}
    for arm in ('receiver', 'elevation', 'signed'):
        d = data[0]
        x = design(d['los'], d['rf'], len(frequencies), arm)[d['train']]
        states = d['states'][d['train']]
        n = x.shape[-1]
        scales = np.full(n, 5.)
        if arm != 'receiver':
            scales[-1] = 10.
        def objective(p):
            scores, grad = score_gradient(p, x, states)
            return -scores.sum() + .5 * np.sum((p / scales)**2), -grad + p / scales**2
        starts = [np.zeros(n)]
        if arm != 'receiver':
            starts.append(np.r_[np.zeros(n - 1), 5.])
        fits = []
        for initial in starts:
            fit = minimize(objective, initial, method='L-BFGS-B', jac=True, bounds=[(-20., 20.)] * 8 + ([(0., 40.)] if arm != 'receiver' else []), options=dict(maxiter=500, ftol=1e-13, gtol=1e-7))
            fits.append(dict(parameters=fit.x.tolist(), objective=float(fit.fun), success=bool(fit.success), message=str(fit.message), gradient_max=float(np.max(np.abs(fit.jac)))))
        fit = min(fits, key=lambda r: r['objective'])
        assert fit['success'], fit
        p = np.array(fit['parameters'])
        analytic = objective(p)[1]
        numerical = np.array([(objective(p + np.eye(n)[i] * 1e-5)[0] - objective(p - np.eye(n)[i] * 1e-5)[0]) / 2e-5 for i in range(n)])
        discrepancy = float(np.max(np.abs(analytic - numerical)))
        assert discrepancy < 1e-5
        evaluations = []
        for index, d in enumerate(data):
            scores = score_gradient(p, design(d['los'], d['rf'], len(frequencies), arm), d['states'])[0]
            for split, mask in [('training', d['train']), ('held', ~d['train'])]:
                evaluations.append(dict(donor=index, split=split, count=int(mask.sum()), score=float(scores[mask].sum()), per_source={str(s): float(scores[mask & (d['source'] == s)].sum()) for s in np.unique(d['source'][mask])}))
        arms[arm] = dict(fits=fits, selected=fit, derivative_discrepancy=discrepancy, evaluations=evaluations)
    p = np.array(arms['signed']['selected']['parameters'])
    d = data[1]
    held = ~d['train']
    controls = {}
    for name in ('swapped', 'permuted'):
        ctrl = dataset(donors[1], frequencies, permutation=name == 'permuted')
        values = score_gradient(p, design(ctrl['los'], ctrl['rf'], len(frequencies), 'swapped' if name == 'swapped' else 'signed'), ctrl['states'])[0]
        controls[name] = float(values[held].sum())
    validation = {arm: next(r for r in out['evaluations'] if r['donor'] == 1 and r['split'] == 'held') for arm, out in arms.items()}
    wins = sum(validation['signed']['per_source'][s] > value for s, value in validation['receiver']['per_source'].items())
    count = len(validation['receiver']['per_source'])
    passed = all(validation['signed']['score'] > validation[a]['score'] for a in ('receiver', 'elevation')) and all(validation['signed']['score'] > v for v in controls.values()) and wins > count / 2
    for name in ('conditional_fit.py', 'conditional_receiver.py', 'test_conditional_receiver.py', 'CONDITIONAL_PROTOCOL.md'):
        sources[str(HERE / name)] = digest(HERE / name)
    result = dict(arms=arms, controls_validation_held=controls, validation_source_wins=wins, validation_source_count=count, signed_screen_passed=passed, frequencies=frequencies, sources=sources, elapsed_s=time.monotonic() - start, scope='conditional nonempty states; inferred source labels; no position fit')
    with (HERE / 'conditional-fit.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(dict(validation={a: dict(score=v['score'], count=v['count']) for a, v in validation.items()}, controls=controls, source_wins=wins, source_count=count, passed=passed, elapsed_s=result['elapsed_s']), indent=2))


if __name__ == '__main__':
    main()
