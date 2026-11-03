"""Combine the fixed12development outcomes, keeping all failures."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from regression_batch import digest

HERE = Path(__file__).resolve().parent
rows, sources = [], {}
for name in ['balanced-group-v1', 'balanced-group-expansion-v1']:
    path = HERE/f'{name}-evaluation.json'
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    evidence = json.loads(path.read_text())
    assert evidence['freeze_sha256'] == digest(HERE/name/'sources.json')
    sources[str(path)] = digest(path)
    rows.extend(evidence['rows'])
selection = HERE/'split-expansion-fit-v1/sources.json'
assert digest(selection) == selection.with_suffix('.sha256').read_text().strip()
units = json.loads(selection.read_text())['units']
assert len(rows) == 24 and len(set((r['unit'], r['arm']) for r in rows)) == 24
assert set(r['unit'] for r in rows) == set(units)
summary = {}
for arm in ['control', 'balanced']:
    arm_rows = [r for r in rows if r['arm'] == arm]
    errors = [r['error_m'] for r in arm_rows if r['accepted']]
    summary[arm] = dict(planned=len(arm_rows), accepted=len(errors),
        median_error_m=float(np.median(errors)) if errors else None,
        p90_error_m=float(np.percentile(errors, 90)) if errors else None,
        within1000m=sum(e <= 1000 for e in errors), within3000m=sum(e <= 3000 for e in errors),
        median_warm_runtime_s=float(np.median([r['runtime_s'] for r in arm_rows])),
        maximum_warm_runtime_s=max(r['runtime_s'] for r in arm_rows),
        median_cpu_s=float(np.median([r['cpu_s'] for r in arm_rows if r['cpu_s'] is not None])))
pairs = []
for unit in units:
    old = next(r for r in rows if r['unit'] == unit and r['arm'] == 'control')
    new = next(r for r in rows if r['unit'] == unit and r['arm'] == 'balanced')
    pairs.append(dict(unit=unit, baseline_m=old['error_m'], balanced_m=new['error_m'],
                      accepted=new['accepted'], improved=bool(old['accepted'] and new['accepted']
                          and new['error_m'] < old['error_m'])))
result = dict(summary=summary, pairs=pairs, improved=sum(p['improved'] for p in pairs),
    source_sha256={**sources, str(Path(__file__)): digest(__file__)},
    qualification='Same12exposed development scans; pilot3plus9unchanged expansion. '
    'Warm fixed-identity fits exclude acquisition. Quantiles conditional on acceptance; '
    'threshold fractions retain all12. No cold64, heldout or uncertainty success.')
output = HERE/'balanced-group-panel-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
fig, ax = plt.subplots(figsize=(10, 5), layout='constrained')
x = np.arange(len(pairs))
ax.plot(x, [p['baseline_m'] for p in pairs], 'o', label='Original baseline')
ax.plot(x, [p['balanced_m'] for p in pairs], 's', label='Satellite-balanced score')
ax.axhline(1000, color='gray', ls=':', label='1,000 m')
ax.set_xticks(x, [p['unit'] for p in pairs], rotation=45, ha='right')
ax.set_ylabel('Horizontal error against operator reference (m)')
ax.set_title('Same12development scans: original versus satellite-balanced weighting')
ax.legend()
fig.savefig(HERE/'balanced-group-panel-v1.png', dpi=150)
print(json.dumps(result, indent=2))
