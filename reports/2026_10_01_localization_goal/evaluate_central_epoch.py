"""Validate all pilot outcomes before offline geographic scoring."""
import importlib.util
import json
from pathlib import Path

import numpy as np

from central_epoch_pilot import CentralEpochObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
directory = HERE/'central-epoch-v1'
freeze = directory/'sources.json'
assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
frozen = json.loads(freeze.read_text())
verify_sources(frozen['source_sha256'])
rows = []
states = {}
for unit, arm in frozen['pairs']:
    path = directory/f'{unit}-{arm}.json'
    receipt = {}
    errors = []
    gradient_error = None
    numeric_decrement = None
    launch = json.loads(path.with_suffix('.launch.json').read_text())
    try:
        assert launch['returncode'] == 0 and launch['within_budget'] and not launch['timed_out']
        assert launch['freeze_sha256'] == digest(freeze)
        assert digest(path) == launch['receipt_sha256']
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        receipt = json.loads(path.read_text())
        assert receipt['converged'], receipt['reason']
        model = CentralEpochObjective(unit, arm)
        assert receipt['parent_sha256'] == digest(model.path)
        assert receipt['initial'] == model.initial.tolist()
        assert receipt['assignments'] == model.assignments
        assert receipt['columns'] == model.columns.tolist()
        assert receipt['inputs'] == model.parent['inputs']
        assert receipt['height'] == model.parent['height']
        state = np.asarray(receipt['state'])
        point = state[model.columns]
        assert model.support(point)
        unused = sorted(set(range(len(state)))-set(model.columns))
        assert np.array_equal(state[unused], model.initial[unused])
        metric = model.metric()
        assert np.allclose(metric, receipt['metric'], atol=1e-10, rtol=1e-10)
        value, gradient = model.evaluate(point)
        assert abs(value-receipt['final_objective']) < 1e-7
        assert abs(value-receipt['objectives'][-1]) < 1e-7
        assert np.all(np.diff(receipt['objectives']) <= 1e-9)
        assert gradient@np.linalg.solve(metric, gradient) <= 1e-6
        finite = np.array([(model.evaluate(point+d, False)[0]-model.evaluate(point-d, False)[0])/.001
                           for d in np.eye(len(point))*.0005])
        gradient_error = float(np.max(abs(finite-gradient)))
        numeric_decrement = float(finite@np.linalg.solve(metric, finite))
        assert gradient_error < .005 and numeric_decrement < 1e-5
        if arm == 'gaussian':
            assert abs(value-model.parent['best']['objectives'][-1]) < 1e-6
            assert np.linalg.norm(state[:2]-model.initial[:2])*1000 < .1
        states[(unit, arm)] = state
    except (AssertionError, OSError, ValueError, KeyError) as error:
        errors.append(type(error).__name__+': '+str(error))
    rows.append(dict(unit=unit, arm=arm, accepted=not errors, failures=errors,
        reason=receipt.get('reason'), iterations=receipt.get('iterations'),
        gradient_error=gradient_error, numeric_decrement_squared=numeric_decrement,
        runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_s'),
        receipt_sha256=launch['receipt_sha256']))

# Only after every process outcome and numerical acceptance decision is fixed.
helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
assert digest(helper) == 'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
spec = importlib.util.spec_from_file_location('offline_reference', helper)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
for row in rows:
    row['error_m'] = None
    if row['accepted']:
        position = states[(row['unit'], row['arm'])][:2]
        row['error_m'] = reference.distance_m(reference.latlon_from_enu(*position), reference.REFERENCE)
candidates = [r for r in rows if r['arm'] == 'student']
errors = [r['error_m'] for r in candidates if r['accepted']]
result = dict(rows=rows, candidate_denominator=len(candidates), accepted=len(errors),
    median_error_m=float(np.median(errors)) if errors else None,
    p90_error_m=float(np.percentile(errors, 90)) if errors else None,
    within1000m=sum(e <= 1000 for e in errors), within3000m=sum(e <= 3000 for e in errors),
    freeze_sha256=digest(freeze), evaluator_sha256=digest(__file__), reference_sha256=digest(helper),
    qualification='Exposed three-scan development pilot, warm fixed-label fitting. '
    'Failures retained in denominator, errors conditional on acceptance. '
    'No cold acquisition, heldout validation, uncertainty calibration or goal success.')
output = HERE/'central-epoch-v1-evaluation.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps(result, indent=2))
