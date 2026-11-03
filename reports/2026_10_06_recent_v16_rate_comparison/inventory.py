"""Metadata-only recent cohort selection through public read-only capture ports.

Run with the archived analysis-release interpreter. No RF or production writes.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RATES = (2_500_000, 10_000_000)


def select(rows, start_ns, end_ns, count=8):
    """Nearest unused capture to each equally spaced time target; no fit scores."""
    chosen = []
    pool = sorted(rows, key=lambda row: (row['capture_start_ns'], row['session_id']))
    for index in range(min(count, len(pool))):
        target = start_ns + (index + .5) * (end_ns - start_ns) / count
        row = min(pool, key=lambda row: (abs(row['capture_start_ns']-target), row['session_id']))
        pool.remove(row)
        chosen.append(dict(row))
    return sorted(chosen, key=lambda row: (row['capture_start_ns'], row['session_id']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--end', required=True)
    parser.add_argument('--hours', type=float, default=8)
    parser.add_argument('--bulk-root', type=Path, default=Path('/srv/bulk/leo'))
    parser.add_argument('--output', type=Path, default=HERE/'cohort.json')
    parser.add_argument('--metadata-cache', type=Path)
    args = parser.parse_args()
    end = datetime.fromisoformat(args.end)
    if end.tzinfo is None or args.hours <= 0:
        raise ValueError('Timezone-aware end and positive duration required')
    start = end - timedelta(hours=args.hours)
    start_ns, end_ns = round(start.timestamp()*1e9), round(end.timestamp()*1e9)
    sys.path.insert(0, str(ROOT/'tools'))
    from bind_adaptive_capture_pose import CapturePoseAuthority, bind
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
    from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
    from leo.storage.errors import BundleNotFoundError
    authority_path = ROOT/'deploy/station/gauss-r20-lt3d-004b-20261001-v1.json'
    authority = CapturePoseAuthority.model_validate_json(authority_path.read_bytes())
    iq = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    analysis = AdaptiveHopAnalysisStore(args.bulk_root, read_only=True)
    rows, errors = [], []
    cached = {}
    if args.metadata_cache:
        previous = json.loads(args.metadata_cache.read_text())
        if previous['start_utc'] != start.isoformat() or previous['end_utc'] != end.isoformat():
            raise ValueError('Cached metadata covers a different time interval')
        cached = {row['session_id']: row for row in previous['inventory']}
    try:
        for created, captured, radio, sid in sorted(iq.tracking_metadata_index()):
            if not start_ns <= captured <= end_ns:
                continue
            if sid in cached:
                row = dict(cached[sid])
                if 'edges' in row:
                    row['allowed_edges'] = row.pop('edges')
                    row['recorded_edges'] = None
                rows.append(row)
                continue
            try:
                published = iq.inspect(sid)
                manifest = published.manifest
                receipt = manifest.receipt
                geometry = receipt.plan.geometry
                timing = manifest.timing
                pose = bind(published, authority)
                rate = int(geometry.sample_rate_hz)
                binding = bind_actual_visit_analysis(receipt,
                    input_manifest_sha256=published.manifest_sha256, probe_stride_ms=120)
                try:
                    with analysis.job(binding) as job:
                        metrics = job.manifest()
                        analyzed_visits = len(metrics.visits) if metrics is not None else None
                except BundleNotFoundError:
                    metrics, analyzed_visits = None, None
                row = dict(session_id=sid, capture_start_ns=timing.first_sample_estimate_utc_ns,
                    capture_end_ns=timing.terminal_realtime_ns,
                    capture_utc=datetime.fromtimestamp(captured/1e9, timezone.utc).isoformat(),
                    sample_rate_hz=rate, manifest_sha256=published.manifest_sha256,
                    duration_s=(receipt.terminal.final_counter-receipt.terminal.first_counter)/rate,
                    complete=receipt.terminal.state == 'completed',
                    source_span_attested=receipt.source_span_attested,
                    timing_qualified=timing.qualified, pose_verified=pose is not None,
                    retained_visits=len(receipt.visits), analyzed_visits=analyzed_visits,
                    analysis_complete=metrics is not None,
                    channels=sorted({p.target.channel for p in geometry.profiles}),
                    allowed_edges=sorted({p.target.edge.value for p in geometry.profiles}),
                    recorded_edges=sorted({v.event.target.edge.value for v in receipt.visits}),
                    pose_binding=pose,
                    analysis_configuration=binding.configuration.model_dump(mode='json'))
                row['eligible'] = (rate in RATES and row['complete'] and row['source_span_attested']
                    and row['timing_qualified'] and row['pose_verified'] and row['duration_s'] >= 295)
                rows.append(row)
                print(json.dumps({k:v for k,v in row.items() if k not in {'pose_binding','analysis_configuration'}}), flush=True)
            except Exception as exc:
                errors.append(dict(session_id=sid, error=f'{type(exc).__name__}: {exc}'))
                print(json.dumps(errors[-1]), flush=True)
    finally:
        analysis.close()
        iq.close()
    chosen, counts = [], {}
    for rate in RATES:
        eligible = [r for r in rows if r['sample_rate_hz']==rate and r['eligible']]
        additions = select(eligible, start_ns, end_ns)
        for index, row in enumerate(additions, 1):
            row.update(label=f"R{'025' if rate==2_500_000 else '100'}-{index:02}",
                       split='prospective_fixed_v16')
        chosen.extend(additions)
        counts[str(rate)] = dict(eligible=len(eligible), selected=len(additions),
            analysis_ready=sum(r['analysis_complete'] for r in additions), shortfall=8-len(additions))
    result = dict(schema='recent-v16-rate-comparison/v1', start_utc=start.isoformat(), end_utc=end.isoformat(),
        selection='Eight equally spaced time targets per rate; nearest unused completed capture with verified pose. No signal/fit score used. No substitution outside the fixed time window.',
        model='V16 frozen; independent 4 km position search; matched fitted-c and zero-c arms',
        authority_sha256=hashlib.sha256(authority_path.read_bytes()).hexdigest(),
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        metadata_cache=str(args.metadata_cache) if args.metadata_cache else None,
        inventory=rows, errors=errors, counts=counts, scans=chosen,
        rate_inventory=dict(Counter(str(r['sample_rate_hz']) for r in rows)),
        status='metadata_frozen; input analysis and IQ readiness checked separately')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print('SUMMARY', json.dumps(dict(counts=counts, errors=len(errors), output=str(args.output))), flush=True)


if __name__ == '__main__':
    main()
