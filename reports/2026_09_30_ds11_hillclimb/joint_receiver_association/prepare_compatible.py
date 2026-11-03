"""Census compatible scans and reconstruct newly covered track memberships."""
from collections import defaultdict
import inspect
import json
from pathlib import Path
import time
from prepare import HERE, HILL, read, digest, alternatives, projected_candidates, export_input


def main():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig, reconstruct_persistent_hop_trajectories
    start = time.monotonic()
    planpath = HILL.parent / '2026_09_30_ds11_single10/plan.json'
    idpath = HILL / 'source_balance/catalogue_identities.json'
    plan, identities = read(planpath), read(idpath)
    frequencies = read(HERE / 'conditional-fit.json')['frequencies']
    sources = {str(p): digest(p) for p in (planpath, idpath, Path(__file__), HERE / 'COMPATIBLE_PROTOCOL.md', HERE / 'prepare.py', HERE / 'ownership.py', Path(inspect.getfile(project_scanner_candidates)), Path(inspect.getfile(reconstruct_persistent_hop_trajectories)))}
    eligible, excluded = [], []
    for index, entry in enumerate(plan['inputs']):
        p = next(a['path'] for a in entry['artifacts'] if a['kind'] == 'observations')
        obs = read(p)
        reasons = []
        if obs['sample_rate_hz'] != 5000000:
            reasons.append('sample_rate')
        if sorted({t['rf_hz'] for t in obs['tracks']}) != frequencies:
            reasons.append('exact_rf_set')
        row = dict(index=index, reasons=reasons, sample_rate_hz=obs['sample_rate_hz'], rf_hz=sorted({t['rf_hz'] for t in obs['tracks']}))
        (excluded if reasons else eligible).append(row)
        sources[p] = digest(p)
    assert [r['index'] for r in eligible] == [0, 4, 9, 16, 19, 20]
    store = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        for row in eligible:
            index = row['index']
            path = HERE / f'input-{index:02d}.json'
            if path.exists():
                row.update(path=str(path), sha256=digest(path), reused=True)
                continue
            entry = plan['inputs'][index]
            local = dict(sources)
            for a in entry['artifacts']:
                assert digest(a['path']) == a['sha256'].removeprefix('sha256:')
                local[a['path']] = digest(a['path'])
            obs = read(next(a['path'] for a in entry['artifacts'] if a['kind'] == 'observations'))
            raw = store.load(entry['session_id'])
            assert raw.qualified and raw.timing.qualified
            assert raw.input_manifest_sha256 == entry['manifest_sha256'] and raw.analysis_manifest_sha256 == obs['analysis_manifest_sha256']
            projected = project_scanner_candidates(raw)
            candidates = {c.candidate_id: c for c in projected}
            graph = reconstruct_persistent_hop_trajectories(projected, config=PersistentHopTrajectoryConfig(minimum_span_s=3., minimum_support=6))
            tracklets = {t.tracklet_id: t for t in graph.tracklets}
            opportunities, _ = export_input(raw, split='ds11-compatible', cache_sha256='public-input:' + raw.input_manifest_sha256 + ':' + raw.analysis_manifest_sha256, projected=projected_candidates(raw))
            window = {}
            for o in opportunities:
                for rx in ('rx0', 'rx1'):
                    for c in o['receivers'][rx]['candidates']:
                        cid = c['projected_candidate_id']
                        if cid is not None:
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
                tracks.append(dict(track_id=tid, receiver=t['receiver_id'], rf_hz=t['rf_hz'], candidate_ids=ids, window_ids=[window[c] for c in ids], training_mask=t['training_mask'], candidate_norad=identities['scans'][str(index)]['tracks'][tid]['candidate_norad']))
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
            with path.open('x') as f:
                json.dump(dict(index=index, session_id=entry['session_id'], tracks=tracks, lanes=lanes, opportunities=opportunities, sources=local, unidentified_candidate_count=len(set(window) - set(owners))), f, indent=2, allow_nan=False)
            row.update(path=str(path), sha256=digest(path), reused=False)
            print(json.dumps(dict(prepared=index, tracks=len(tracks))), flush=True)
    finally:
        store.close()
    with (HERE / 'compatible-inputs.json').open('x') as f:
        json.dump(dict(eligible=eligible, excluded=excluded, sources=sources, elapsed_s=time.monotonic() - start), f, indent=2)


if __name__ == '__main__':
    main()
