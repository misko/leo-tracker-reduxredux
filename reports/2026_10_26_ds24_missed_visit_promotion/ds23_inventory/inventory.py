"""Metadata-only original DS23 authority/path inventory; no outcome selection."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import os

HERE = Path(__file__).resolve().parent
MANIFEST = Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_18_ds23_post_ds22/manifest.json')


def status(path):
    try:
        st = os.stat(path)
        return {'exists': True, 'bytes': st.st_size}
    except FileNotFoundError:
        return {'exists': False, 'reason': 'not_found'}
    except OSError as exc:
        return {'exists': None, 'reason': type(exc).__name__, 'errno': exc.errno}


def main():
    original = json.loads(MANIFEST.read_text())
    rows = []
    for member in original['members']:
        if member['recording_format'] != 'short_window_iq_recording':
            continue
        raw = member['raw_recording']
        row = {key: member.get(key) for key in ('dataset_label', 'recording_id',
               'session_id', 'recording_format', 'captured_utc_ns', 'channels',
               'window_count', 'raw_authority_digest')}
        row['original_raw_root'] = {'path': raw['root'], **status(raw['root'])}
        for field, values in [('source_inputs', member.get('source_inputs', [])),
                              ('tracking_inputs', member.get('tracking_inputs', [])),
                              ('raw_segments', raw.get('segments', []))]:
            row[field] = [{'path': x['path'], 'manifest_sha256': x.get('sha256'),
                           **status(x['path'])} for x in values]
        row['all_original_paths_present'] = bool(row['source_inputs'] and
            row['tracking_inputs'] and row['raw_segments']) and all(
                x['exists'] is True for k in ('source_inputs', 'tracking_inputs', 'raw_segments')
                for x in row[k])
        rows.append(row)
    result = {'manifest_path': str(MANIFEST),
              'manifest_sha256': hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
              'format_counts': dict(Counter(x['recording_format'] for x in original['members'])),
              'fast_recordings': len(rows), 'all_original_paths_present': sum(x['all_original_paths_present'] for x in rows),
              'permission_failures': sum(x.get('exists') is None for r in rows for k in ('source_inputs', 'tracking_inputs', 'raw_segments') for x in r[k]),
              'original_path_inventory_only': True, 'IQ_payload_opened': False,
              'position_errors_opened': False, 'relocated_archive_search_performed': False,
              'rows': rows}
    output = HERE / 'original_path_inventory.json'
    with output.open('x') as handle:
        json.dump(result, handle, indent=2); handle.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
