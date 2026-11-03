"""Full state finite differences including conditional offset scale changes."""
import json
import time
from pathlib import Path

import numpy as np

from candidate_offset_marginal_joint import CandidateJointObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
started = time.monotonic()
rows, sources, inputs = [], {}, {}
for name in ['audit_offset_marginal_gradient.py', 'candidate_offset_marginal_joint.py',
             'offset_marginal_density.py', 'offset_grid_quadrature.py']:
    sources[str(HERE/name)] = digest(HERE/name)
for unit in ['DS9-F025', 'DS10-F028', 'DS11-F018']:
    model = CandidateJointObjective(unit)
    verify_sources(model.base.parent['source_sha256'])
    verify_sources(model.base.parent['inputs'])
    inputs[str(model.base.parent_path)] = digest(model.base.parent_path)
    point = model.initial
    value, analytic = model.evaluate(point)
    control = model.evaluate(point, candidate_weight=0)[0]
    assert abs(control-model.base.parent['best']['objectives'][-1]) < 1e-7
    errors = []
    for step in [.001, .0005]:
        finite = []
        for direction in np.eye(len(point))*step:
            a = model.evaluate(point+direction, gradient=False)[0]
            b = model.evaluate(point-direction, gradient=False)[0]
            finite.append((a-b)/(2*step))
        errors.append(float(np.max(abs(np.asarray(finite)-analytic))))
    assert errors[-1] < .005, (unit, errors)
    rows.append(dict(unit=unit, dimensions=len(point), objective=value,
                     maximum_gradient_errors=errors, parameters=model.parameters))
verify_sources(sources)
result = dict(rows=rows, seconds=time.monotonic()-started, source_sha256=sources,
    input_sha256=inputs, qualification='Training-only starting states, no fits or GPS. '
    'Derivative includes GLS offset, conditional contrast quadratic and offset scale. '
    'Even-degree tracks use numerically refined convolution derivatives; odd degrees '
    'use exact rational Fourier sums. This is not a geographic improvement claim.')
output = HERE/'offset-marginal-gradient-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps(dict(rows=rows, seconds=result['seconds']), indent=2))
