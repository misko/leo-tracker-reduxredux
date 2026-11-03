"""Compare audited fresh delta runs to earlier accepted alternating runs."""
import json
from pathlib import Path

import numpy as np

from regression_batch import digest

HERE = Path(__file__).resolve().parent
evaluations = []
inputs = {}
for name in ['calibrated-alternating-v1', 'calibrated-delta-search-v1']:
    path = HERE/(name+'-evaluation.json')
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    inputs[str(path)] = digest(path)
    evaluations.append({(r['unit'], r['arm']): r for r in json.loads(path.read_text())['rows']})
rows = []
for key, after in evaluations[1].items():
    before = evaluations[0][key]
    if not before['valid'] or not after['valid']:
        continue
    unit, arm = key
    receipts = []
    for folder in ['calibrated-alternating-v1', 'calibrated-delta-search-v1']:
        path = HERE/folder/(unit+'-'+arm+'.json')
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        inputs[str(path)] = digest(path)
        receipts.append(json.loads(path.read_text()))
    first, second = receipts
    assert first['assignments'] == second['assignments']
    assert [(r['iteration'], r['track'], r['identity']) for r in first['trials']] == [
        (r['iteration'], r['track'], r['identity']) for r in second['trials']]
    difference = np.asarray(first['full_state'])-second['full_state']
    rows.append(dict(unit=unit, arm=arm, maximum_state_difference=float(np.max(abs(difference))),
        position_difference_m=float(np.linalg.norm(difference[:2])*1000),
        old_seconds=before['runtime_s'], new_seconds=after['runtime_s']))
result = dict(rows=rows, input_sha256=inputs, source_sha256=digest(__file__),
    compared_accepted_arms=len(rows),
    maximum_state_difference=max(r['maximum_state_difference'] for r in rows),
    maximum_position_difference_m=max(r['position_difference_m'] for r in rows),
    qualification='Same accepted control/candidate pairs only; prior failures excluded from '
    'state equivalence, retained in their original evaluations. Identical assignments and '
    'proposal membership/order asserted. Historical timing, not a host-load-controlled trial.')
path = HERE/'calibrated-delta-equivalence-v1.json'
with path.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
path.with_suffix('.sha256').write_text(digest(path)+'\n')
print(json.dumps({k: v for k, v in result.items() if k not in ['rows', 'input_sha256']}, indent=2))
