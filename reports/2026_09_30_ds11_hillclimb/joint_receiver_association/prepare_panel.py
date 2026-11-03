"""Prepare remaining fixed panel using the existing public observation join."""
from collections import defaultdict
import json
from pathlib import Path
import time
from prepare import HERE, HILL, ROOT, read, digest, alternatives, projected_candidates, export_input


def main():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    start = time.monotonic()
    planpath = HILL.parent / '2026_09_30_ds11_single10/plan.json'
    sidepath = HILL / 'source_consistency/source_groups.json'
    idpath = HILL / 'source_balance/catalogue_identities.json'
    plan, side, identities = map(read, (planpath, sidepath, idpath))
    assert side['plan_sha256'] == digest(planpath)
    source_paths = [planpath, sidepath, idpath, Path(__file__), HERE / 'prepare.py', HERE / 'ownership.py', ROOT / 'tools/rx_paired_opportunities.py', HERE / 'PANEL_PROTOCOL.md']
    sources = {str(p): digest(p) for p in source_paths}
    scans = []
    store = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        for index in (4, 8, 12, 20, 24, 28):
            entry = plan['inputs'][index]
            local_sources = dict(sources)
            for a in entry['artifacts']:
                assert digest(a['path']) == a['sha256'].removeprefix('sha256:')
                local_sources[a['path']] = digest(a['path'])
            obs = read(next(a['path'] for a in entry['artifacts'] if a['kind'] == 'observations'))
            assert obs['sample_rate_hz'] == 5000000
            assert sorted({t['rf_hz'] for t in obs['tracks']}) == read(HERE / 'conditional-fit.json')['frequencies']
            raw = store.load(entry['session_id'])
            assert raw.input_manifest_sha256 == entry['manifest_sha256'] and raw.analysis_manifest_sha256 == obs['analysis_manifest_sha256']
            assert raw.qualified and raw.timing.qualified
            opportunities, _ = export_input(raw, split='ds11-panel', cache_sha256='public-input:' + raw.input_manifest_sha256 + ':' + raw.analysis_manifest_sha256, projected=projected_candidates(raw))
            candidates = {}
            windows = {o['source_window_id']: o for o in opportunities}
            for o in opportunities:
                for rx in ('rx0', 'rx1'):
                    for c in o['receivers'][rx]['candidates']:
                        cid = c['projected_candidate_id']
                        if cid is not None:
                            assert cid not in candidates
                            candidates[cid] = (o['source_window_id'], int(rx[-1]), o['receivers'][rx]['actual_rf_hz'])
            tracks, owners = [], defaultdict(list)
            for t in obs['tracks']:
                tid = t['track_id']
                points = side['scans'][str(index)]['tracks'][tid]
                assert len(points) == len(t['times_s'])
                ids, wins = [], []
                for j, point in enumerate(points):
                    cid = point['candidate_id']
                    win, rx, rf = candidates[cid]
                    assert rx == t['receiver_id'] and rf == t['rf_hz']
                    assert windows[win]['source_window']['visit_index'] == t['visits'][j] and point['training'] == t['training_mask'][j]
                    ids.append(cid)
                    wins.append(win)
                    owners[cid].append(tid)
                tracks.append(dict(track_id=tid, receiver=t['receiver_id'], rf_hz=t['rf_hz'], candidate_ids=ids, window_ids=wins, training_mask=t['training_mask'], candidate_norad=identities['scans'][str(index)]['tracks'][tid]['candidate_norad']))
            lanes = []
            for rf in sorted({t['rf_hz'] for t in tracks}):
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
            path = HERE / f'input-{index:02d}.json'
            with path.open('x') as f:
                json.dump(dict(index=index, session_id=entry['session_id'], tracks=tracks, lanes=lanes, opportunities=opportunities, sources=local_sources, unidentified_candidate_count=len(set(candidates) - set(owners))), f, indent=2, allow_nan=False)
            scans.append(dict(index=index, path=str(path), sha256=digest(path)))
            print(json.dumps(dict(prepared=index, tracks=len(tracks))), flush=True)
    finally:
        store.close()
    with (HERE / 'panel-inputs.json').open('x') as f:
        json.dump(dict(scans=scans, sources=sources, elapsed_s=time.monotonic() - start), f, indent=2)


if __name__ == '__main__':
    main()
