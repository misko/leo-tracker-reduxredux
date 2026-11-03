"""Verify bounded association audits without introducing geographic selection."""
import json
from pathlib import Path

from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
directory = HERE/'calibrated-proposal-audit-v1'
freeze = directory/'sources.json'
assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
frozen = json.loads(freeze.read_text())
verify_sources(frozen['source_sha256'])
rows = []
for unit in frozen['units']:
    path = directory/(unit+'.json')
    launch = json.loads(path.with_suffix('.launch.json').read_text())
    failures, result = [], {}
    try:
        assert launch['returncode'] == 0 and launch['within_budget'] and not launch['timed_out']
        assert launch['freeze_sha256'] == digest(freeze)
        assert digest(path) == launch['receipt_sha256']
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        result = json.loads(path.read_text())
        assert result['complete'] and result['unit'] == unit
        assert result['freeze_sha256'] == digest(freeze)
        assert result['evaluated_alternatives'] == len(result['rows'])
    except (AssertionError, OSError, KeyError) as error:
        failures.append(type(error).__name__+': '+str(error))
    rows.append(dict(unit=unit, valid=not failures, failures=failures,
        evaluated=result.get('evaluated_alternatives', 0),
        positive=result.get('full_objective_improvements', 0), best=result.get('best'),
        seconds=launch['elapsed_seconds'], cpu_s=result.get('cpu_s'),
        positive_alternatives=[p for p in result.get('rows', []) if p['full_objective_gain'] > 1e-7]))
summary = dict(planned=len(rows), valid=sum(r['valid'] for r in rows),
    evaluated_alternatives=sum(r['evaluated'] for r in rows),
    positive_alternatives=sum(r['positive'] for r in rows),
    scans_with_positive_alternatives=sum(r['positive'] > 0 for r in rows), rows=rows,
    freeze_sha256=digest(freeze), summarizer_sha256=digest(__file__),
    qualification='Fixed calibrated endpoints; one best-training alternative per track, not '
    'exhaustive association search. Full objective and exact unused-epoch profiling checked '
    'against independent scalar and vectorized evaluations. Positive gain does not establish '
    'geographic improvement. No GPS or fits. Incomplete scans remain failures.')
output = HERE/'calibrated-proposal-audit-v1-summary.json'
with output.open('x') as stream:
    json.dump(summary, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps(summary, indent=2))
