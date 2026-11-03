"""Fresh maintained-server projection and tracking for one complete detector replay."""
import argparse
import importlib.util
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scan', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root/'reports/2026_09_30_arm_fast_tracks/server-baseline/export_baseline.py'
    spec = importlib.util.spec_from_file_location('frozen_baseline_export', source)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    server = args.scan/'server'
    summary = json.loads((server/'summary.json').read_text())
    if summary['status'] != 'pass' or not summary['complete_capture'] or summary['visits'] != summary['expected_visits']:
        raise ValueError('complete fresh detector replay required')
    session = summary['dependencies']['session_id']
    capture = summary['dependencies']['recording_manifest_sha256']
    output = args.scan/'server-tracking'; output.mkdir()
    started = time.monotonic()
    store = m.AdaptiveHopIqStore(Path('/srv/bulk/leo'), read_only=True)
    try:
        published = store.inspect(session)
        if published.manifest_sha256 != capture:
            raise ValueError('capture changed')
        manifest = published.manifest; receipt = manifest.receipt
        analysis = m.canonical_digest({'algorithm_version':'fresh-standard-server-full-scan-analysis-v1',
            'recording_manifest_sha256':capture, 'server_task_digest':summary['task_digest'],
            'server_visits_jsonl_sha256':m.sha256(server/'server-visits.jsonl'),
            'server_harness_sha256':summary['dependencies']['harness_sha256']})
        source_input = m.TrackingInput(session_id=session, capture_mode='adaptive',
            sample_rate_hz=receipt.plan.geometry.sample_rate_hz, radio_id=receipt.radio_id,
            stream_generation=f'adaptive-iio-{receipt.stream_generation:016x}' if receipt.stream_generation else '',
            input_manifest_sha256=capture, analysis_manifest_sha256=analysis,
            raw_recording_authority_digest=m.canonical_digest({'capture':capture,'iq':manifest.uncompressed_sha256}),
            timing=manifest.timing, qualified=receipt.terminal.state == 'completed' and receipt.source_span_attested,
            probes=m.load_server(server, receipt.events, analysis), probe_ms=20,
            capture_start_utc_ns=manifest.timing.first_sample_estimate_utc_ns,
            capture_end_utc_ns=manifest.timing.first_sample_estimate_utc_ns+round(
                (receipt.terminal.final_counter-receipt.terminal.first_counter)*1e9/receipt.plan.geometry.sample_rate_hz))
        candidates = m.project_scanner_candidates(source_input)
    finally:
        store.close()
    if len(candidates) != summary['passing_candidates']:
        raise ValueError('projection lost passing candidates')
    m.write_observations(output,'server',candidates)
    projection_s = time.monotonic()-started
    print(json.dumps({'projected':len(candidates),'projection_s':projection_s}),flush=True)
    start = time.monotonic()
    config = m.PersistentHopTrajectoryConfig()
    tracks = m.reconstruct_persistent_hop_trajectories(candidates,config=config)
    tracking_s = time.monotonic()-start
    m.write_json(output/'server-tracks.json',tracks)
    m.write_tracks_tsv(output,tracks,{c.candidate_id:c for c in candidates})
    from leo.analysis import persistent_hop_trajectory
    result = {'status':'complete','session':session,'capture_digest':capture,
        'observations':len(candidates),'tracks':len(tracks.tracklets),
        'projection_s':projection_s,'tracking_s':tracking_s,'config':m.json_value(config),
        'source_sha256':{str(source):m.sha256(source),str(Path(__file__)):m.sha256(Path(__file__)),
            persistent_hop_trajectory.__file__:m.sha256(Path(persistent_hop_trajectory.__file__))},
        'scope':'Fresh maintained-server default tracker on fresh fractional GLRT; not the native tracker'}
    m.write_json(output/'receipt.json',result);print(json.dumps(result),flush=True)


if __name__ == '__main__':
    main()
