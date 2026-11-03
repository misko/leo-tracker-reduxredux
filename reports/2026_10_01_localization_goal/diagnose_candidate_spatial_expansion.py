"""Bounded warm spatial optimization of a composite candidate-level objective."""
import argparse
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
from candidate_spatial_expansion_adapter import CandidateSpatialObjective
from regression_batch import digest, verify_sources

from leo.analysis.localization_position_search import fit_position_objective

HERE = Path(__file__).resolve().parent


def main():
    start = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--arm', choices=['control', 'candidate'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    model = CandidateSpatialObjective(args.unit)
    verify_sources(model.parent['source_sha256'])
    verify_sources(model.parent['inputs'])
    parity = model.check_parity()
    weight = float(args.arm == 'candidate')

    def objective(point):
        train, candidate = model.components(point)
        return train-weight*candidate

    fit = fit_position_objective(model.initial[:2], objective,
        lambda point: np.linalg.norm(point) <= 250., deadline=start+25., max_iterations=16)
    result = dict(unit=args.unit, arm=args.arm, parent_sha256=digest(model.parent_path),
                  inputs=model.parent['inputs'], height=model.parent['height'],
                  assignments=model.assignments, initial_point=model.initial[:2].tolist(),
                  point=fit.position.tolist(), objectives=list(fit.objectives),
                  converged=fit.converged, reason=fit.reason, iterations=fit.iterations,
                  calls=model.calls, parity=parity,
                  final_components=model.components(fit.position),
                  position_change_m=float(np.linalg.norm(fit.position-model.initial[:2])*1000),
                  sources={})
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.suffix == '.py' and path.is_relative_to(HERE.parents[1]):
                result['sources'][str(path)] = digest(path)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result.update(seconds=time.monotonic()-start, cpu_s=usage.ru_utime+usage.ru_stime,
        qualification='Warm fixed-identity/fixed-nuisance spatial pilot, not cold inference. '
        'Previously checking candidate observations are now training evidence. Objective is '
        'original track NLL minus candidate-set composite log ratio; disjoint source sets. '
        'Checking observations cannot validate this fitted model. No GPS; unchanged uniform '
        'Sacramento250km support and100ftMSL height. Frequency offsets reprofiled on original '
        'training samples at each position; not integrated with new candidates.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps(dict(unit=args.unit, arm=args.arm, converged=fit.converged,
                          reason=fit.reason, seconds=result['seconds'])))


if __name__ == '__main__':
    main()
