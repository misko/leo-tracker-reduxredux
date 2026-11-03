"""Exact saved-prefix selection ablation; does not rerun acquisition."""
import importlib.util
import json
from pathlib import Path

import numpy as np

from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
evaluation = HERE/'heldout-baseline-v1-runtime-16.json'
assert json.loads(evaluation.read_text())['evaluator_sha256'] == digest(HERE/'evaluate_heldout_runtime.py')
original = json.loads(evaluation.read_text())
inputs = {str(evaluation): digest(evaluation)}
rows = []
for row in original['rows']:
    unit = row['unit']
    path = next((HERE/'heldout-baseline-v1').glob('batch-*/'+unit+'.json'))
    assert digest(path) == row['receipt_sha256']
    parent = json.loads(path.read_text())
    verify_sources(parent['source_sha256'])
    verify_sources(parent['inputs'])
    inputs[str(path)] = digest(path)
    for count in [1, 3]:
        subset = parent['fits'][:count]
        scored = [f for f in subset if f['objectives']]
        best = min(scored, key=lambda f: f['objectives'][-1]) if scored else None
        if count == 3:
            assert best == parent['best']
        rows.append(dict(unit=unit, seed_count=count, accepted=bool(best and best['converged']),
            best_state=best['mean'] if best and best['converged'] else None,
            reason=best['reason'] if best else 'no_scored_fit',
            skipped_recorded_fit_seconds=sum(f['seconds'] for f in parent['fits'][count:])))
helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
assert digest(helper) == 'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
spec = importlib.util.spec_from_file_location('offline_reference', helper)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
reference_path = HERE/'ds12-reference-admission-v1.json'
assert digest(reference_path) == reference_path.with_suffix('.sha256').read_text().strip()
inputs[str(reference_path)] = digest(reference_path)
references = {r['unit']: r['reference_latlon'] for r in json.loads(reference_path.read_text())['rows']}
for row in rows:
    state = row.pop('best_state')
    row['error_m'] = reference.distance_m(reference.latlon_from_enu(*state[:2]), references[row['unit']]) if state else None
summaries = {}
for count in [1, 3]:
    chosen = [r for r in rows if r['seed_count'] == count]
    errors = [r['error_m'] for r in chosen if r['accepted']]
    summaries[count] = dict(planned=16, accepted=len(errors), median_error_m=float(np.median(errors)),
        p90_error_m=float(np.percentile(errors, 90)), within1000m=sum(e <= 1000 for e in errors),
        within3000m=sum(e <= 3000 for e in errors),
        median_skipped_recorded_fit_seconds=float(np.median([r['skipped_recorded_fit_seconds'] for r in chosen])))
assert abs(summaries[3]['median_error_m']-2101.5776492649634) < 1e-6
result = dict(summaries=summaries, rows=rows, inputs=inputs,
    source_sha256={str(Path(__file__)): digest(__file__), str(helper): digest(helper)},
    qualification='Exact saved-prefix winner selection with same acquisition and independent seed fits. '
    'No reference-dependent selection. Skipped fit times are accounting estimates, not newly measured '
    'end-to-end runtime. Unconverged winning seeds count as failures, no fallback to a worse score.')
output = HERE/'seed-count-heldout-ablation-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps(summaries, indent=2))
