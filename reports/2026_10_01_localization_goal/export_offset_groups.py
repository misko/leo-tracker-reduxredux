"""Join sealed checking candidate residuals to training-only offset distributions."""
import json
from pathlib import Path

import numpy as np

from candidate_joint_expansion_adapter import CandidateJointObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
loaded, inputs, sources = [], {}, {str(Path(__file__)): digest(__file__)}
for name in ['candidate-calibration-inputs-v1.json', 'conditional-offset-audit-v1.json']:
    path = HERE/name
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    data = json.loads(path.read_text())
    verify_sources(data['source_sha256'])
    verify_sources(data['input_sha256'])
    sources.update(data['source_sha256'])
    inputs[str(path)] = digest(path)
    loaded.append(data)
candidates, offsets = loaded
offset_rows = {(r['unit'], r['track']): r for r in offsets['rows']}
rows = []
for scan in candidates['rows']:
    unit = scan['unit']
    samples = {s['source_group_id']: s for s in scan['samples']}
    model = CandidateJointObjective(unit)
    b = model.base
    slot_groups = {s: j for j, slots in enumerate(b.group_slots) for s in slots}
    active = [k for k, (p, i) in enumerate(zip(b.ports, b.assignments, strict=True)) if i < p.candidate_count]
    offset = 0
    for track, prepared in zip(active, model.prepared, strict=True):
        query, _, _, n, _, _, _ = prepared
        groups = []
        for slot in range(offset, offset+len(query.times)-n):
            group = b.groups[slot_groups[slot]]
            if group['id'] in samples:
                groups.append(samples[group['id']])
        offset += len(query.times)-n
        old = offset_rows[(unit, track)]
        assert len(groups) == old['checking_groups']
        if groups:
            assert abs(np.median([g['residual_hz'] for g in groups])-old['checking_median_residual_hz']) < 1e-6
            assert len({g['period_hz'] for g in groups}) == 1
        rows.append(dict(unit=unit, track=track, df=old['posterior_df'],
            offset_scale_hz=old['posterior_scale_hz'], groups=groups))
assert sum(len(r['groups']) for r in rows) == offsets['checking_groups'] == 7933
assert len(rows) == offsets['tracks'] == 526
verify_sources(sources)
output = HERE/'offset-candidate-groups-v1.json'
with output.open('x') as stream:
    json.dump(dict(rows=rows, source_sha256=sources, input_sha256=inputs), stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print('Joined 526 tracks and 7933 checking groups; seals and per-track counts/medians verified.')
