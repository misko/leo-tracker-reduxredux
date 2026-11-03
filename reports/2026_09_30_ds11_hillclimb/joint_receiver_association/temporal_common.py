"""One fixed-persistence geometry ablation, calibrated only on earlier data."""
import json
from pathlib import Path
import time
import numpy as np
from scipy.optimize import minimize
from temporal_fit import dataset, score
from temporal_validate import evaluate
from doppler_pilot import digest, read

HERE = Path(__file__).resolve().parent


def main():
    start = time.monotonic()
    null = read(HERE / 'temporal-fit-receiver.json')
    independent = read(HERE / 'conditional-fit.json')
    donors = [read(HERE / f'donor-{i}.json') for i in (0, 1)]
    for obj in (null, independent, *donors):
        for p, h in obj['sources'].items():
            assert digest(p) == h, p
    logtau = null['selected']['parameters'][-1]
    arms = {'receiver': dict(parameters=null['selected']['parameters'], fits=[null['selected']])}
    paths = [Path(__file__), HERE / 'TEMPORAL_COMMON_PROTOCOL.md', HERE / 'temporal-fit-receiver.json', HERE / 'conditional-fit.json', HERE / 'donor-0.json', HERE / 'donor-1.json', HERE / 'temporal_fit.py', HERE / 'temporal_validate.py', HERE / 'temporal_receiver.py']
    for arm in ('elevation', 'signed'):
        previous = HERE / f'temporal-fit-{arm}.json'
        paths.append(previous)
        rows = dataset(donors[0], independent['frequencies'], arm)
        scales = np.r_[np.full(8, 5.), 10.]
        def objective(p):
            value, gradient, _ = score(np.r_[p, logtau], rows)
            return -value + .5 * np.sum((p / scales)**2), -gradient[:-1] + p / scales**2
        fits = []
        for initial in (read(previous)['selected']['parameters'][:-1], independent['arms'][arm]['selected']['parameters']):
            fit = minimize(objective, initial, method='L-BFGS-B', jac=True, bounds=[(-20., 20.)] * 8 + [(0., 40.)], options=dict(maxiter=300, ftol=1e-12, gtol=1e-6))
            fits.append(dict(parameters=fit.x.tolist(), objective=float(fit.fun), success=bool(fit.success), iterations=int(fit.nit), message=str(fit.message)))
        selected = min(fits, key=lambda r: r['objective'])
        assert selected['success']
        p = np.array(selected['parameters'])
        analytic = objective(p)[1]
        numerical = np.array([(objective(p + np.eye(len(p))[i] * 1e-5)[0] - objective(p - np.eye(len(p))[i] * 1e-5)[0]) / 2e-5 for i in range(len(p))])
        discrepancy = float(np.max(np.abs(analytic - numerical)))
        assert discrepancy < 1e-4
        arms[arm] = dict(parameters=np.r_[p, logtau].tolist(), fits=fits, derivative_discrepancy=discrepancy)
    for arm, out in arms.items():
        out['evaluations'] = [evaluate(np.array(out['parameters']), dataset(d, independent['frequencies'], arm)) for d in donors]
    p = np.array(arms['signed']['parameters'])
    controls = {name: evaluate(p, dataset(donors[1], independent['frequencies'], 'swapped' if name == 'swapped' else 'signed', permutation=name == 'permuted')) for name in ('swapped', 'permuted')}
    signed, base = arms['signed']['evaluations'][1], arms['receiver']['evaluations'][1]
    wins = sum(signed['sources_held'][s] > v for s, v in base['sources_held'].items())
    passed = signed['held'] > base['held'] and signed['held'] > arms['elevation']['evaluations'][1]['held'] and all(signed['held'] > c['held'] for c in controls.values()) and wins > len(base['sources_held']) / 2
    result = dict(arms=arms, controls=controls, common_tau_s=float(np.exp(logtau)), source_wins=wins, source_count=len(base['sources_held']), temporal_common_gate_passed=bool(passed), frequencies=independent['frequencies'], sources={str(p): digest(p) for p in paths}, elapsed_s=time.monotonic() - start)
    with (HERE / 'temporal-common.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(dict(held={a: v['evaluations'][1]['held'] for a, v in arms.items()}, controls={a: v['held'] for a, v in controls.items()}, wins=wins, count=len(base['sources_held']), passed=bool(passed), elapsed_s=result['elapsed_s']), indent=2))


if __name__ == '__main__':
    main()
