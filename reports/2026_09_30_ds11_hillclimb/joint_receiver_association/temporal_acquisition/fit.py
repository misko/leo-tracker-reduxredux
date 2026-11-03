"""One receiver-only persistence fit per acquisition family; frozen emissions."""
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))
from doppler_pilot import read, digest
from temporal_fit import dataset
from temporal_receiver import sequence_score
from null_score import score


def evaluate(parameters, rows, tau):
    held, per_source = 0., {}
    for row in rows:
        weights = row['features'] @ parameters
        logp = weights - logsumexp(weights, axis=1)[:, None]
        training = sequence_score(row['times'], logp[None], row['states'], row['train'], tau)[0][0]
        joint = sequence_score(row['times'], logp[None], row['states'], np.ones(len(row['times']), bool), tau)[0][0]
        held += joint - training
        if np.any(~row['train']):
            per_source[str(row['source'])] = float(joint - training)
    return dict(score=float(held), per_source=per_source)


def main(number):
    started = time.monotonic()
    calpath = PARENT / f'acquisition_calibration/fit-{number}.json'
    inventorypath = PARENT / 'acquisition-calibration-inventory.json'
    calibration = read(calpath)
    assert calibration['screen']['passed']
    family = read(inventorypath)['families'][number]
    sources = {str(p): digest(p) for p in (Path(__file__), HERE / 'null_score.py', HERE / 'test_null_score.py', HERE / 'PROTOCOL.md', calpath, inventorypath, PARENT / 'temporal_fit.py', PARENT / 'temporal_receiver.py', PARENT / 'conditional_receiver.py')}
    donors = []
    for role in ('calibration', 'validation'):
        for r in family[role]:
            path = PARENT / f"acquisition_calibration/donor-{r['index']:02d}.json"
            doc = read(path)
            for p, h in doc['sources'].items():
                assert digest(p) == h, p
            sources[str(path)] = digest(path)
            donors.append(doc)
    null = np.array(calibration['arms']['receiver']['selected']['parameters'])
    sequences = []
    for doc in donors:
        if doc['role'] != 'calibration':
            continue
        for row in dataset(doc, calibration['frequencies'], 'receiver'):
            if not np.any(row['train']):
                continue
            weights = row['features'][0] @ null
            p = np.exp(weights - logsumexp(weights))
            sequences.append((row['times'][row['train']], row['states'][row['train']], p))
    def objective(logtau):
        value, gradient = score(logtau, sequences)
        return -value + .5 * (logtau / 3.)**2, -gradient + logtau / 9.
    bounds = np.log([.01, 60.])
    fit = minimize_scalar(lambda x: objective(x)[0], bounds=bounds, method='bounded', options=dict(xatol=1e-10, maxiter=150))
    derivative = objective(fit.x)[1]
    numerical = (objective(fit.x + 1e-5)[0] - objective(fit.x - 1e-5)[0]) / 2e-5
    discrepancy = abs(derivative - numerical)
    projected = abs(derivative)
    if (fit.x <= bounds[0] + 1e-7 and derivative > 0) or (fit.x >= bounds[1] - 1e-7 and derivative < 0):
        projected = 0.
    qualified = bool(fit.success and projected <= .001 and discrepancy <= .00001)
    tau = float(np.exp(fit.x))
    evaluations = {}
    for name in ('receiver', 'elevation', 'signed', 'swapped', 'permuted'):
        arm = name if name in ('receiver', 'elevation') else 'signed'
        p = np.array(calibration['arms'][arm]['selected']['parameters'])
        records = []
        for doc in donors:
            if doc['role'] != 'validation':
                continue
            rows = dataset(doc, calibration['frequencies'], 'swapped' if name == 'swapped' else arm, permutation=name == 'permuted')
            result = evaluate(p, rows, tau)
            records.append(dict(donor=doc['index'], **result))
        evaluations[name] = dict(score=sum(r['score'] for r in records), per_source={f"{r['donor']}:{s}": v for r in records for s, v in r['per_source'].items()}, records=records)
    reference = evaluations['receiver']['per_source']
    wins = sum(evaluations['signed']['per_source'][s] > v for s, v in reference.items())
    passed = qualified and wins > len(reference) / 2 and all(evaluations['signed']['score'] > evaluations[a]['score'] for a in ('receiver', 'elevation', 'swapped', 'permuted'))
    result = dict(family=number, tau_s=tau, fit=dict(success=bool(fit.success), projected_gradient=projected, derivative_discrepancy=discrepancy, qualified=qualified), evaluations=evaluations, source_wins=wins, source_count=len(reference), passed=bool(passed), independent_validation_scores={a: v['score'] for a, v in calibration['validation'].items()}, sources=sources, elapsed_s=time.monotonic() - started)
    with (HERE / f'fit-{number}.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(dict(family=number, tau_s=tau, qualified=qualified, held={a: v['score'] for a, v in evaluations.items()}, source_wins=wins, source_count=len(reference), passed=bool(passed), elapsed_s=result['elapsed_s'])), flush=True)


if __name__ == '__main__':
    main(int(sys.argv[1]))
