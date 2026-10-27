"""Inspect immutable DS23 fast metadata rates, without IQ or fit outcomes."""
from pathlib import Path
from collections import Counter
import hashlib
import json

HERE = Path(__file__).resolve().parent


def main():
    path = HERE / 'original_path_inventory.json'
    inventory = json.loads(path.read_text())
    rows = []
    for record in inventory['rows']:
        segments = []
        for ref in record['raw_segments']:
            if ref['exists'] is not True:
                segments.append({'path': ref['path'], 'status': 'unavailable'})
                continue
            source = Path(ref['path'])
            data = source.read_bytes()
            doc = json.loads(data)
            digest = 'sha256:' + hashlib.sha256(data).hexdigest()
            segments.append({'path': str(source), 'sha256': digest,
                'matches_frozen_digest': digest == ref['manifest_sha256'],
                'sample_rate_hz': doc.get('sample_rate_hz'),
                'window_ms': doc.get('window_ms'),
                'sample_format': doc.get('sample_format'),
                'sample_layout': doc.get('sample_layout'),
                'schema_version': doc.get('schema_version'),
                'status': doc.get('status'),
                'policy_id': doc.get('configuration', {}).get('policy_id')})
        rows.append({'case': record['dataset_label'],
            'all_original_paths_present': record['all_original_paths_present'],
            'rates_hz': sorted({s['sample_rate_hz'] for s in segments if s.get('sample_rate_hz') is not None}),
            'segment_hash_mismatches': sum(not s['matches_frozen_digest'] for s in segments if 'matches_frozen_digest' in s),
            'segments': segments})
    result = {'source_inventory_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'fast_recordings': len(rows),
        'recording_rate_patterns': dict(Counter(str(r['rates_hz']) for r in rows)),
        'segment_hash_mismatches': sum(r['segment_hash_mismatches'] for r in rows),
        'IQ_opened': False, 'geographic_errors_opened': False, 'rows': rows}
    with (HERE / 'sample_rate_inventory.json').open('x') as handle:
        json.dump(result, handle, indent=2);handle.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}, indent=2))


if __name__ == '__main__':
    main()
