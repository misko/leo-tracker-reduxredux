"""Read and verify existing capture-bound operator pose; never infer a site."""
import hashlib
import json
import subprocess
from pathlib import Path

import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'2026_10_01_localization_goal'))
from regression_batch import digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def canonical_digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return 'sha256:'+hashlib.sha256(payload.encode()).hexdigest()


def validate(document, capture, authority, upper_boundary):
    content = {k: v for k, v in document.items() if k != 'binding_digest'}
    if canonical_digest(content) != document['binding_digest']:
        raise ValueError('binding digest mismatch')
    pose = document['pose_authority']
    if pose != authority or canonical_digest(pose) != document['pose_authority_digest']:
        raise ValueError('authority mismatch')
    for key in ['session_id', 'manifest_sha256', 'capture_start_earliest_utc_ns',
                'capture_end_utc_ns']:
        if document[key] != capture[key]:
            raise ValueError('capture binding mismatch: '+key)
    if capture['radio_id'] != pose['radio_id'] or capture['receiver_ids'] != [0, 1]:
        raise ValueError('radio or receiver mismatch')
    start, end = capture['capture_start_earliest_utc_ns'], capture['capture_end_utc_ns']
    if not (capture['utc_qualified'] and pose['valid_from_utc_ns'] <= start <= end
            < min(pose['valid_until_utc_ns'], upper_boundary)):
        raise ValueError('capture outside qualified authority interval')
    return [pose['latitude_deg'], pose['longitude_deg']]


def main():
    selection_path = HERE/'selection.json'
    assert digest(selection_path) == selection_path.with_suffix('.sha256').read_text().strip()
    selection = json.loads(selection_path.read_text())
    authority_path = ROOT/'deploy/station/gauss-r20-roof-20260926-v1.json'
    next_path = ROOT/'deploy/station/gauss-r20-lt3d-004b-20261001-v1.json'
    authority = json.loads(authority_path.read_text())
    boundary = json.loads(next_path.read_text())['valid_from_utc_ns']
    captures = {r['session_id']: r for r in selection['captures']}
    rows = []
    for unit in selection['captures']:
        session = unit['session_id']
        path = Path('/srv/bulk/leo/capture-pose')/authority['revision']/(session+'.json')
        payload = subprocess.run(['sudo', '-n', '-u', 'leo', 'cat', str(path)],
                                 check=True, capture_output=True).stdout
        document = json.loads(payload)
        capture = captures[session]
        assert unit['manifest_sha256'] == capture['manifest_sha256']
        reference = validate(document, capture, authority, boundary)
        rows.append(dict(unit=unit['unit_id'], reference_latlon=reference,
                         companion_path=str(path), companion=document,
                         companion_file_sha256='sha256:'+hashlib.sha256(payload).hexdigest()))
    result = dict(
        admitted=len(rows), selection_sha256=digest(selection_path),
        source_sha256={str(p): digest(p) for p in [Path(__file__), authority_path, next_path]},
        qualification='Existing immutable capture companions bind operator-reported coordinates '
        'to exact selected manifests and UTC intervals. Reference is unsurveyed; WGS84 assumed, '
        'survey uncertainty and actual altitude unknown. No new operator confirmation or physical '
        'movement detection implied. Use for qualified horizontal reference error only.', rows=rows)
    output = HERE/'reference-admission-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
