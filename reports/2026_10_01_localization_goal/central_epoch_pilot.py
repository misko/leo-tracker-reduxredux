"""Warm fixed-label epoch prior experiment; estimator never reads reference."""
import argparse
import json
import resource
import time

import numpy as np

from fixed_reference_nuisance import ConditionalObjective
from regression_batch import digest
from leo.analysis.localization_joint_search import fit_joint_objective
from leo.analysis.localization_prior import ScalarStudentPriorPort


class CentralEpochObjective(ConditionalObjective):
    def __init__(self, unit, arm):
        super().__init__(unit, 'control')
        self.columns = np.array([0, 1, 2, 3, 4, *self.epochs])
        self.arm = arm
        self.factors = []
        if arm == 'student':
            self.precision[self.epochs] = 0.
            self.factors = [ScalarStudentPriorPort(int(k), len(self.initial), .625,
                            f'central-epoch-{k}') for k in self.epochs]

    def evaluate(self, reduced, gradient=True):
        value, grad = super().evaluate(reduced, gradient)
        state = self.initial.copy()
        state[self.columns] = reduced
        for factor in self.factors:
            # Replace normalized Gaussian with normalized t4, retaining the
            # baseline's omitted Gaussian normalization constant convention.
            value -= factor.score_selected(state, 0)+.5*np.log(2*np.pi*.25)
            if gradient:
                k = int(np.flatnonzero(self.columns == factor.column)[0])
                e = state[factor.column]
                grad[k] += 5*e/(1.25+e*e)
        return value, grad

    def metric(self):
        matrix = super().metric()
        for factor in self.factors:
            k = int(np.flatnonzero(self.columns == factor.column)[0])
            e = self.initial[factor.column]
            matrix[k, k] += 5/(1.25+e*e)
        return matrix


def main():
    start = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--arm', choices=['gaussian', 'student'], required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    model = CentralEpochObjective(args.unit, args.arm)
    metric = model.metric()
    fit = fit_joint_objective(model.initial[model.columns], model.evaluate, metric,
                             model.support, deadline=start+25., max_iterations=64)
    state = model.initial.copy()
    state[model.columns] = fit.mean
    value, gradient = model.evaluate(fit.mean)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result = dict(unit=args.unit, arm=args.arm, parent_sha256=digest(model.path),
        assignments=model.assignments, columns=model.columns.tolist(),
        initial=model.initial.tolist(), state=state.tolist(), metric=metric.tolist(),
        converged=fit.converged, reason=fit.reason, iterations=fit.iterations,
        objectives=list(fit.objectives), final_objective=value,
        decrement_squared=float(gradient@np.linalg.solve(metric, gradient)),
        seconds=time.monotonic()-start, cpu_s=usage.ru_utime+usage.ru_stime,
        inputs=model.parent['inputs'], height=model.parent['height'],
        qualification='Warm original-baseline initialization, fixed hard identities. '
        'Student t4 variance .625s², central curvature4. Not a cold acquisition result.')
    from pathlib import Path
    output = Path(args.output)
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(unit=args.unit, arm=args.arm, reason=fit.reason,
                          seconds=result['seconds'])))


if __name__ == '__main__':
    main()
