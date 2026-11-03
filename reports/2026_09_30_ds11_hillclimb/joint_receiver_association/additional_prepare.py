"""Public-port reconstruction for the separately frozen compatible record."""
from collections import defaultdict
import json
from pathlib import Path
from prepare import HERE, HILL, read, digest, alternatives, projected_candidates, export_input


def main():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig, reconstruct_persistent_hop_trajectories
    base = HILL / 'additional'
    plan = read(base / 'plan.json')
    identities = read(base / 'catalogue_identities.json')
    assert identities['plan_sha256'] == digest(base / 'plan.json')
    frequencies = read(HERE / 'conditional-fit.json')['frequencies']
    eligible, excluded = [], []
    for i, entry in enumerate(plan['inputs']):
        obs = read(next(a['path'] for a in entry['artifacts'] if a['kind'] == 'observations'))
        (eligible if obs['sample_rate_hz'] == 5000000 and sorted({t['rf_hz'] for t in obs['tracks']}) == frequencies else excluded).append(i)
    assert eligible == [1]
    entry = plan['inputs'][1]
    sources = {str(p): digest(p) for p in (base / 'plan.json', base / 'catalogue_identities.json', Path(__file__), HERE / 'ADDITIONAL_PROTOCOL.md', HERE / 'ownership.py', HERE / 'prepare.py')}
    for a in entry['artifacts']:
        assert digest(a['path']) == a['sha256'].removeprefix('sha256:')
        sources[a['path']] = digest(a['path'])
    obs = read(next(a['path'] for a in entry['artifacts'] if a['kind'] == 'observations'))
    store = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        raw = store.load(entry['session_id'])
    finally:
        store.close()
    assert raw.qualified and raw.timing.qualified
    assert raw.input_manifest_sha256 == entry['manifest_sha256'] and raw.analysis_manifest_sha256 == obs['analysis_manifest_sha256']
    projected = project_scanner_candidates(raw)
    candidates = {c.candidate_id: c for c in projected}
    graph = reconstruct_persistent_hop_trajectories(projected, config=PersistentHopTrajectoryConfig(minimum_span_s=3., minimum_support=6))
    tracklets = {t.tracklet_id: t for t in graph.tracklets}
    opportunities, _ = export_input(raw, split='ds11-additional-confirmation', cache_sha256='public-input:' + raw.input_manifest_sha256 + ':' + raw.analysis_manifest_sha256, projected=projected_candidates(raw))
    window = {}
    for o in opportunities:
        for rx in ('rx0', 'rx1'):
            for c in o['receivers'][rx]['candidates']:
                if c['projected_candidate_id'] is not None:
                    cid = c['projected_candidate_id']
                    assert cid not in window
                    window[cid] = o['source_window_id']
    tracks, owners = [], defaultdict(list)
    for t in obs['tracks']:
        tid = t['track_id']
        points = tracklets[tid].points
        assert len(points) == len(t['times_s'])
        ids = []
        for j, point in enumerate(points):
            c = candidates[point.candidate_id]
            assert abs((c.support_center_utc_ns - obs['start_utc_ns']) / 1e9 - t['times_s'][j]) < 1e-9
            assert abs(point.normalized_dealiased_cfo_hz - t['measured_hz'][j]) < 1e-7
            assert c.receiver_id == t['receiver_id'] and c.actual_rf_hz == t['rf_hz'] and c.visit_index == t['visits'][j]
            ids.append(c.candidate_id)
            owners[c.candidate_id].append(tid)
        tracks.append(dict(track_id=tid, receiver=t['receiver_id'], rf_hz=t['rf_hz'], candidate_ids=ids, window_ids=[window[c] for c in ids], training_mask=t['training_mask'], candidate_norad=identities['scans']['1']['tracks'][tid]['candidate_norad']))
    lanes = []
    for rf in frequencies:
        current = [t for t in tracks if t['rf_hz'] == rf]
        tids = {t['track_id'] for t in current}
        left = [t for t in current if t['receiver'] == 0]
        right = [t for t in current if t['receiver'] == 1]
        edges = []
        for a in left:
            for b in right:
                common = sorted(set(a['candidate_norad']) & set(b['candidate_norad']))
                aw = {w for w, m in zip(a['window_ids'], a['training_mask']) if m}
                bw = {w for w, m in zip(b['window_ids'], b['training_mask']) if m}
                if common and aw & bw:
                    edges.append(dict(left=a['track_id'], right=b['track_id'], candidate_norad=common, common_training_windows=len(aw & bw)))
        ambiguous = {cid: ts for cid, ts in owners.items() if len(ts) > 1 and set(ts) <= tids}
        lanes.append(dict(rf_hz=rf, left=[t['track_id'] for t in left], right=[t['track_id'] for t in right], edges=edges, ambiguous_owners=ambiguous, ownership_alternatives=[dict(assignment=a, log_prior=w) for a, w in alternatives(ambiguous)]))
    with (HERE / 'additional-input-01.json').open('x') as f:
        json.dump(dict(index=1, session_id=entry['session_id'], tracks=tracks, lanes=lanes, opportunities=opportunities, sources=sources, eligible=eligible, excluded=excluded), f, indent=2, allow_nan=False)
    print(json.dumps(dict(index=1, tracks=len(tracks), excluded=excluded)), flush=True)


if __name__ == '__main__':
    main()
