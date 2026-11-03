"""Freeze 64 additional recorded scans using metadata, never fit quality."""
import argparse
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent / '2026_10_04_ds13_18_scan_benchmark'
sys.path.insert(0, str(BENCH))
from cohort import verify_capture, digest


def select(existing, eligible, count=64):
    """Deterministic farthest-time additions; retain the original 18 unchanged."""
    ids = {r['session_id'] for r in existing}
    pool = [copy.deepcopy(r) for r in eligible if r['session_id'] not in ids]
    if len({r['session_id'] for r in pool}) != len(pool):
        raise ValueError('duplicate eligible sessions')
    if not existing or len(pool) < count or count < 1:
        raise ValueError('insufficient metadata candidates')
    selected = []
    for rank in range(count):
        row = max(pool, key=lambda r: (
            min(abs(r['capture_start_ns'] - p['capture_start_ns']) for p in existing + selected),
            r['session_id']))
        pool.remove(row)
        row['selection_rank'] = rank + 1
        selected.append(row)
    selected.sort(key=lambda r: (r['capture_start_ns'], r['session_id']))
    for i, row in enumerate(selected, 17):
        row.update(label=f'N{i:02d}', split='sky_extension_full_data',
                   uncertainty_time_block=row['capture_start_ns'] // (3 * 3600 * 10**9))
    return selected


def build(source):
    raw = source.read_bytes()
    old = json.loads(raw)
    additions = select(old['scans'], old['eligible_new'])
    for row in additions:
        manifest = Path(row['manifest_path']).read_bytes()
        pose = Path(row['pose_path']).read_bytes()
        if digest(manifest) != row['manifest_file_sha256'] or digest(pose) != row['pose_file_sha256']:
            raise ValueError(f"changed metadata: {row['session_id']}")
        verified = verify_capture(json.loads(manifest), json.loads(pose), row['sample_rate_hz'])
        assert verified['manifest_sha256'] == row['manifest_sha256']
        assert verified['sample_rate_hz'] == 2_500_000
    scans = copy.deepcopy(old['scans']) + additions
    chronological = sorted(scans, key=lambda r: r['capture_start_ns'])
    gaps = [(b['capture_start_ns'] - a['capture_end_ns']) / 6e10 for a, b in zip(chronological, chronological[1:])]
    return dict(schema='receiver-sky-extension/v1', source=str(source), source_sha256=digest(raw),
        implementation_sha256=digest(Path(__file__).read_bytes()), scans=scans,
        original_labels=[r['label'] for r in old['scans']], new_labels=[r['label'] for r in additions],
        original_count=len(old['scans']), additional_count=len(additions),
        status='metadata_verified_processing_pending',
        selection='Farthest-time greedy from the frozen 197-entry eligible metadata inventory, excluding the original 18. No signal score, coverage, residual, sky position, or localization result used.',
        spacing_caveat='The original one-per-three-hour policy cannot support 64 additions in this 62-hour inventory. Additional scans are not independent three-hour blocks; use whole three-hour-block resampling for uncertainty.',
        minimum_interval_gap_minutes=min(gaps),
        pipeline='Reuse orbit-blind refinement, timing-aware bootstrap, original five-fold calibration and absolute-timing T1-AT v1 greedy/replacement. Both c arms. All refined alternatives used for paired sky evidence. No position searches or new RF.',
        readiness='Capture/pose metadata reverified. Processing and full IQ availability require separate checks.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=BENCH/'cohort-v2.json')
    p.add_argument('--output', type=Path, default=HERE/'cohort.json')
    args = p.parse_args()
    result = build(args.source)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: result[k] for k in ('original_count', 'additional_count', 'minimum_interval_gap_minutes', 'status')}))
