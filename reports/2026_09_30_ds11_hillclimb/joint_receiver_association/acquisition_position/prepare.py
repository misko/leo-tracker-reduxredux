"""Reconstruct public observation joins for the frozen acquisition pilot."""
from collections import defaultdict
import inspect
import json
import sys
import time
from common import HERE, PARENT, ROOT, JOBS, base, read, digest, bindings
from ownership import alternatives
from tools.rx_paired_opportunities import export_input, projected_candidates


def main(cohort, index):
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig, reconstruct_persistent_hop_trajectories
    started = time.monotonic()
    family = next(f for c, i, f in JOBS if (c, i) == (cohort, index))
    planpath = base(cohort) / 'plan.json'
    idpath = PARENT.parent / 'source_balance/catalogue_identities.json' if cohort == 'original' else base(cohort) / 'catalogue_identities.json'
    plan, identities = read(planpath), read(idpath)
    assert identities['plan_sha256'] == digest(planpath)
    entry = plan['inputs'][index]
    sources = bindings([planpath, idpath, HERE / 'PROTOCOL.md', HERE / 'common.py', HERE / 'prepare.py', PARENT / 'ownership.py', ROOT / 'tools/rx_paired_opportunities.py', inspect.getfile(ScannerTrackingInputStore), inspect.getfile(reconstruct_persistent_hop_trajectories)])
    for a in entry['artifacts']:
        assert digest(a['path']) == a['sha256'].removeprefix('sha256:')
        sources[a['path']] = digest(a['path'])
    obs = read(next(a['path'] for a in entry['artifacts'] if a['kind'] == 'observations'))
    store = ScannerTrackingInputStore(__import__('pathlib').Path('/srv/bulk/leo'))
    try:
        raw = store.load(entry['session_id'])
    finally:
        store.close()
    assert raw.qualified and raw.timing.qualified
    assert raw.input_manifest_sha256 == entry['manifest_sha256'] and raw.analysis_manifest_sha256 == obs['analysis_manifest_sha256']
    projected = projected_candidates(raw)
    candidates = {c.candidate_id: c for c in projected.values()}
    assert len(candidates) == len(projected)
    graph = reconstruct_persistent_hop_trajectories(list(projected.values()), config=PersistentHopTrajectoryConfig(minimum_span_s=3., minimum_support=6))
    tracklets = {t.tracklet_id: t for t in graph.tracklets}
    opportunities, _ = export_input(raw, split='ds11-acquisition-pilot', cache_sha256='public-input:' + raw.input_manifest_sha256 + ':' + raw.analysis_manifest_sha256, projected=projected)
    windows = {}
    for o in opportunities:
        for rx in ('rx0', 'rx1'):
            assert o['receivers'][rx]['receiver_status'].startswith('observed_')
            for c in o['receivers'][rx]['candidates']:
                cid = c['projected_candidate_id']
                if cid is not None:
                    assert cid not in windows
                    windows[cid] = o['source_window_id']
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
        tracks.append(dict(track_id=tid, receiver=t['receiver_id'], rf_hz=t['rf_hz'], candidate_ids=ids, window_ids=[windows[c] for c in ids], training_mask=t['training_mask'], candidate_norad=identities['scans'][str(index)]['tracks'][tid]['candidate_norad']))
    lanes = []
    for rf in sorted({t['rf_hz'] for t in tracks}):
        current = [t for t in tracks if t['rf_hz'] == rf]
        tids = {t['track_id'] for t in current}
        ambiguous = {cid: ts for cid, ts in owners.items() if len(ts) > 1 and set(ts) <= tids}
        assert len(current) <= 16
        lanes.append(dict(rf_hz=rf, left=[t['track_id'] for t in current if t['receiver'] == 0], right=[t['track_id'] for t in current if t['receiver'] == 1], ambiguous_owners=ambiguous, ownership_alternatives=[dict(assignment=a, log_prior=w) for a, w in alternatives(ambiguous)]))
    result = dict(cohort=cohort, index=index, family=family, session_id=entry['session_id'], tracks=tracks, lanes=lanes, opportunities=opportunities, sources=sources, elapsed_s=time.monotonic() - started)
    with (HERE / f'input-{cohort}-{index:02d}.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(dict(cohort=cohort, index=index, tracks=len(tracks), windows=len(opportunities), elapsed_s=result['elapsed_s'])), flush=True)


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
