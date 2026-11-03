"""Public source views bound to availability-correct calibration geometry."""
from collections import defaultdict
import inspect
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(PARENT))
sys.path.insert(0, str(ROOT))
from doppler_pilot import fast, read, digest
from tools.rx_paired_opportunities import export_input, projected_candidates
from tools.ds7_export_baseline import partition
from bit_ownership import source_bits


def main(index):
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig, reconstruct_persistent_hop_trajectories
    from leo.operations.tle_archive import TleArchiveReader
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.sky.propagation import parse_element_sets, parse_element_set_records
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    start = time.monotonic()
    geometry_path = PARENT / 'causal-calibration-geometry.polished.json'
    inventory_path = PARENT / 'acquisition-calibration-inventory.json'
    geometry, inventory = read(geometry_path), read(inventory_path)
    assert geometry['fit']['qualified'] and index in geometry['indices']
    for p, h in geometry['sources'].items():
        assert digest(p) == h, p
    family, role, declared_capture = next((f, role, r) for f in inventory['families'] for role in ('calibration', 'validation') for r in f[role] if r['index'] == index)
    assert declared_capture['capture_end_utc_ns'] < geometry['cutoff_utc_ns'] and declared_capture['finalized_utc_ns'] < geometry['cutoff_utc_ns']
    plan_path = HERE.parents[2] / '2026_09_30_ds10_scale_weighting/plan.json'
    plan = read(plan_path)
    entry = plan['inputs'][index]
    assert entry['session_id'] == declared_capture['session_id']
    position = geometry['sessions'].index(entry['session_id'])
    x = np.array(geometry['fit']['x'])[[0, 1, position + 2]]
    sources = {str(p): digest(p) for p in (geometry_path, inventory_path, plan_path, Path(__file__), HERE / 'PROTOCOL.md', HERE / 'bit_ownership.py', ROOT / 'tools/rx_paired_opportunities.py', ROOT / 'tools/ds7_export_baseline.py')}
    for artifact in entry['artifacts']:
        assert digest(artifact['path']) == artifact['sha256'].removeprefix('sha256:')
        sources[artifact['path']] = digest(artifact['path'])
    doc = fast.load_documents(dict(config=geometry['config'], inputs=[entry]))[0]
    manifest = read(next(a['path'] for a in entry['artifacts'] if a['kind'] == 'candidates' and a['path'].endswith('.json')))
    npz = next(a['path'] for a in entry['artifacts'] if a['kind'] == 'candidates' and a['path'].endswith('.npz'))
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    refs, loaded = archive.list_snapshots(), []
    for declared in manifest['provider_sources']:
        ref = next(r for r in refs if r.provider == declared['provider'] and r.collected_utc_ns == declared['collected_utc_ns'] and 'sha256:' + r.sha256 == declared['snapshot_sha256'])
        assert ref.collected_utc_ns < doc['start_utc_ns']
        text = archive.read(ref)
        assert 'sha256:' + __import__('hashlib').sha256(text.encode()).hexdigest() == declared['snapshot_sha256']
        filtered, _ = exclude_labelled_starlink_debris(text)
        loaded.append((declared, list(parse_element_set_records(filtered)), parse_element_sets(filtered).element_epoch_utc_ns()))
        sources[str(ref.path)] = digest(ref.path)
    roster = next(records for declared, records, epochs in loaded if declared['snapshot_sha256'] == manifest['baseline_snapshot_sha256'])
    choices = {}
    for declared, records, epochs in loaded:
        for record, epoch in zip(records, epochs, strict=True):
            key = (int(epoch), declared['collected_utc_ns'], declared['snapshot_sha256'])
            if record.satellite_number not in choices or key > choices[record.satellite_number][0]:
                choices[record.satellite_number] = key, record
    catalogue = parse_element_sets(''.join(choices[r.satellite_number][1].text for r in roster))
    assert len(catalogue.satellite_numbers) == manifest['catalogue_size']
    engine = fast.Stationary(doc, geometry['config'])
    tracks = {t['track_id']: t for t in doc['tracks']}
    items = {t['track_id']: t for t in manifest['tracks']}
    grid = np.asarray(geometry['config']['timing_grid_s'])
    hi = int(np.searchsorted(grid, x[2], side='right'))
    lo = hi - 1
    assert 0 <= lo < hi < len(grid)
    taus = grid[[lo, hi]]
    fraction = (x[2] - taus[0]) / (taus[1] - taus[0])
    selections, excluded, replay = {}, [], 0.
    with np.load(npz, allow_pickle=False) as bank:
        for tid, track in tracks.items():
            item = items[tid]
            prediction, visible = engine.prediction(track, x)
            scores, _, audits, _ = fast.profile(track['y'][None] - prediction, track['mask'])
            assert all(a['converged'] for a in audits)
            scores = np.where(visible, scores, -np.inf)
            posterior = np.exp(scores - logsumexp(scores))
            slot = int(np.argmax(posterior))
            if posterior[slot] < .9:
                excluded.append(dict(track_id=tid, confidence=float(posterior[slot]), reason='ambiguous_identity'))
                continue
            candidate = int(bank[f"candidate_ids_{item['index']}"][slot])
            p, v, valid = propagate_candidate_states(catalogue, np.array([candidate]), doc['start_utc_ns'], np.asarray(track['times_s']), taus)
            np.testing.assert_array_equal(valid, [candidate])
            error = max(float(np.max(abs(p[0] - track['candidate_position_km'][slot, [lo, hi]]))), float(np.max(abs(v[0] - track['candidate_velocity_km_s'][slot, [lo, hi]]))))
            assert error < 1e-8
            replay = max(replay, error)
            selections[tid] = dict(candidate=candidate, norad=int(catalogue.satellite_numbers[candidate]), confidence=float(posterior[slot]), rf_hz=track['rf_hz'])
    store = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        raw = store.load(entry['session_id'])
    finally:
        store.close()
    assert raw.qualified and raw.timing.qualified
    assert raw.input_manifest_sha256 == entry['manifest_sha256'] and raw.analysis_manifest_sha256 == doc['analysis_manifest_sha256']
    projected = projected_candidates(raw)
    by_id = {candidate.candidate_id: candidate for candidate in projected.values()}
    assert len(by_id) == len(projected)
    opportunities, _ = export_input(raw, split=role, cache_sha256='public-input:' + raw.input_manifest_sha256 + ':' + raw.analysis_manifest_sha256, projected=projected)
    assert all(o['opportunity_status'] in ('both_receivers_candidate_present', 'both_receivers_candidate_absent', 'one_receiver_candidate_present') for o in opportunities)
    graph = reconstruct_persistent_hop_trajectories(list(projected.values()), config=PersistentHopTrajectoryConfig(minimum_span_s=3., minimum_support=6))
    graphtracks = {t.tracklet_id: t for t in graph.tracklets}
    views = {}
    for i, o in enumerate(opportunities):
        for rx in (0, 1):
            for c in o['receivers'][f'rx{rx}']['candidates']:
                cid = c['projected_candidate_id']
                if cid is not None:
                    assert cid not in views
                    views[cid] = i, rx
    owners, groups = defaultdict(set), defaultdict(list)
    for tid, selection in selections.items():
        key = selection['norad'], selection['rf_hz']
        groups[key].append(tid)
        track = tracks[tid]
        points = graphtracks[tid].points
        assert len(points) == len(track['times_s'])
        for j, point in enumerate(points):
            candidate = by_id[point.candidate_id]
            assert abs((candidate.support_center_utc_ns - doc['start_utc_ns']) / 1e9 - track['times_s'][j]) < 1e-9
            assert abs(point.normalized_dealiased_cfo_hz - track['y'][j]) < 1e-7
            assert candidate.receiver_id == track['receiver_id'] and candidate.actual_rf_hz == track['rf_hz']
            assert candidate.visit_index == track['visits'][j]
            owners[point.candidate_id].add(key)
    times = np.array([((o['window_start_utc_ns'] - doc['start_utc_ns']) + (o['window_end_utc_ns'] - doc['start_utc_ns'])) / 2e9 for o in opportunities])
    ids = sorted({s['candidate'] for s in selections.values()})
    positions, _, valid = propagate_candidate_states(catalogue, np.array(ids), doc['start_utc_ns'], times, taus)
    np.testing.assert_array_equal(valid, ids)
    receiver, _ = fast.baseline.site(*engine.coordinates(x))
    lat, lon = np.radians(engine.coordinates(x))
    rotation = np.array([[-np.sin(lon), np.cos(lon), 0], [-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat)], [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]])
    lanes = []
    for key, members in sorted(groups.items()):
        norad, rf = key
        indices = [i for i, o in enumerate(opportunities) if o['receivers']['rx0']['actual_rf_hz'] == rf]
        bits = source_bits(key, owners, views, len(opportunities))
        slot = ids.index(selections[members[0]]['candidate'])
        pos = positions[slot, 0] * (1 - fraction) + positions[slot, 1] * fraction
        los = pos - receiver
        los /= np.linalg.norm(los, axis=-1)[:, None]
        lanes.append(dict(norad=norad, rf_hz=rf, tracks=members, times_s=times[indices].tolist(), los_enu=(los @ rotation.T)[indices].tolist(), bits=bits[indices].tolist(), training_mask=[partition(entry['session_id'], opportunities[i]['source_window']['visit_index']) for i in indices]))
    for function in (propagate_candidate_states, reconstruct_persistent_hop_trajectories, ScannerTrackingInputStore):
        p = Path(inspect.getfile(function))
        sources[str(p)] = digest(p)
    result = dict(index=index, family=family['family'], role=role, session_id=entry['session_id'], sample_rate_hz=family['sample_rate_hz'], rf_hz=family['rf_hz'], lanes=lanes, inferred_labels=True, excluded_tracks=excluded, eligibility_exclusions=doc.get('eligibility_exclusions', []), original_bank_replay_maximum=replay, fixed_geometry_x=x.tolist(), sources=sources, elapsed_s=time.monotonic() - start)
    with (HERE / f'donor-{index:02d}.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(dict(index=index, family=result['family'], role=role, sources=len(lanes), selected_tracks=len(selections), excluded=len(excluded), replay=replay, elapsed_s=result['elapsed_s'])), flush=True)


if __name__ == '__main__':
    main(int(sys.argv[1]))
