"""Audit raw cross-receiver epoch pairs; Doppler labels are inferred only."""
from collections import defaultdict
import hashlib
import inspect
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def delta_us(a, b, fs, frame_rate):
    period = fs / frame_rate
    difference = (b['integer_epoch_sample'] + b['fractional_epoch_offset_samples']
                  - a['integer_epoch_sample'] - a['fractional_epoch_offset_samples'])
    return ((difference + period / 2) % period - period / 2) / fs * 1e6


def label_pair(a, b):
    if len(a) != 1 or len(b) != 1:
        return 'unknown'
    return 'same' if a == b else 'different'


def main(index):
    from tools.rx_paired_opportunities import export_input, projected_candidates
    from tools.ds7_export_baseline import partition
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig, reconstruct_persistent_hop_trajectories
    from leo.application.persistent_hop_trajectory import FRAME_RATE_HZ
    from leo.application import persistent_hop_trajectory
    started = time.monotonic()
    donor_path = HERE.parent / 'acquisition_calibration' / f'donor-{index:02d}.json'
    donor = json.loads(donor_path.read_text())
    for path, sha in donor['sources'].items():
        assert digest(path) == sha, path
    store = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        raw = store.load(donor['session_id'])
    finally:
        store.close()
    assert raw.qualified and raw.timing.qualified
    plan = json.loads((ROOT / 'reports/2026_09_30_ds10_scale_weighting/plan.json').read_text())
    entry = plan['inputs'][index]
    assert entry['session_id'] == donor['session_id']
    assert entry['manifest_sha256'] == raw.input_manifest_sha256
    projected = projected_candidates(raw)
    graph = reconstruct_persistent_hop_trajectories(list(projected.values()), config=PersistentHopTrajectoryConfig(minimum_span_s=3., minimum_support=6))
    tracks = {t.tracklet_id: t for t in graph.tracklets}
    owners = defaultdict(set)
    for lane in donor['lanes']:
        for tid in lane['tracks']:
            for point in tracks[tid].points:
                owners[point.candidate_id].add((lane['norad'], lane['rf_hz']))
    opportunities, _ = export_input(raw, split=donor['role'], cache_sha256='public-input:' + raw.input_manifest_sha256 + ':' + raw.analysis_manifest_sha256, projected=projected)
    rows = []
    for opportunity in opportunities:
        receivers = opportunity['receivers']
        assert receivers['rx0']['actual_rf_hz'] == receivers['rx1']['actual_rf_hz']
        fs = opportunity['source_window']['sample_rate_hz']
        assert fs == donor['sample_rate_hz']
        for a in receivers['rx0']['candidates']:
            for b in receivers['rx1']['candidates']:
                if not (a['passed_fractional_margin_gate'] and b['passed_fractional_margin_gate']):
                    continue
                rows.append(dict(window_id=opportunity['source_window_id'], visit=opportunity['source_window']['visit_index'], training=partition(donor['session_id'], opportunity['source_window']['visit_index']), rf_hz=receivers['rx0']['actual_rf_hz'], label=label_pair(owners[a['projected_candidate_id']], owners[b['projected_candidate_id']]), delta_us=delta_us(a, b, fs, FRAME_RATE_HZ), candidate_ids=[a['projected_candidate_id'], b['projected_candidate_id']], exact=[c['fractional_exact_score'] for c in (a, b)], control=[c['fractional_control_score'] for c in (a, b)], cfo_hz=[c['fractional_tracking_cfo_hz'] for c in (a, b)]))
    paths = [Path(__file__), HERE / 'PROTOCOL.md', donor_path]
    paths += [Path(inspect.getfile(f)) for f in (export_input, projected_candidates, partition, ScannerTrackingInputStore, reconstruct_persistent_hop_trajectories, persistent_hop_trajectory)]
    result = dict(index=index, family=donor['family'], role=donor['role'], session_id=donor['session_id'], sample_rate_hz=donor['sample_rate_hz'], frame_rate_hz=FRAME_RATE_HZ, input_manifest_sha256=raw.input_manifest_sha256, analysis_manifest_sha256=raw.analysis_manifest_sha256, inferred_labels=True, rows=rows, sources={str(p): digest(p) for p in paths}, elapsed_s=time.monotonic()-started)
    with (HERE / f'epoch-pairs-{index:02d}.json').open('x') as stream:
        json.dump(result, stream, allow_nan=False)
    print(json.dumps(dict(index=index, pairs=len(rows), elapsed_s=result['elapsed_s'])), flush=True)


if __name__ == '__main__':
    main(int(sys.argv[1]))
