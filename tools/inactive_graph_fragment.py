"""Expose only commonly unowned graph observations as predictive evidence."""
import copy
import numpy as np
from pathlib import Path
from debug_fast_graph_unassociated import read
from leo.analysis.research.retained_track_likelihood import whitening


def append_inactive_fragment(scan,index,occupied):
    """Preserve the original graph/calibration arrays and every measured value."""
    track=scan.tracks[index];ids=track['observation_ids'];occupied=set(occupied)
    if len(ids)!=len(set(ids)):raise ValueError('parent graph repeats observation IDs')
    keep=np.array([o not in occupied for o in ids],bool)
    if not keep.any() or keep.all():raise ValueError('a partial graph curve must contain owned and unowned observations')
    times=np.asarray(track['times'])[keep];values=np.asarray(track['values'])[keep]
    if np.any(np.diff(times)<=0) or not np.isfinite(np.r_[times,values]).all():raise ValueError('fragment requires finite increasing measurements')
    fragment=dict(track,key=track['key']+'-INACTIVE',observation_ids=[o for o,k in zip(ids,keep,strict=True) if k],
        times=times.copy(),values=values.copy(),start_s=float(times[0]),end_s=float(times[-1]),
        quality_status='inherited_parent_graph_not_independently_refitted',parent_graph_index=index,
        parent_graph_component=track['key'],parent_graph_indices=np.flatnonzero(keep))
    changed=copy.copy(scan);changed.tracks=[*scan.tracks,fragment];changed.white=[*scan.white,whitening(times)]
    changed.rx_basis=[*scan.rx_basis,np.asarray(scan.rx_basis[index])[keep].copy()]
    return changed,len(scan.tracks)


def inactive_fragment_context(d,inventory,track_id):
    source=next(t for t in inventory['tracks'] if t['track_id']==track_id and t['current_large'])
    occupied=set()
    for arm in ('c0','fitted_c'):
        occupied.update(inventory['policy'][arm]['proposed_associated_ids'])
        p,_=d['problems'][arm]
        occupied.update(o for i,sl in zip(p.members,p.slices,strict=True)
            for o,k in zip(d['scan'].tracks[i]['observation_ids'],p.keep[sl],strict=True) if k)
    occupied.update(o for e in d['entries'] for o in e['observation_ids'])
    changed,index=append_inactive_fragment(d['scan'],source['track_index'],occupied)
    t=changed.tracks[index]
    target=dict(source,track_index=index,component=t['key'],observation_ids=t['observation_ids'],
        inactive_graph_fragment=True,parent_track_index=source['track_index'],parent_track_id=track_id,
        selection='all parent observations unused by both c arms; no frequency or GPS selection',
        original_graph_unchanged=True,source_parent_indices=t['parent_graph_indices'])
    return dict(d,scan=changed),target


def validated_inactive_context(d,inventory,validation):
    """Reconstruct exactly the annotated fragment, or reject changed ownership."""
    validation=Path(validation);protocol=read(validation/'protocol.json');result=read(validation/'result.json')
    if not result.get('inactive_graph_fragment') or protocol['job']['job_id']!=inventory['job']['job_id']:
        raise ValueError('inactive fragment provenance does not match this scan')
    updated,target=inactive_fragment_context(d,inventory,result['track_id']);expected=protocol['target']
    for key in ('track_id','component','parent_track_index','observation_ids'):
        if target[key]!=expected[key]:raise ValueError('inactive fragment observations or parent changed since annotation')
    return updated,target


def original_graph_view(problem,count):
    """Appended predictive rows must not enter the indexed graph-extension path."""
    if not 0 < count <= len(problem.scan.tracks):raise ValueError('invalid original graph count')
    view=copy.copy(problem);view.scan=copy.copy(problem.scan);view.scan.tracks=problem.scan.tracks[:count]
    return view
