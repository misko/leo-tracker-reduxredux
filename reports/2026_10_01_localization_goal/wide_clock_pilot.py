"""Bounded shared-clock prior pilot."""
import argparse
import json
import resource
import time

import numpy as np
from wide_clock_objective import WideClockObjective, ARMS
from regression_batch import digest
from leo.analysis.localization_joint_search import fit_joint_objective


def main():
    start = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--arm', choices=ARMS, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    model = WideClockObjective(args.unit, args.arm)
    metric = model.metric()
    fit = fit_joint_objective(model.initial[model.columns], model.evaluate, metric,
                             model.support, deadline=start+25., max_iterations=64)
    state = model.initial.copy()
    state[model.columns] = fit.mean
    value, gradient = model.evaluate(fit.mean)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result = dict(unit=args.unit, arm=args.arm, parent_sha256=digest(model.path),
        assignments=model.assignments, clock_sigma_s=model.clock_sigma_s, columns=model.columns.tolist(),
        initial=model.initial.tolist(), state=state.tolist(), metric=metric.tolist(),
        converged=fit.converged, reason=fit.reason, iterations=fit.iterations,
        objectives=list(fit.objectives), final_objective=value,
        decrement_squared=float(gradient@np.linalg.solve(metric, gradient)),
        seconds=time.monotonic()-start, cpu_s=usage.ru_utime+usage.ru_stime,
        inputs=model.parent['inputs'], height=model.parent['height'],
        qualification='Warm original-baseline initialization, fixed hard identities. '
        'Wider shared-clock prior comparison; not a cold acquisition result.')
    from pathlib import Path
    output = Path(args.output)
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(unit=args.unit, arm=args.arm, reason=fit.reason,
                          seconds=result['seconds'])))


if __name__ == '__main__':
    main()
