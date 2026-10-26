"""Read-only, metadata-sized check of one existing 10 MS/s recording chunk."""
import hashlib
import json
from pathlib import Path
import time

DATASET = Path('/srv/bulk/leo/research/ds24-20261024-extension/manifest.json')
CASE = 'DS24-0011'


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def main():
    started = time.monotonic()
    payload = DATASET.read_bytes()
    member = next(row for row in json.loads(payload)['members']
                  if row['dataset_label'] == CASE)
    assert member['sample_rate_hz'] == 10_000_000
    chunk = member['raw_recording']['chunks'][0]
    paths = {key: Path(chunk[key]) for key in
             ('segment_manifest', 'index_path', 'payload_path')}
    stats = {key: dict(path=str(path), bytes=path.stat().st_size)
             for key, path in paths.items()}
    # Never read/decompress the IQ payload for this availability decision.
    assert stats['payload_path']['bytes'] == chunk['compressed_bytes']
    assert stats['segment_manifest']['bytes'] < 1024**2
    assert stats['index_path']['bytes'] == chunk['index_bytes'] < 1024**2
    manifest_bytes = paths['segment_manifest'].read_bytes()
    index_bytes = paths['index_path'].read_bytes()
    pinned = next(row for row in member['raw_recording']['segments']
                  if row['path'] == str(paths['segment_manifest']))
    assert digest(manifest_bytes) == pinned['sha256']
    assert digest(index_bytes) == chunk['index_sha256']
    manifest = json.loads(manifest_bytes)
    index = [json.loads(line) for line in index_bytes.splitlines()]
    assert len(index) == chunk['window_count']
    first = index[0]
    # Keep extraction deliberately small, with no whole-recording probe dump.
    small = {k: v for k, v in first.items()
             if isinstance(v, (str, int, float, bool)) or v is None}
    result = dict(case=CASE, dataset_manifest_sha256=digest(payload),
                  dataset_manifest_path=str(DATASET), sample_rate_hz=member['sample_rate_hz'],
                  recording_id=member['recording_id'], paths=stats,
                  manifest_sha256=digest(manifest_bytes), index_sha256=digest(index_bytes),
                  manifest_keys=sorted(manifest), index_keys=sorted(first),
                  first_index_scalars=small, first_index_nested_keys={
                      k: sorted(v) for k, v in first.items() if isinstance(v, dict)},
                  first_window_power_summaries=first['powers'],
                  chunk_window_count=len(index),
                  chunk_uncompressed_bytes=chunk['uncompressed_bytes'],
                  payload_hash_verified=False, payload_read_or_decompressed=False,
                  detector_executed=False, GPS_read=False, seconds=time.monotonic()-started)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
