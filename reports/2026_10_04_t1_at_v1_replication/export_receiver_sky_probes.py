"""Read-only scheduled-probe export through the installed tracking contract."""
import argparse
import hashlib
import inspect
import json
from pathlib import Path


def run(scan, cohort_path=None):
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    here = Path(__file__).resolve().parent
    source = cohort_path or here.parent / '2026_10_04_ds13_18_scan_benchmark/cohort-v2.json'
    meta = next(r for r in json.loads(source.read_text())['scans'] if r['label'] == scan)
    store = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        data = store.load(meta['session_id'])
    finally:
        store.close()
    assert data.input_manifest_sha256 == meta['manifest_sha256'] and data.probe_ms == 20
    # valid_start_counter is a device counter, so subtract the capture counter.
    first = data.timing.session_start_device_sample_counter
    probes = []
    for p in data.probes:
        counter = p.valid_start_counter + round(p.probe_start_ms * data.sample_rate_hz / 1000)
        probes.append(dict(key=[p.visit_index, p.receiver_id, p.probe_index],
            channel=p.channel, edge=p.edge, rf_hz=p.actual_rf_hz, start_counter=counter,
            center_s=(counter-first)/data.sample_rate_hz + .010,
            candidates=len(p.candidates), passing_candidates=sum(c.passed_fractional_margin_gate for c in p.candidates)))
    port = Path(inspect.getfile(ScannerTrackingInputStore))
    return dict(scan=scan, session_id=data.session_id, probe_ms=data.probe_ms,
        sample_rate_hz=data.sample_rate_hz, probes=probes,
        capture_sha256=data.input_manifest_sha256, analysis_sha256=data.analysis_manifest_sha256,
        port_path=str(port), port_sha256=hashlib.sha256(port.read_bytes()).hexdigest())


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('scan'); args=p.parse_args()
    print(json.dumps(run(args.scan), allow_nan=False))
