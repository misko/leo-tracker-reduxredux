"""Frozen conditional receiver fits, independently by acquisition family."""
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from conditional_fit import dataset, digest
from conditional_receiver import design, score_gradient


def projected_gradient(p, grad, bounds):
    g = np.array(grad, copy=True)
    for i, (lo, hi) in enumerate(bounds):
        if (p[i] <= lo + 1e-7 and g[i] > 0) or (p[i] >= hi - 1e-7 and g[i] < 0):
            g[i] = 0.
    return float(np.max(np.abs(g)))


def screen(validation, controls, qualified):
    if not validation['receiver']['per_source']:
        return dict(passed=False, status='no_validation_donor', wins=0, count=0)
    reference = validation['receiver']['per_source']
    wins = sum(validation['signed']['per_source'][s] > v for s, v in reference.items())
    score = validation['signed']['score']
    passed = qualified and wins > len(reference) / 2 and all(score > validation[a]['score'] for a in ('receiver', 'elevation')) and all(score > v for v in controls.values())
    return dict(passed=bool(passed), status='passed' if passed else 'failed', wins=wins, count=len(reference))


def main(number):
    started = time.monotonic()
    inventory_path = HERE.parent / 'acquisition-calibration-inventory.json'
    inventory = json.loads(inventory_path.read_text())
    family = next(f for f in inventory['families'] if f['family'] == number)
    frequencies = family['rf_hz']
    paths = [Path(__file__), HERE / 'CONDITIONAL_PROTOCOL.md', inventory_path, HERE.parent / 'conditional_fit.py', HERE.parent / 'conditional_receiver.py']
    sources = {str(p): digest(p) for p in paths}
    donors = []
    for role in ('calibration', 'validation'):
        for row in family[role]:
            path = HERE / f"donor-{row['index']:02d}.json"
            doc = json.loads(path.read_text())
            assert doc['role'] == role and doc['family'] == number
            for p, h in doc['sources'].items():
                assert digest(p) == h, p
            sources[str(path)] = digest(path)
            donors.append((doc, dataset(doc, frequencies)))
    arms = {}
    for arm in ('receiver', 'elevation', 'signed'):
        x = np.concatenate([design(d['los'], d['rf'], len(frequencies), arm)[d['train']] for doc, d in donors if doc['role'] == 'calibration'])
        states = np.concatenate([d['states'][d['train']] for doc, d in donors if doc['role'] == 'calibration'])
        n = x.shape[-1]
        scales = np.r_[np.full(8, 5.), 10.] if arm != 'receiver' else np.full(8, 5.)
        bounds = [(-20., 20.)] * 8 + ([(0., 40.)] if arm != 'receiver' else [])
        def objective(p):
            scores, gradient = score_gradient(p, x, states)
            return -scores.sum() + .5 * np.sum((p / scales)**2), -gradient + p / scales**2
        starts = [np.zeros(n)] + ([np.r_[np.zeros(8), 5.]] if arm != 'receiver' else [])
        fits = []
        for initial in starts:
            result = minimize(objective, initial, method='L-BFGS-B', jac=True, bounds=bounds, options=dict(maxiter=500, ftol=1e-13, gtol=1e-7))
            finite = np.array([(objective(result.x + np.eye(n)[i] * 1e-5)[0] - objective(result.x - np.eye(n)[i] * 1e-5)[0]) / 2e-5 for i in range(n)])
            discrepancy = float(np.max(abs(finite - result.jac)))
            pg = projected_gradient(result.x, result.jac, bounds)
            fits.append(dict(parameters=result.x.tolist(), objective=float(result.fun), success=bool(result.success), message=str(result.message), projected_gradient=pg, derivative_discrepancy=discrepancy, qualified=bool(result.success and pg <= .01 and discrepancy <= .0001), bound_active=[i for i, (lo, hi) in enumerate(bounds) if min(result.x[i] - lo, hi - result.x[i]) < 1e-7]))
        selected = min(fits, key=lambda r: r['objective'])
        p = np.array(selected['parameters'])
        evaluations = []
        for doc, d in donors:
            scores = score_gradient(p, design(d['los'], d['rf'], 4, arm), d['states'])[0]
            for split, mask in [('training', d['train']), ('held', ~d['train'])]:
                evaluations.append(dict(donor=doc['index'], role=doc['role'], split=split, count=int(mask.sum()), score=float(scores[mask].sum()), per_source={f"{doc['index']}:{int(s)}": float(scores[mask & (d['source'] == s)].sum()) for s in np.unique(d['source'][mask])}))
        arms[arm] = dict(fits=fits, selected=selected, evaluations=evaluations)
    validation = {}
    for arm, out in arms.items():
        rows = [r for r in out['evaluations'] if r['role'] == 'validation' and r['split'] == 'held']
        validation[arm] = dict(score=sum(r['score'] for r in rows), count=sum(r['count'] for r in rows), per_source={k: v for r in rows for k, v in r['per_source'].items()})
    controls = {}
    p = np.array(arms['signed']['selected']['parameters'])
    for name in ('swapped', 'permuted'):
        total = 0.
        for doc, _ in donors:
            if doc['role'] != 'validation':
                continue
            d = dataset(doc, frequencies, permutation=name == 'permuted')
            values = score_gradient(p, design(d['los'], d['rf'], 4, 'swapped' if name == 'swapped' else 'signed'), d['states'])[0]
            total += float(values[~d['train']].sum())
        controls[name] = total
    gate = screen(validation, controls, all(out['selected']['qualified'] for out in arms.values()))
    result = dict(family=number, frequencies=frequencies, sample_rate_hz=family['sample_rate_hz'], arms=arms, validation=validation, controls=controls, screen=gate, sources=sources, elapsed_s=time.monotonic() - started)
    with (HERE / f'fit-{number}.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(dict(family=number, validation={a: v['score'] for a, v in validation.items()}, controls=controls, screen=gate, qualified=[a for a, v in arms.items() if v['selected']['qualified']], elapsed_s=result['elapsed_s'])), flush=True)


if __name__ == '__main__':
    main(int(sys.argv[1]))
