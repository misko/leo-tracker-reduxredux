"""Public raw candidate to existing retained track membership, no identity truth."""
import hashlib
import inspect
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main(index):
    from tools.rx_paired_opportunities import export_input, projected_candidates
    from tools.ds7_export_baseline import partition
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig, reconstruct_persistent_hop_trajectories
    start = time.monotonic()
    pp = ROOT/'reports/2026_09_30_ds10_scale_weighting/plan.json'
    entry = json.loads(pp.read_text())['inputs'][index]
    artifact = next(a for a in entry['artifacts'] if a['kind']=='observations')
    assert digest(artifact['path']) == artifact['sha256'].removeprefix('sha256:')
    obs = json.loads(Path(artifact['path']).read_text())
    store = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        raw = store.load(entry['session_id'])
    finally:
        store.close()
    assert raw.qualified and raw.timing.qualified
    assert raw.input_manifest_sha256 == entry['manifest_sha256'] == obs['manifest_sha256']
    assert raw.analysis_manifest_sha256 == obs['analysis_manifest_sha256']
    projected = projected_candidates(raw)
    graph = reconstruct_persistent_hop_trajectories(list(projected.values()), config=PersistentHopTrajectoryConfig(minimum_span_s=3., minimum_support=6))
    tracks = {t.tracklet_id: t for t in graph.tracklets}
    selected = {t['track_id'] for t in obs['tracks']}
    assert selected <= tracks.keys()
    retained = {p.candidate_id for tid in selected for p in tracks[tid].points}
    opportunities, _ = export_input(raw, split='calibration' if index==16 else 'validation',
        cache_sha256='public-input:'+raw.input_manifest_sha256+':'+raw.analysis_manifest_sha256, projected=projected)
    rows = []; rejected = 0; duplicates = 0; seen = set()
    for op in opportunities:
        for rx in (0, 1):
            view = op['receivers'][f'rx{rx}']
            for candidate in view['candidates']:
                if not candidate['passed_fractional_margin_gate']:
                    rejected += 1
                    continue
                cid = candidate['projected_candidate_id']
                assert cid is not None
                if cid in seen:
                    duplicates += 1
                    continue
                seen.add(cid)
                visit = op['source_window']['visit_index']
                rows.append(dict(window=op['source_window_id'], visit=visit, rx=rx,
                    rf_hz=view['actual_rf_hz'], exact=candidate['fractional_exact_score'],
                    control=candidate['fractional_control_score'], retained=cid in retained,
                    training=partition(entry['session_id'], visit), candidate_id=cid))
    paths = [Path(__file__), HERE/'PROTOCOL.md', pp, Path(artifact['path'])]
    paths += [Path(inspect.getfile(f)) for f in (export_input, projected_candidates, partition,
        ScannerTrackingInputStore, reconstruct_persistent_hop_trajectories)]
    result = dict(index=index, session_id=entry['session_id'], rows=rows,
        rejected_raw_entries=rejected, duplicate_projected_entries=duplicates,
        retained_tracks=len(selected), input_manifest_sha256=raw.input_manifest_sha256,
        analysis_manifest_sha256=raw.analysis_manifest_sha256,
        sources={str(p):digest(p) for p in paths}, elapsed_s=time.monotonic()-start)
    with (HERE/f'donor-{index:02d}.json').open('x') as stream:
        json.dump(result, stream, allow_nan=False)
    print(json.dumps(dict(index=index, rows=len(rows), retained=sum(r['retained'] for r in rows), elapsed_s=result['elapsed_s'])))

if __name__=='__main__':
    main(int(sys.argv[1]))
