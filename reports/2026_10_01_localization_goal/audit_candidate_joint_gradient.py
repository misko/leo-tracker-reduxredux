"""Real-data value parity and derivative checks before any joint fitting."""
import json
import time
from pathlib import Path

import numpy as np
from candidate_joint_adapter import CandidateJointObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    start = time.monotonic()
    rows = []
    for unit in ['DS9-F001', 'DS10-F056', 'DS11-F001']:
        model = CandidateJointObjective(unit)
        verify_sources(model.base.parent['sources'] if 'sources' in model.base.parent
                       else model.base.parent['source_sha256'])
        verify_sources(model.base.parent['inputs'])
        x = model.initial
        value, gradient = model.evaluate(x)
        scalar = model.base(x[:2])
        assert abs(value-scalar) < 1e-7
        errors, refined_errors = [], []
        for direction in np.eye(len(x)):
            finite = []
            for step in [.001, .0005]:
                plus = model.evaluate(x+step*direction, gradient=False)[0]
                minus = model.evaluate(x-step*direction, gradient=False)[0]
                finite.append((plus-minus)/(2*step))
            analytic = float(gradient@direction)
            errors.append(abs(analytic-finite[0]))
            refined_errors.append(abs(analytic-finite[1]))
        assert max(refined_errors) < .005
        control, control_gradient = model.evaluate(x, candidate_weight=0.)
        assert abs(control-model.base.parent['best']['objectives'][-1]) < 1e-7
        rows.append(dict(unit=unit, columns=model.columns.tolist(),
                         value_parity=value-scalar, errors=errors, refined_errors=refined_errors,
                         maximum_refined_error=max(refined_errors),
                         gradient=gradient.tolist(), control_gradient=control_gradient.tolist(),
                         control_value_parity=control-model.base.parent['best']['objectives'][-1],
                         parent_sha256=digest(model.base.parent_path)))
    files = [Path(__file__), HERE/'candidate_joint_adapter.py',
             HERE.parents[1]/'src/leo/analysis/localization_candidate_derivatives.py']
    result = dict(rows=rows, seconds=time.monotonic()-start,
                  source_sha256={str(p): digest(p) for p in files},
                  qualification='Derivative audit only, no fitting, GPS, source reassignment or '
                  'geographic improvement. Position derivative uses exact line-of-sight chain '
                  'rule with numerical fixed-MSL receiver surface derivative; clock/epoch '
                  'derivatives use original orbit-interpolator finite differences at1e-4s. '
                  'Profiled training-offset derivative retained. Same composite model as '
                  'spatial pilot at fixed nuisance values; all shared nuisance columns '
                  'now exposed.')
    output = HERE/'candidate-joint-gradient-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(seconds=result['seconds'], rows=[dict(
        unit=r['unit'], dimensions=len(r['columns']), parity=r['value_parity'],
        max_error=r['maximum_refined_error']) for r in rows]), indent=2))


if __name__ == '__main__':
    main()
