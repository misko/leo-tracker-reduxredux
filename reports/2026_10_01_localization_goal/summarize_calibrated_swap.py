"""Full12panel: one audited swap when available, otherwise retain parent."""
import json
from pathlib import Path

import numpy as np

from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
names = ['calibrated-joint-panel-v1.json', 'calibrated-proposal-audit-v1-summary.json',
         'calibrated-swap-v1-evaluation.json']
sources = {str(Path(__file__)): digest(__file__)}
loaded = []
for name in names:
    path = HERE/name
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    sources[str(path)] = digest(path)
    loaded.append(json.loads(path.read_text()))
parent, audit, fitting = loaded
assert audit['valid'] == 12
new = {r['unit']: r for r in fitting['rows'] if r['arm'] == 'candidate'}
assert set(new) == {r['unit'] for r in audit['rows'] if r['positive'] > 0}
rows = []
for row in parent['rows']:
    r = dict(row)
    changed = new.get(r['unit'])
    r['swap_attempted'] = changed is not None
    r['final_error_m'] = changed['error_m'] if changed else r['calibrated_joint_error_m']
    r['valid'] = changed['valid'] if changed else r['valid']
    r['swap_failures'] = changed['audit_errors'] if changed else []
    r['swap_runtime_s'] = changed['runtime_s'] if changed else 0.
    rows.append(r)
valid = [r for r in rows if r['valid']]
summary = {}
for key in ['original_all_data_error_m', 'uncalibrated_joint_error_m',
            'calibrated_joint_error_m', 'final_error_m']:
    values = [r[key] for r in valid]
    summary[key] = dict(median=float(np.median(values)) if values else None,
        p90=float(np.percentile(values, 90)) if values else None,
        within1000m_of12=sum(v <= 1000 for v in values),
        within3000m_of12=sum(v <= 3000 for v in values))
result = dict(planned=12, accepted=len(valid), attempted_swaps=len(new),
    accepted_swaps=sum(r['valid'] for r in new.values()),
    improved_over_fixed_assignments=sum(r['final_error_m'] < r['calibrated_joint_error_m']
                                        for r in valid),
    median_swap_runtime_s=float(np.median([r['runtime_s'] for r in new.values()])),
    maximum_swap_runtime_s=max(r['runtime_s'] for r in new.values()),
    summary=summary, rows=rows, source_sha256=sources,
    qualification='One objective-selected swap in9scans, unchanged parent in3with no positive '
    'tested proposal. Same12development scans, no geographic selection. Quantiles conditional '
    'on acceptance, failures retained in denominators. Warm timing excludes prior fitting, '
    'proposal audit, cold acquisition and preprocessing. No heldout or uncertainty claim.')
verify_sources(sources)
path = HERE/'calibrated-swap-panel-v1.json'
with path.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
path.with_suffix('.sha256').write_text(digest(path)+'\n')
print(json.dumps({k: v for k, v in result.items() if k not in ['rows', 'source_sha256']}, indent=2))
