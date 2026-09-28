"""Read-only metadata inventory; never reads IQ or starts analysis/acquisition."""
import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


def digest(b):
    return 'sha256:' + hashlib.sha256(b).hexdigest()


def canonical(d):
    return json.dumps(d, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def utc(ns):
    return datetime.fromtimestamp(ns / 1e9, timezone.utc).isoformat()


def get_status(sid):
    result = {}
    for name, route in [('glrt', f'/api/v2/scanner/adaptive-sessions/{sid}/analysis'),
                        ('tracking', f'/api/v1/scanner/tracking/{sid}')]:
        try:
            with urlopen('http://127.0.0.1:8090' + route, timeout=30) as response:
                d = json.load(response)
            result[name] = {k: d[k] for k in ('state', 'session_id', 'input_manifest_sha256',
                'binding_sha256', 'metrics_manifest_sha256', 'total_visits', 'checkpoint_visits') if k in d}
            if name == 'glrt':
                result[name]['configuration'] = d.get('configuration')
            product = d.get('product') or {}
            if product:
                result[name]['product_provenance'] = {k: product[k] for k in (
                    'schema_version', 'analysis_id', 'input_manifest_sha256',
                    'analysis_manifest_sha256', 'configuration_digest', 'created_at',
                    'trajectory_state', 'tle_state', 'attempted_group_count',
                    'deferred_group_count', 'group_limit') if k in product}
        except Exception as e:
            result[name] = {'state': 'unavailable', 'error': str(e)}
    result['observed_at_utc'] = utc(time.time_ns())
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ds6', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    cutoff = time.time_ns()
    prior_bytes = args.ds6.read_bytes()
    prior = json.loads(prior_bytes)
    lower = max(c['capture_end_utc_ns'] for c in prior['captures'])
    prior_ids = {c['session_id'] for c in prior['captures']}
    store = AdaptiveHopIqStore(Path('/srv/bulk/leo'), read_only=True)
    rows = []
    try:
        index = store.tracking_metadata_index()
        candidates = [(created, captured, radio, sid) for created, captured, radio, sid in index
                      if lower < captured <= cutoff and sid not in prior_ids]
        for _, _, _, sid in sorted(candidates, key=lambda c: (c[1], c[3])):
            row = {'session_id': sid, 'exclusion_reasons': []}
            try:
                session = store.inspect(sid)
                m = session.manifest
                r = m.receipt
                t = m.timing
                row.update(manifest_sha256=session.manifest_sha256,
                    finalized_utc_ns=m.finalized_utc_ns,
                    radio_id=r.radio_id, radio_serial=r.radio_serial,
                    receiver_ids=list(r.plan.geometry.receiver_ids),
                    sample_rate_hz=r.plan.geometry.sample_rate_hz,
                    bandwidth_hz=r.plan.geometry.bandwidth_hz,
                    visits=r.complete_visit_count, events=len(r.events),
                    chunks=len(m.chunks), compressed_bytes=m.compressed_bytes,
                    uncompressed_bytes=m.uncompressed_bytes, total_sample_count=m.total_sample_count,
                    uncompressed_sha256=m.uncompressed_sha256,
                    source_span_attested=r.source_span_attested,
                    terminal_state=r.terminal.state, terminal_error_code=r.terminal.error_code,
                    device_dropped_events=r.terminal.device_dropped_events,
                    transport_missing_sample_count=r.transport_missing_sample_count,
                    unreceived_tail_sample_count=r.unreceived_tail_sample_count,
                    unclassified_sample_count=r.unclassified_sample_count,
                    valid_sample_count=r.valid_sample_count,
                    transition_invalid_sample_count=r.transition_invalid_sample_count,
                    duty_denominator_sample_count=r.duty_denominator_sample_count,
                    valid_duty_ppm=r.valid_duty_ppm, duty_target_met=r.duty_target_met,
                    retained_visit_count=len(r.retained_visit_indices),
                    restoration_status=r.restoration.status,
                    metadata_abi_version=r.metadata_abi_version,
                    chunk_inventory_sha256=digest(canonical([c.model_dump(mode='json') for c in m.chunks])))
                if t:
                    row.update(capture_start_utc_ns=t.first_sample_estimate_utc_ns,
                        capture_start_earliest_utc_ns=t.first_sample_earliest_utc_ns,
                        capture_start_latest_utc_ns=t.first_sample_latest_utc_ns,
                        capture_end_utc_ns=t.terminal_realtime_ns,
                        capture_start_utc=utc(t.first_sample_estimate_utc_ns),
                        capture_end_utc=utc(t.terminal_realtime_ns), utc_qualified=t.qualified,
                        utc_bracket_width_ns=t.first_sample_bracket_width_ns)
                checks = {
                    'not_finalized_at_cutoff': m.finalized_utc_ns > cutoff,
                    'not_completed': r.terminal.state != 'completed' or r.terminal.error_code != 0,
                    'source_span_unattested': not r.source_span_attested,
                    'utc_unqualified_or_overlapping_ds6': not t or not t.qualified or t.first_sample_earliest_utc_ns <= lower,
                    'missing_samples_or_events': any((r.transport_missing_sample_count,
                        r.unreceived_tail_sample_count, r.unclassified_sample_count, r.terminal.device_dropped_events)),
                    'incomplete_visits': r.complete_visit_count != len(r.events) or len(r.retained_visit_indices) != len(r.events),
                    'restoration_incomplete': r.restoration.status != 'restored',
                    'empty_recording': not m.chunks or not m.total_sample_count,
                }
                row['exclusion_reasons'].extend(k for k, failed in checks.items() if failed)
                pose_path = Path('/srv/bulk/leo/capture-pose/gauss-r20-roof-20260926-v1') / (sid + '.json')
                try:
                    b = pose_path.read_bytes()
                    pose = json.loads(b)
                    assert pose['session_id'] == sid and pose['manifest_sha256'] == session.manifest_sha256
                    assert pose['binding_digest'] == digest(canonical({k: v for k,v in pose.items() if k != 'binding_digest'}))
                    assert pose['pose_authority_digest'] == digest(canonical(pose['pose_authority']))
                    assert pose['capture_start_earliest_utc_ns'] == t.first_sample_earliest_utc_ns
                    assert pose['capture_end_utc_ns'] == t.terminal_realtime_ns
                    authority = pose['pose_authority']
                    assert authority['valid_from_utc_ns'] <= t.first_sample_earliest_utc_ns < t.terminal_realtime_ns < authority['valid_until_utc_ns']
                    row.update(pose_status='verified', pose_file_sha256=digest(b),
                        pose_binding_digest=pose['binding_digest'], pose_authority_digest=pose['pose_authority_digest'],
                        pose_authority_revision=authority['revision'])
                except Exception as e:
                    row.update(pose_status='unavailable_or_invalid', pose_error=str(e))
            except Exception as e:
                row['exclusion_reasons'].append('manifest_inspection_failed')
                row['inspection_error'] = str(e)
            row['recording_complete'] = not row['exclusion_reasons']
            rows.append(row)
            if len(rows) % 20 == 0:
                print(f'Inspected {len(rows)}/{len(candidates)} published recordings', flush=True)
    finally:
        store.close()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row, status in zip(rows, pool.map(get_status, [r['session_id'] for r in rows])):
            row['analysis_readiness'] = status
    document = {'status': 'proposal_not_minted', 'proposed_dataset_id': 'DS7',
        'inventory_cutoff_utc_ns': cutoff, 'inventory_cutoff_utc': utc(cutoff),
        'inventory_finished_utc': utc(time.time_ns()), 'ds6_manifest_sha256': digest(prior_bytes),
        'after_ds6_capture_end_utc_ns': lower, 'after_ds6_capture_end_utc': utc(lower),
        'scope': 'All published adaptive-hop recordings after DS6, across radios in the store metadata index',
        'integrity_scope': 'Validated sealed manifests and chunk accounting through read-only store; raw IQ not reread or rehashed',
        'analysis_membership_rule': 'not required; readiness recorded separately',
        'pose_membership_rule': 'not required for raw corpus; verified pose subset explicitly available',
        'duty_membership_rule': 'duty target is not completeness; retune-invalid intervals are retained as metadata',
        'captures': rows}
    args.output.write_text(json.dumps(document, indent=2) + '\n')
    print(json.dumps({'candidates': len(rows), 'complete': sum(r['recording_complete'] for r in rows),
                      'cutoff': document['inventory_cutoff_utc']}))


if __name__ == '__main__':
    main()
