"""Frozen transfer gate for the refresh-state receiver calibration."""
import json
from pathlib import Path
import numpy as np
from temporal_fit import dataset, score
from doppler_pilot import digest, read

HERE = Path(__file__).resolve().parent


def evaluate(parameters, rows):
    train, _, sources_train = score(parameters, rows, 'training', False)
    joint, _, sources_joint = score(parameters, rows, 'joint', False)
    return dict(training=train, held=joint - train, sources_held={s: sources_joint[s] - v for s, v in sources_train.items()})


def main():
    independent = read(HERE / 'conditional-fit.json')
    paths = [Path(__file__), HERE / 'conditional-fit.json', HERE / 'donor-0.json', HERE / 'donor-1.json']
    donors = [read(HERE / f'donor-{i}.json') for i in (0, 1)]
    for donor in donors:
        for p, h in donor['sources'].items():
            assert digest(p) == h, p
    arms = {}
    for arm in ('receiver', 'elevation', 'signed'):
        path = HERE / f'temporal-fit-{arm}.json'
        fit = read(path)
        paths.append(path)
        for p, h in fit['sources'].items():
            assert digest(p) == h, p
        parameters = np.array(fit['selected']['parameters'])
        evaluations = [evaluate(parameters, dataset(d, independent['frequencies'], arm)) for d in donors]
        arms[arm] = dict(parameters=parameters.tolist(), tau_s=float(np.exp(parameters[-1])), evaluations=evaluations)
    parameters = np.array(arms['signed']['parameters'])
    controls = {name: evaluate(parameters, dataset(donors[1], independent['frequencies'], 'swapped' if name == 'swapped' else 'signed', permutation=name == 'permuted')) for name in ('swapped', 'permuted')}
    signed = arms['signed']['evaluations'][1]
    base = arms['receiver']['evaluations'][1]
    wins = sum(signed['sources_held'][s] > v for s, v in base['sources_held'].items())
    passed = signed['held'] > base['held'] and signed['held'] > arms['elevation']['evaluations'][1]['held'] and all(signed['held'] > c['held'] for c in controls.values()) and wins > len(base['sources_held']) / 2
    original = next(r['score'] for r in independent['arms']['signed']['evaluations'] if r['donor'] == 1 and r['split'] == 'held')
    output = dict(arms=arms, controls=controls, source_wins=wins, source_count=len(base['sources_held']), independent_signed_held=original, temporal_screen_passed=bool(passed), frequencies=independent['frequencies'], sources={str(p): digest(p) for p in paths})
    with (HERE / 'temporal-validation.json').open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps(dict(arms={a: dict(tau_s=v['tau_s'], held=v['evaluations'][1]['held']) for a, v in arms.items()}, controls={a: v['held'] for a, v in controls.items()}, independent_signed_held=original, wins=wins, source_count=len(base['sources_held']), passed=bool(passed)), indent=2))


if __name__ == '__main__':
    main()
