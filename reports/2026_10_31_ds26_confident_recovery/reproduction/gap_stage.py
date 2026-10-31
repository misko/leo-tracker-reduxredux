"""Research adapter for native graph fragments split solely at >5 s gaps.

Original graph, calibration, measurements and IDs are retained. Each eligible
fragment is re-annotated; parent satellite confidence is not copied to it.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys
import numpy as np
from run_trials import RELEASE, STUDY, targets, read
sys.path[:0]=[str(RELEASE/'tools'),str(RELEASE/'src')]
from debug_fast_graph_unassociated import write
from algo04_numerical_helper import patched_stages

def partitions(times, gap=5., minimum_points=12, minimum_span=10.):
    t=np.asarray(times,float)
    if t.ndim!=1 or len(t)<1 or not np.isfinite(t).all() or np.any(np.diff(t)<=0):
        raise ValueError('finite strictly increasing times required')
    cuts=np.r_[0,np.flatnonzero(np.diff(t)>gap)+1,len(t)]
    return [(int(a),int(b)) for a,b in zip(cuts[:-1],cuts[1:])
            if b-a>=minimum_points and t[b-1]-t[a]>=minimum_span]

def prepare(t):
    from diagnose_all_large_tracks import context
    from leo.analysis.research.retained_track_likelihood import PERIOD
    inv=read(t['inventory']);d=context(inv)
    source=next(r for r in inv['tracks'] if r['track_id']==t['track_id'])
    parent=d['scan'].tracks[source['track_index']]
    obs_path=Path(inv['job']['root'])/inv['job']['case']/'observations.json'
    obs={o['observation_id']:o for o in read(obs_path)}
    folder=STUDY/t['case']/'gap-source';folder.mkdir(exist_ok=False)
    branches=[]
    for a,b in partitions(parent['times']):
        ids=parent['observation_ids'][a:b];values=parent['values'][a:b]
        lifts=np.rint((values-np.array([obs[o]['measured_cfo_hz'] for o in ids]))/PERIOD).astype(int)
        branches.append(dict(branch_id=hashlib.sha256('\n'.join(ids).encode()).hexdigest()[:20],
            parent_track_id=t['track_id'],parent_index=source['track_index'],parent_key=parent['key'],
            observation_ids=ids,times_s=parent['times'][a:b],values_hz=values,alias_lifts=lifts,
            receiver=parent['receiver'],channel=parent['channel'],rf_hz=parent['rf_hz'],
            quality_status='inherited_graph_gap_fragment',pieces=parent['pieces'],
            RMS_hz=parent['residual_rms_hz'],large=True))
    write(folder/'protocol.json',dict(job=inv['job'],gap_s=5,minimum_points=12,minimum_span_s=10,
        selection='All eligible time-gap components; no frequency, residual, satellite or position filter',
        parent_observation_ids=parent['observation_ids'],retained_points=sum(len(b['observation_ids']) for b in branches),
        input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(t['inventory']),obs_path)}))
    write(folder/'branches.json',dict(branches=branches))

def gap_context(d,inventory,path,branch_id):
    from native_predictive_branch import append_branch
    path=Path(path);pr=read(path.parent/'protocol.json')
    if pr['job']['job_id']!=inventory['job']['job_id'] or pr['gap_s']!=5:
        raise ValueError('wrong source identity or gap policy')
    for p,h in pr['input_sha256'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('source changed')
    b=next(b for b in read(path)['branches'] if b['branch_id']==branch_id)
    parent=d['scan'].tracks[b['parent_index']]
    if parent['key']!=b['parent_key']:raise ValueError('parent changed')
    eligible=[parent['observation_ids'][a:z] for a,z in partitions(parent['times'])]
    if b['observation_ids'] not in eligible:raise ValueError('not an eligible whole time-gap component')
    occupied={o for r in inventory['policy'].values() for o in r['proposed_associated_ids']}
    for p,_ in d['problems'].values():
        occupied.update(o for i,sl in zip(p.members,p.slices,strict=True)
                        for o,k in zip(d['scan'].tracks[i]['observation_ids'],p.keep[sl],strict=True) if k)
    occupied.update(o for e in d['entries'] for o in e['observation_ids'])
    obs=read(Path(inventory['job']['root'])/inventory['job']['case']/'observations.json')
    changed,i=append_branch(d['scan'],b,obs,occupied)
    target=dict(track_id=branch_id,track_index=i,component=changed.tracks[i]['key'],current_large=True,
        observation_ids=b['observation_ids'],native_branch_source=str(path),
        native_branch_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        original_graph_unchanged=True,gap_parent=b['parent_key'])
    return dict(d,scan=changed),target

def execute(script, arguments):
    import native_predictive_branch
    native_predictive_branch.native_context=gap_context
    if Path(script).name=='audit_shared_predictive_inclusion.py':
        import diagnose_all_large_tracks
        original=diagnose_all_large_tracks.context
        trial=Path(arguments[arguments.index('--trial')+1]);pr=read(trial/'protocol.json')
        def context(inv):
            d=original(inv)
            for receipt in pr['annotation_receipts']:
                validation=Path(receipt['path']);source=native_predictive_branch.validated_native_source(validation)
                d,_=gap_context(d,inv,source,read(validation/'result.json')['track_id'])
            return d
        diagnose_all_large_tracks.context=context
    with patched_stages(reference_limit_s=30,centered_lbfgsb=True) as state:
        sys.argv=[str(script),*arguments]
        try:runpy.run_path(str(script),run_name='__main__')
        finally:
            out=Path(arguments[arguments.index('--output')+1])
            receipt=out.parent/(out.name+'-numerics.json')
            write(receipt,state)

if __name__=='__main__':
    if sys.argv[1]=='prepare':
        for t in targets():
            if t['case'] in ('DS27-0004','DS27-0022'):prepare(t)
    else:execute(RELEASE/'tools'/sys.argv[1],sys.argv[2:])
