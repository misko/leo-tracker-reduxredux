"""Combine unchanged balanced model over frozen64; retain failures."""
import json
from pathlib import Path

import numpy as np

from regression_batch import digest

HERE = Path(__file__).resolve().parent
baseline_path = HERE/'regression-v1-evaluation-64.json'
assert digest(baseline_path) == 'sha256:97be104787783e3bb81d851ba8664f3a26ac93fe10b617aae605ad8b13372bd7'
baseline = json.loads(baseline_path.read_text())
sources = {str(baseline_path): digest(baseline_path), str(Path(__file__)): digest(__file__)}
rows = []
for name in ['balanced-group-v1', 'balanced-group-expansion-v1', 'balanced-group-regression-v1']:
    path = HERE/f'{name}-evaluation.json'
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    result = json.loads(path.read_text())
    assert result['freeze_sha256'] == digest(HERE/name/'sources.json')
    sources[str(path)] = digest(path)
    rows.extend(r for r in result['rows'] if r['arm'] == 'balanced')
assert len(rows) == len({r['unit'] for r in rows}) == 64
old = {r['unit']: r for r in baseline['rows']}
assert set(old) == {r['unit'] for r in rows}
for row in rows:
    row['baseline_error_m'] = old[row['unit']]['error_m']
    row['improved'] = bool(row['accepted'] and row['error_m'] < row['baseline_error_m'])


def summarize(subset):
    errors = [r['error_m'] for r in subset if r['accepted']]
    return dict(planned=len(subset), accepted=len(errors), improved=sum(r['improved'] for r in subset),
        median_error_m=float(np.median(errors)) if errors else None,
        p90_error_m=float(np.percentile(errors, 90)) if errors else None,
        baseline_median_error_m=float(np.median([r['baseline_error_m'] for r in subset])),
        baseline_p90_error_m=float(np.percentile([r['baseline_error_m'] for r in subset], 90)),
        within1000m=sum(e <= 1000 for e in errors), within3000m=sum(e <= 3000 for e in errors),
        median_warm_runtime_s=float(np.median([r['runtime_s'] for r in subset])),
        maximum_warm_runtime_s=max(r['runtime_s'] for r in subset),
        median_cpu_s=float(np.median([r['cpu_s'] for r in subset if r['cpu_s'] is not None])))


result = dict(summary=summarize(rows), by_dataset={d: summarize([r for r in rows if r['unit'].startswith(d+'-')])
    for d in ['DS9', 'DS10', 'DS11']}, rows=rows, source_sha256=sources,
    qualification='Unchanged satellite-balanced composite score; frozen64 independent baseline '
    'initializations, warm refits with fixed labels. Accuracy quantiles conditional on acceptance; '
    'thresholds retain all64. No fresh cold timing, heldout result, calibrated uncertainty or goal success.')
output = HERE/'balanced-group-regression64-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps({k: v for k, v in result.items() if k not in ['rows', 'source_sha256']}, indent=2))
