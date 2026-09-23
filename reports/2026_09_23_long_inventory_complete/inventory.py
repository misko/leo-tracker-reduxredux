"""Complete the frozen older metadata inventory without reading analysis evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

from leo.storage.adaptive_hop import AdaptiveHopIqStore

OUT = Path(__file__).resolve().parent


def main():
    original = OUT.parent / '2026_09_23_long_group_metadata/inventory.py'
    spec = importlib.util.spec_from_file_location('original_inventory', original)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    blocked = module.excluded()
    store = AdaptiveHopIqStore(Path('/srv/bulk/leo'), read_only=True)
    try:
        ids = sorted({sid for stamp, sid in store.publication_index()
                      if int(module.START.timestamp() * 1e9) <= stamp
                      < int(module.END.timestamp() * 1e9) and sid not in blocked})
    finally:
        store.close()

    def one(sid):
        try:
            with urlopen(
                f'http://127.0.0.1:8090/api/v3/scanner/adaptive-sessions/{sid}', timeout=5
            ) as response:
                capture = json.load(response)['capture']
            start = datetime.fromisoformat(capture['captured_at']).astimezone(UTC)
            duration = capture.get('nominal_duration_seconds')
            if not module.START <= start < module.END:
                return {'session_id': sid, 'state': 'outside_capture_window'}
            group = start.replace(hour=start.hour // 8 * 8, minute=0, second=0, microsecond=0)
            valid_duration = isinstance(duration, (int, float)) and duration > 0
            contained = valid_duration and start + timedelta(seconds=duration) <= min(
                group + timedelta(hours=8), module.END
            )
            return {'session_id': sid, 'captured_at': start.isoformat(),
                    'sample_rate_hz': capture['sample_rate_hz'], 'nominal_duration_s': duration,
                    'utc_8h_start': group.isoformat(), 'contained_nominal_interval': contained,
                    'state': 'eligible_metadata' if contained else 'invalid_or_crossing_interval'}
        except Exception as exc:
            return {'session_id': sid, 'state': 'unavailable', 'reason': type(exc).__name__}

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one, ids))
    groups = {}
    for row in rows:
        if row['state'] == 'eligible_metadata':
            groups.setdefault(row['utc_8h_start'], []).append(row)
    result = {
        'metadata_only': True, 'position_or_track_outcomes_opened': False,
        'worker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'source_worker_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
        'window_start': module.START.isoformat(), 'window_end_exclusive': module.END.isoformat(),
        'excluded_ids': sorted(blocked), 'publication_candidate_ids': ids,
        'scans': rows, 'utc_8h_groups': [
            {'utc_8h_start': key, 'scan_count': len(value),
             'nominal_capture_seconds': sum(row['nominal_duration_s'] for row in value),
             'session_ids': [
                 row['session_id'] for row in sorted(value, key=lambda r: r['captured_at'])
             ]}
            for key, value in sorted(groups.items())],
    }
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
