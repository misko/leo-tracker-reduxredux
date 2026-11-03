"""Training-only fit of conditional time-correlated receiver states."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from conditional_receiver import design
from temporal_receiver import sequence_score
from doppler_pilot import read, digest

HERE = Path(__file__).resolve().parent


def dataset(donor, frequencies, arm, permutation=False):
    lanes = donor['lanes']
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
        keep = (bits >= 0).all(axis=1) & (bits.sum(axis=1) > 0)
        other = lanes[alternate[i]]
        assert other['times_s'] == lane['times_s']
        los = np.asarray(other['los_enu'])[keep]
        x = design(los, np.full(len(los), frequencies.index(lane['rf_hz'])), len(frequencies), arm)
        features = np.stack((x[:, 0], x[:, 1], x.sum(axis=1)), axis=1)
        rows.append(dict(times=np.asarray(lane['times_s'])[keep], states=bits[keep, 0] + 2 * bits[keep, 1], train=np.asarray(lane['training_mask'], bool)[keep], features=features, source=i))
    return rows


def score(parameters, rows, split='training', with_gradient=True):
    total = 0.
    gradient = np.zeros(len(parameters))
    per_source = {}
    for row in rows:
        features = row['features']
        weights = features @ parameters[:-1]
        logp = weights - logsumexp(weights, axis=1)[:, None]
        derivative = np.zeros(logp.shape + (len(parameters),))
        if with_gradient:
            derivative[..., :-1] = features - np.einsum('ns,nsp->np', np.exp(logp), features)[:, None, :]
        mask = row['train'] if split == 'training' else np.ones(len(row['times']), bool)
        value, grad = sequence_score(row['times'], logp[None], row['states'], mask, np.exp(parameters[-1]), derivative[None], len(parameters) - 1 if with_gradient else None)
        total += value[0]
        gradient += grad[0]
        per_source[str(row['source'])] = float(value[0])
    return float(total), gradient, per_source


def main(arm):
    start = time.monotonic()
    independent = read(HERE / 'conditional-fit.json')
    donor = read(HERE / 'donor-0.json')
    for p, h in donor['sources'].items():
        assert digest(p) == h, p
    rows = dataset(donor, independent['frequencies'], arm)
    initial = np.array(independent['arms'][arm]['selected']['parameters'])
    scales = np.r_[np.full(8, 5.), [] if arm == 'receiver' else [10.], 3.]
    bounds = [(-20., 20.)] * 8 + ([] if arm == 'receiver' else [(0., 40.)]) + [(np.log(.01), np.log(60.))]
    def objective(p):
        value, gradient, _ = score(p, rows)
        return -value + .5 * np.sum((p / scales)**2), -gradient + p / scales**2
    fits = []
    for tau in (.1, 1., 10.):
        fit = minimize(objective, np.r_[initial, np.log(tau)], method='L-BFGS-B', jac=True, bounds=bounds, options=dict(maxiter=300, ftol=1e-12, gtol=1e-6))
        fits.append(dict(parameters=fit.x.tolist(), objective=float(fit.fun), success=bool(fit.success), message=str(fit.message), iterations=int(fit.nit), gradient_max=float(np.max(np.abs(fit.jac)))))
        print(json.dumps(dict(arm=arm, initial_tau=tau, success=bool(fit.success), iterations=int(fit.nit), objective=float(fit.fun), fitted_tau=float(np.exp(fit.x[-1])))), flush=True)
    selected = min(fits, key=lambda r: r['objective'])
    assert selected['success']
    parameters = np.array(selected['parameters'])
    analytic = objective(parameters)[1]
    numerical = np.array([(objective(parameters + np.eye(len(parameters))[i] * 1e-5)[0] - objective(parameters - np.eye(len(parameters))[i] * 1e-5)[0]) / 2e-5 for i in range(len(parameters))])
    discrepancy = float(np.max(np.abs(analytic - numerical)))
    assert discrepancy < 1e-4, discrepancy
    paths = (Path(__file__), HERE / 'temporal_receiver.py', HERE / 'test_temporal_receiver.py', HERE / 'TEMPORAL_PROTOCOL.md', HERE / 'conditional-fit.json', HERE / 'donor-0.json')
    output = dict(arm=arm, fits=fits, selected=selected, derivative_discrepancy=discrepancy, elapsed_s=time.monotonic() - start, sources={str(p): digest(p) for p in paths})
    with (HERE / f'temporal-fit-{arm}.json').open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps(dict(arm=arm, elapsed_s=output['elapsed_s'], discrepancy=discrepancy)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--arm', required=True, choices=['receiver', 'elevation', 'signed'])
    main(parser.parse_args().arm)
