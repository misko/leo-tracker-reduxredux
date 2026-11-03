"""Audit frozen track timestamp conversion; no fitting or GPS reads."""
import json
from pathlib import Path

import numpy as np

from regression_batch import digest

HERE = Path(__file__).resolve().parent
BASE = HERE.parent/'2026_09_30_gaussian_sum_64_scan'
selection_path = BASE/'selection.json'
selection = json.loads(selection_path.read_text())
inputs = {str(selection_path): digest(selection_path)}
rows = []
for selected in selection['selected'].values():
    for selected_row in selected:
        unit = selected_row['unit_id']
        evidence_path = BASE/'evidence'/f'{unit}.json'
        evidence = json.loads(evidence_path.read_text())
        source_path = Path(evidence['source']['path'])
        assert digest(source_path) == evidence['source']['sha256']
        source = json.loads(source_path.read_text())
        assert source['session_id'] == evidence['session_id'] == selected_row['session_id']
        assert source['manifest_sha256'] == evidence['manifest_sha256'] == selected_row['manifest_sha256']
        parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
        assert digest(parent_path) == json.loads(parent_path.with_suffix('.seal.json').read_text())['prediction_sha256']
        parent = json.loads(parent_path.read_text())
        assert parent['inputs'][str(evidence_path)] == digest(evidence_path)
        assert parent['inputs'][str(source_path)] == digest(source_path)
        inputs.update({str(p): digest(p) for p in [evidence_path, source_path, parent_path]})
        originals = {t['track_id']: t for t in source['tracks']}
        assert len(originals) == len(source['tracks'])
        maximum = 0.
        count = 0
        for track in evidence['tracks']:
            original = originals[track['track_id']]
            absolute = np.asarray(track['times_utc_ns'], dtype=np.int64)
            relative = (absolute-source['start_utc_ns'])/1e9
            expected = np.asarray(original['times_s'])
            assert len(relative) == len(expected)
            assert np.all(np.diff(relative) >= 0)
            delta = float(np.max(abs(relative-expected)))
            maximum = max(maximum, delta)
            count += len(relative)
        rows.append(dict(unit=unit, tracks=len(evidence['tracks']), points=count,
                         maximum_roundtrip_error_ns=maximum*1e9,
                         export_minus_capture_start_ns=source['start_utc_ns']-selected_row['capture_start_utc_ns']))
result = dict(rows=rows, scans=len(rows), total_points=sum(r['points'] for r in rows),
    maximum_roundtrip_error_ns=max(r['maximum_roundtrip_error_ns'] for r in rows),
    source_sha256={str(Path(__file__)): digest(__file__)}, inputs=inputs,
    qualification='Checks frozen exported relative times versus integer UTC evidence consumed by '
    'the estimator, and capture-start metadata. Not raw timing calibration or independent hardware '
    'UTC verification. Covers all exported evidence tracks, including tracks later excluded.')
output = HERE/'timestamp-roundtrip-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps({k: v for k, v in result.items() if k not in ['inputs', 'source_sha256']}, indent=2))
