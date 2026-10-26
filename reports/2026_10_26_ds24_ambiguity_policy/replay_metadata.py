"""Bounded read-only metadata authority for one original detector replay."""
import hashlib
import json
from pathlib import Path

MANIFEST = Path('/srv/bulk/leo/research/ds24-20261024-extension/manifest.json')


def read(path, limit=64 * 1024**2):
    path = Path(path)
    size = path.stat().st_size
    assert size < limit, (path, size)
    data = path.read_bytes()
    return data, {'path': str(path), 'bytes': size,
                  'sha256': 'sha256:' + hashlib.sha256(data).hexdigest()}


def shape(value):
    if isinstance(value, dict):
        return {'keys': sorted(value)}
    if isinstance(value, list):
        return {'length': len(value), 'first_shape': shape(value[0]) if value else None}
    return value


def main():
    # The sealed all-recording manifest is 119,545,966 bytes; inputs below
    # retain the smaller bound. This is metadata, not an IQ payload read.
    b, authority = read(MANIFEST, 128 * 1024**2)
    member = next(x for x in json.loads(b)['members'] if x['dataset_label'] == 'DS24-0011')
    sources = []
    for entry in member['source_inputs']:
        raw, record = read(entry['path'])
        assert record['sha256'] == entry['sha256']
        doc = json.loads(raw)
        record['top_level'] = {k: shape(v) for k, v in doc.items()}
        record['first_records'] = {
            k: v[0] for k, v in doc.items()
            if isinstance(v, list) and v and isinstance(v[0], dict)
        }
        # Restrict this output to the first record of each top-level list.
        sources.append(record)
    chunk = member['raw_recording']['chunks'][0]
    raw, index_record = read(chunk['index_path'], 1024**2)
    assert index_record['sha256'] == chunk['index_sha256']
    first_index = json.loads(raw.splitlines()[0])
    raw, segment_record = read(chunk['segment_manifest'], 1024**2)
    segment = json.loads(raw)
    result = {'dataset': authority, 'case': 'DS24-0011', 'sources': sources,
              'index': index_record, 'first_index': first_index,
              'segment': segment_record, 'segment_document': segment,
              'IQ_read': False, 'detector_run': False}
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
