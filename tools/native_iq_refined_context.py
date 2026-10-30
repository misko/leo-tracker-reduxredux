"""Research-only native CFO replacement with unchanged IDs, times and noise."""
import copy,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read
from leo.analysis.research.retained_track_likelihood import PERIOD


def reject_unsupported_shared_refinement(protocol):
    if protocol.get('measurement_refinement'):
        raise ValueError('shared-family inclusion does not yet replay native IQ refinements; use a supported refinement-aware route')


def replacement_values(track,rows,method):
    byid={r['point']['observation_id']:r for r in rows}
    if len(byid)!=len(rows) or set(byid)!=set(track['observation_ids']):raise ValueError('refinement must cover exactly the complete native target')
    values=[]
    for oid,t,y in zip(track['observation_ids'],track['times'],track['values'],strict=True):
        r=byid[oid];p=r['point'];m=r['methods'][method]
        if p['time_s']!=t:raise ValueError('refinement changed observation time')
        lift=(y-p['CFO_hz'])/PERIOD
        if abs(lift-round(lift))>1e-8:raise ValueError('refinement original CFO differs beyond integer alias')
        if any(v for k,v in m.items() if k.endswith('_search_boundary')):raise ValueError('refinement hit a search boundary')
        if not np.isfinite(m['CFO_hz']):raise ValueError('nonfinite refined CFO')
        values.append(y+m['CFO_hz']-p['CFO_hz'])
    return np.asarray(values)


def refined_context(d,target,path,method='joint_all'):
    path=Path(path);result=read(path);folder=path.parent;plan=read(folder/'plan.json');panel=read(folder/'panel/manifest.json')
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    if (not result.get('all_original_selected_points_present') or not result.get('no_GPS_TLE_or_satellite_in_local_refinement')
            or not panel.get('raw_authority_matches_tracking')):raise ValueError('incomplete verified IQ refinement')
    if result['plan_sha256']!=sha(folder/'plan.json') or panel['plan_sha256']!=sha(folder/'plan.json'):raise ValueError('changed refinement plan')
    worker_rows=[]
    for name,digest in result['worker_hashes'].items():
        if sha(Path(name))!=digest:raise ValueError('changed refinement worker')
        worker=read(Path(name));worker_rows.extend(worker['rows'])
        if worker['panel_manifest_sha256']!=sha(folder/'panel/manifest.json'):raise ValueError('changed refinement panel')
    if sorted(worker_rows,key=lambda r:r['point']['observation_id'])!=sorted(result['rows'],key=lambda r:r['point']['observation_id']):
        raise ValueError('refinement summary differs from terminal worker measurements')
    execution=read(folder/'execution.json')
    if len(execution)!=plan['workers'] or any(r['status']!='complete' for r in execution):raise ValueError('refinement workers incomplete')
    index=target['track_index'];track=d['scan'].tracks[index];ids=set(track['observation_ids'])
    occupied={o for e in d['entries'] for o in e['observation_ids']}
    for p,_ in d['problems'].values():
        occupied.update(o for i,sl in zip(p.members,p.slices,strict=True) for o,k in zip(d['scan'].tracks[i]['observation_ids'],p.keep[sl],strict=True) if k)
    if ids&occupied:raise ValueError('refinement overlaps retained evidence')
    changed=copy.copy(d['scan']);changed.tracks=list(changed.tracks)
    changed.tracks[index]=dict(track,values=replacement_values(track,result['rows'],method))
    receipt=dict(source=str(path),sha256=sha(path),method=method,track_index=index,observation_ids=track['observation_ids'],
        plan_sha256=sha(folder/'plan.json'),panel_manifest_sha256=sha(folder/'panel/manifest.json'),
        original_timestamps_ownership_noise_and_aliases_preserved=True,production_measurements_unchanged=True)
    return dict(d,scan=changed),receipt


def replay_refinement(d,target,receipt):
    changed,actual=refined_context(d,target,Path(receipt['source']),receipt['method'])
    if actual!=receipt:raise ValueError('measurement refinement receipt changed')
    return changed
