"""REFERENCE-INFORMED conditional diagnosis, never a localization result."""
import argparse
import importlib.util
import json
import resource
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from acquisition_dot import prepare
from regression_batch import digest, verify_sources
from leo.analysis.localization_joint_search import fit_joint_objective

HERE = Path(__file__).resolve().parent


def reference_position():
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == 'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec = importlib.util.spec_from_file_location('offline_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    lat0, lon0 = np.radians(reference.CENTER)
    lat, lon = np.radians(reference.REFERENCE)
    east = np.cos(lat)*np.sin(lon-lon0)
    north = np.cos(lat0)*np.sin(lat)-np.sin(lat0)*np.cos(lat)*np.cos(lon-lon0)
    dot = np.sin(lat0)*np.sin(lat)+np.cos(lat0)*np.cos(lat)*np.cos(lon-lon0)
    length = np.hypot(east, north)
    point = reference.EARTH_RADIUS_KM*np.arctan2(length, dot)*np.array([east, north])/length
    assert reference.distance_m(reference.latlon_from_enu(*point), reference.REFERENCE) < .001
    return point, helper


class ConditionalObjective:
    def __init__(self, unit, arm):
        self.path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
        assert digest(self.path) == json.loads(self.path.with_suffix('.seal.json').read_text())['prediction_sha256']
        self.parent = json.loads(self.path.read_text())
        verify_sources(self.parent['source_sha256'])
        verify_sources(self.parent['inputs'])
        self.scan, self.height, self.ports = prepare(unit)
        assert self.scan.inputs == self.parent['inputs']
        assert self.height.input_bindings == self.parent['height']
        assert [list(p.observation_ids) for p in self.ports] == self.parent['observations']
        self.original = np.asarray(self.parent['best']['mean'])
        self.assignments = [int(np.argmax(p.score_all(self.original))) for p in self.ports]
        self.epochs = sorted({5+i for p, i in zip(self.ports, self.assignments, strict=True) if i < p.candidate_count})
        self.columns = np.array([2, 3, 4, *self.epochs])
        self.initial = self.original.copy()
        if arm == 'reference':
            self.initial[:2] = reference_position()[0]
        self.precision = np.r_[0., 0., 1., np.full(len(self.original)-3, 4.)]

    def evaluate(self, reduced, gradient=True):
        state = self.initial.copy()
        state[self.columns] = reduced
        value = float(.5*(self.precision*state)@state)
        grad = (self.precision*state)[self.columns]
        for port, identity in zip(self.ports, self.assignments, strict=True):
            value -= port.score_selected(state, identity)
            if gradient and identity < port.candidate_count:
                prediction = port.predict_selected(state, identity)
                residual = port.observation-prediction.mean
                solved = np.linalg.solve(prediction.covariance, residual)
                weight = (4+len(residual))/(4+float(residual@solved))
                grad -= weight*prediction.jacobian[:, self.columns].T@solved
        return value, grad if gradient else None

    def metric(self):
        matrix = np.diag(self.precision[self.columns])
        for port, identity in zip(self.ports, self.assignments, strict=True):
            if identity == port.candidate_count:
                continue
            prediction = port.predict_selected(self.initial, identity)
            residual = port.observation-prediction.mean
            solved = np.linalg.solve(prediction.covariance, residual)
            weight = (4+len(residual))/(4+float(residual@solved))
            j = prediction.jacobian[:, self.columns]
            matrix += weight*j.T@np.linalg.solve(prediction.covariance, j)
        return (matrix+matrix.T)/2

    def support(self, reduced):
        state = self.initial.copy()
        state[self.columns] = reduced
        lower = min(t.times_s.min() for _, t in self.scan.tracks)
        upper = max(t.times_s.max() for _, t in self.scan.tracks)
        shifts = state[2]+state[5:]
        return (np.all(np.isfinite(state)) and np.linalg.norm(state[:2]) <= 250
                and np.all(lower+shifts >= self.scan.bank.times_s[1]+1e-4)
                and np.all(upper+shifts <= self.scan.bank.times_s[-2]-1e-4))

    def decompose(self, state):
        groups = defaultdict(lambda: dict(tracks=[], observation_nll=0., epoch_prior=0.))
        for k, (port, identity) in enumerate(zip(self.ports, self.assignments, strict=True)):
            key = str(self.scan.bank.norad_ids[identity]) if identity < port.candidate_count else 'clutter'
            groups[key]['tracks'].append(k)
            groups[key]['observation_nll'] -= float(port.score_selected(state, identity))
            if identity < port.candidate_count:
                groups[key]['epoch_prior'] = 2*float(state[5+identity]**2)
        shared = float(.5*state[2]**2+2*np.sum(state[3:5]**2))
        unused = sorted(set(range(5, len(state)))-set(self.epochs))
        unused_prior = float(2*np.sum(state[unused]**2))
        return dict(groups=dict(groups), shared_prior=shared, unused_epoch_prior=unused_prior)


def main():
    start = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--arm', choices=['control', 'reference'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    model = ConditionalObjective(args.unit, args.arm)
    metric = model.metric()
    fit = fit_joint_objective(model.initial[model.columns], model.evaluate, metric, model.support,
                             deadline=start+25., max_iterations=64)
    state = model.initial.copy()
    state[model.columns] = fit.mean
    value, gradient = model.evaluate(fit.mean)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result = dict(unit=args.unit, arm=args.arm, reference_informed=args.arm == 'reference',
        parent_sha256=digest(model.path), assignments=model.assignments, columns=model.columns.tolist(),
        initial=model.initial.tolist(), state=state.tolist(), metric=metric.tolist(),
        converged=fit.converged, reason=fit.reason, iterations=fit.iterations,
        objectives=list(fit.objectives), final_objective=value,
        decrement_squared=float(gradient@np.linalg.solve(metric, gradient)),
        decomposition=model.decompose(state), seconds=time.monotonic()-start,
        cpu_s=usage.ru_utime+usage.ru_stime, inputs=model.parent['inputs'], height=model.parent['height'],
        qualification='Reference-informed conditional nuisance fit, fixed baseline identities. '
        'Single inherited nuisance start; local optimum only. Never a localization result, '
        'new prior, GPS-based association rule, or deployment correction.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps(dict(unit=args.unit, arm=args.arm, reason=fit.reason, seconds=result['seconds'])))


if __name__ == '__main__':
    main()
