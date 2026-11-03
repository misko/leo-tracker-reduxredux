"""Explicit no-refinement input adapter; never publishes fake refined results.

Original frequencies and GLRT margins, one deterministic top candidate per
original passing window. Public tracking-input port supplies bootstrap records.
No IQ read, orbit-guided frequency correction, or inherited refined calibration.
"""
import json
from pathlib import Path
import numpy as np

from numeric_data import Data, enable_research_model, view
from cohort import ROOF, digest


def top_rows(records):
    chosen = {}
    for r in records:
        key = r['group_id']
        rank = (-r['original_margin'], r['row_index'])
        if key not in chosen or rank < chosen[key][0]:
            chosen[key] = (rank, r['row_index'])
    return sorted(r[1] for r in chosen.values())


def load(directory, *, top_only=True):
    enable_research_model()
    from oracle_position_diagnostic import reference_coordinates
    paths = [directory/'observations.json', directory/'orbit-bank/states.npz',
             directory/'orbit-bank/receipt.json', Path(__file__)]
    source = json.loads(paths[0].read_text())
    bank = json.loads(paths[2].read_text())
    if (bank['signature']['observations_sha256'] != digest(paths[0].read_bytes()) or
            bank['arrays_sha256'] != digest(paths[1].read_bytes())):
        raise ValueError('Original-candidate orbit-bank binding failed')
    records = source['records']
    if len({r['row_index'] for r in records}) != len(records):
        raise ValueError('Duplicate original row')
    with np.load(paths[1], allow_pickle=False) as a:
        data = Data(nodes=a['nodes_s'].copy(), numbers=a['numbers'].copy(),
                    position=a['position_km'].copy(), velocity=a['velocity_km_s'].copy())
    for name, field, dtype in [('times','time_s',float), ('measured','original_hz',float),
            ('rf','rf_hz',float), ('receiver','receiver',int), ('channel','channel',int),
            ('margin','original_margin',float), ('original_rows','row_index',int)]:
        setattr(data, name, np.array([r[field] for r in records], dtype=dtype))
    _, data.group = np.unique([r['group_id'] for r in records], return_inverse=True)
    if not np.all(np.isfinite(data.measured)) or not np.all(np.isfinite(data.margin)):
        raise ValueError('Nonfinite original candidate')
    data.initial = np.zeros(6+len(data.numbers))
    data.initial[:2] = reference_coordinates(*ROOF)
    data.reference_time_s = 150.
    data.session_id = source['summary']['session_id']
    data.origin_utc_ns = source['origin_utc_ns']
    data.sources = {str(p):digest(p.read_bytes()) for p in paths}
    data.top_rows = np.array(top_rows(records), int)
    data.top_mask = np.isin(data.original_rows, data.top_rows)
    if sum(data.top_mask) != len(np.unique(data.group)):
        raise ValueError('Original top-one window inventory mismatch')
    if top_only:
        data = view(data, data.top_mask)
        data.top_mask = np.ones(len(data.times), bool)
    return data


def reconstruct(data, directory):
    import inspect
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.analysis.persistent_hop_trajectory import (
        reconstruct_persistent_hop_trajectories, PersistentHopTrajectoryConfig)
    original = json.loads((directory/'observations.json').read_text())
    store = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        source = store.load(data.session_id)
    finally:
        store.close()
    if (source.input_manifest_sha256 != original['signature']['manifest_sha256'] or
            source.analysis_manifest_sha256 != original['analysis_manifest_sha256']):
        raise ValueError('Tracking input changed after export')
    live = {p.candidate_id:p for p in project_scanner_candidates(source)}
    metadata = {r['row_index']:r for r in original['records']}
    points, lookup, nonpositive = [], {}, []
    for i, row in enumerate(data.original_rows):
        p = live[metadata[int(row)]['candidate_id']]
        np.testing.assert_allclose([p.measured_cfo_hz,p.margin], [data.measured[i],data.margin[i]], rtol=0,atol=0)
        if data.margin[i] <= 0:
            nonpositive.append(int(row)); continue
        points.append(p); lookup[p.candidate_id] = i
    config = PersistentHopTrajectoryConfig()
    result = reconstruct_persistent_hop_trajectories(tuple(points), config=config)
    tracks = []
    for track in result.tracklets:
        rows = sorted({lookup[p.candidate_id] for p in track.points},key=lambda i:data.times[i])
        if len(rows)<15 or np.ptp(data.times[rows])<15: continue
        tracks.append(dict(track_id=str(track.tracklet_id), rows=rows, receiver=int(data.receiver[rows[0]]),
            span_s=float(np.ptp(data.times[rows])),channel=int(data.channel[rows[0]])))
    chosen=[]
    for rx in (0,1):
        chosen.extend(sorted([r for r in tracks if r['receiver']==rx],key=lambda r:(-r['span_s'],r['track_id']))[:12])
    import dataclasses
    return chosen, dict(configuration=dataclasses.asdict(config),all_tracks=len(result.tracklets),
        supported_tracks=len(tracks),chosen_tracks=len(chosen),bootstrap_only_nonpositive_rows=nonpositive,
        measurement_variant='original-no-refinement',sources={
            str(Path(inspect.getfile(o))):digest(Path(inspect.getfile(o)).read_bytes()) for o in
            (project_scanner_candidates,reconstruct_persistent_hop_trajectories,ScannerTrackingInputStore)})


def seed(parent):
    """Same ten seed families as seed-timing-v6, with original-candidate inputs."""
    from seed_timing_variant import timing_seed
    from prepare_scans import ShiftedData
    from staged_fit import fit_receiver_lines
    from track_seed import loss
    from refinement import circular
    from process_stage import save
    target = parent/'seed-timing-v6'
    target.mkdir(exist_ok=True)
    for name in ('observations.json','orbit-bank'):
        dest=target/name; source=parent/name
        if dest.exists():
            if dest.resolve()!=source.resolve(): raise ValueError('Seed input mismatch')
        else: dest.symlink_to(source.resolve(),target_is_directory=source.is_dir())
    output=target/'bootstrap.json'
    if output.exists(): return
    data=load(target); previous=parent/'bootstrap.json'; saved=json.loads(previous.read_text())
    timing,indices=timing_seed(saved['tracks'],len(data.numbers))
    rough=dict(position_km=data.initial[:2],assignments=[r for r in saved['tracks'] if r['accepted']])
    trials=[dict(r,initializer_family='zero-individual-timing') for r in saved['common_timing_trials']]
    for common in (-10.,-5.,0.,5.,10.):
        shifts=np.clip(timing+np.clip(common,-10+1e-8,10-1e-8),-20+1e-6,20-1e-6)
        p=fit_receiver_lines(ShiftedData(data,shifts),rough);p[6:]=shifts
        costs=[]
        for t in rough['assignments']:
            rows=np.array(t['rows'],int)
            pred,visible=data.predict(p,rows=rows,satellites=np.full(len(rows),t['satellite_index']))
            if np.any(visible): costs.append(float(np.mean(loss(circular(data.measured[rows]-pred)[visible]))))
        trials.append(dict(common_shift_s=common,parameters=p.tolist(),score=float(np.mean(costs)),
                           initializer_family='shape-individual-timing'))
    best=min(trials,key=lambda r:r['score'])
    save(output,dict(saved,initial_parameters=best['parameters'],common_timing_trials=trials,
        sources={**data.sources,str(previous):digest(previous.read_bytes())},
        timing_seed_relative_s=timing[indices].tolist(),timing_seed_indices=indices,
        measurement_variant='original-no-refinement',scope=__doc__))
