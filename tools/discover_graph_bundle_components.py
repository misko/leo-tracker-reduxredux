"""Inventory all same-lane fragment edges and alias-consistent components."""
import argparse,hashlib
from collections import defaultdict
from itertools import combinations
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from predictive_graph_bundle import polynomial_pair
from leo.analysis.research.retained_track_likelihood import PERIOD


def canonical_sources(inventory_tracks,frozen_ids):
    """Inventory rows can repeat a curve for c=0 and fitted-c; count it once."""
    groups=defaultdict(list)
    for target in inventory_tracks:
        if target['track_id'] in frozen_ids:groups[target['track_id']].append(target)
    if set(groups)!=set(frozen_ids):raise ValueError('frozen curve missing from scan inventory')
    result=[]
    for tid,rows in sorted(groups.items()):
        if len({r['track_index'] for r in rows})!=1:raise ValueError('duplicate curve identity has inconsistent graph indices')
        result.append(dict(rows[0],current_large=any(r['current_large'] for r in rows)))
    return result


def alias_components(edges):
    """Propagate integer lifts; a contradictory cycle invalidates the component."""
    graph=defaultdict(list)
    for edge in edges:
        a,b,delta=edge['first'],edge['second'],edge['alias_lift']
        if a==b or type(delta) is not int:raise ValueError('distinct vertices and integer alias edge required')
        graph[a].append((b,delta));graph[b].append((a,-delta))
    seen=set();components=[]
    for root in sorted(graph):
        if root in seen:continue
        lifts={root:0};pending=[root];conflicts=[]
        while pending:
            a=pending.pop()
            for b,delta in sorted(graph[a]):
                expected=lifts[a]+delta
                if b in lifts:
                    if lifts[b]!=expected:conflicts.append(dict(first=a,second=b,expected=expected,actual=lifts[b]))
                else:lifts[b]=expected;pending.append(b)
        seen.update(lifts);components.append(dict(lifts=lifts,consistent=not conflicts,conflicts=conflicts))
    return components


def union_polynomial(tracks,lifts):
    """Fit one curve without introducing continuous fragment-specific shifts."""
    ids=[o for t in tracks for o in t['observation_ids']]
    times=np.concatenate([t['times'] for t in tracks])
    values=np.concatenate([np.asarray(t['values'])+lift*PERIOD for t,lift in zip(tracks,lifts,strict=True)])
    if len(set(ids))!=len(ids) or len(np.unique(times))!=len(times):return dict(eligible=False,reason='duplicate_observation_or_time')
    if not np.isfinite(np.r_[times,values]).all() or np.ptp(times)<=0:return dict(eligible=False,reason='nonfinite_or_zero_span')
    z=2*(times-times.min())/np.ptp(times)-1;labels=np.concatenate([np.full(len(t['times']),k) for k,t in enumerate(tracks)]);offers=[]
    for degree in range(1,5):
        u=np.polynomial.legendre.legvander(z,degree)
        if np.linalg.matrix_rank(u)!=degree+1:continue
        coef=np.linalg.lstsq(u,values,rcond=None)[0];r=values-u@coef
        offers.append(dict(degree=degree,BIC=float(len(times)*np.log(max(150.**2,np.mean(r*r)))+(degree+1)*np.log(len(times))),
            RMS_hz=float(np.sqrt(np.mean(r*r))),member_RMS_hz=[float(np.sqrt(np.mean(r[labels==k]**2))) for k in range(len(tracks))],
            times_s=times,aligned_values_hz=values,residual_hz=r,coefficients=coef,member_indices=labels))
    if not offers:return dict(eligible=False,reason='rank_deficient')
    best=min(offers,key=lambda r:r['BIC']);eligible=best['RMS_hz']<250 and max(best['member_RMS_hz'])<250
    return dict(best,eligible=eligible,reason='shape_candidate' if eligible else 'joint_or_member_shape_mismatch')


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    queue_path=args.study/'systematic-annotation-v1/protocol.json';queue=read(queue_path)['rows'];jobs=defaultdict(list)
    for row in queue:jobs[row['inventory']].append(row)
    bundles=[];components=[];edge_rows=[];scan_rows=[];exclusions=[];sources={str(queue_path):hashlib.sha256(queue_path.read_bytes()).hexdigest()}
    for path,rows in sorted(jobs.items()):
        path=Path(path);inv=read(path);track_path=Path(inv['job']['root'])/inv['job']['case']/'tracks.json';tracks=read(track_path)
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (path,track_path)};sources.update(source_hashes)
        occupied=set(o for arm in inv['policy'].values() for o in arm['proposed_associated_ids']);selected={};lanes=defaultdict(list)
        frozen={r['track_id'] for r in rows}
        for target in canonical_sources(inv['tracks'],frozen):
            t=tracks[target['track_index']];tid=target['track_id']
            if not target['current_large'] or occupied.intersection(t['observation_ids']):
                exclusions.append(dict(job_id=inv['job']['job_id'],track_id=tid,reason='not_current_large_or_partially_owned'));continue
            selected[tid]=target;lanes[t['receiver'],t['channel'],t['rf_hz']].append(tid)
        edges=[]
        for tids in lanes.values():
            for first,second in combinations(sorted(tids),2):
                a=tracks[selected[first]['track_index']];b=tracks[selected[second]['track_index']]
                if max(a['start_s'],b['start_s'])-min(a['end_s'],b['end_s'])>12:continue
                times=np.r_[a['times'],b['times']]
                if len(np.unique(times))!=len(times) or set(a['observation_ids'])&set(b['observation_ids']):continue
                fit=polynomial_pair(a,b)
                if not fit or fit['RMS_hz']>=250:continue
                edges.append(dict(first=first,second=second,alias_lift=fit['alias_lift'],RMS_hz=fit['RMS_hz'],degree=fit['degree']))
        edge_rows.extend(dict(job_id=inv['job']['job_id'],label=inv['job']['label'],**e) for e in edges)
        for component in alias_components(edges):
            tids=sorted(component['lifts']);members=[dict(track_id=tid,track_index=selected[tid]['track_index'],alias_lift=component['lifts'][tid]) for tid in tids]
            parts=[tracks[m['track_index']] for m in members];count=sum(len(t['times']) for t in parts)
            bid=hashlib.sha256('|'.join(tids).encode()).hexdigest()[:20];fit=union_polynomial(parts,[m['alias_lift'] for m in members]) if component['consistent'] else dict(eligible=False,reason='inconsistent_alias_cycle')
            times=np.concatenate([t['times'] for t in parts]);blocks=len(np.unique(np.floor(times/12)))
            eligible=component['consistent'] and fit['eligible'] and blocks>=3
            receipt=dict(bundle_id=bid,job_id=inv['job']['job_id'],label=inv['job']['label'],members=len(tids),points=count,span_s=float(np.ptp(times)),
                eligible=eligible,reason=fit['reason'] if blocks>=3 else 'fewer_than_three_timestamp_blocks',alias_consistent=component['consistent'],conflicts=component['conflicts'])
            components.append(receipt)
            if eligible:
                bundles.append(dict(bundle_id=bid,job=inv['job'],inventory=str(path),points=count,members=members,nomination=fit,
                    source_hashes=source_hashes,selection_uses_frozen_graph_CFO=True,GPS_used=False,satellite_identity_used=False,
                    nomination_is_not_validation=True,connected_component_alias_consistency=True))
        scan_rows.append(dict(job_id=inv['job']['job_id'],label=inv['job']['label'],inventory_tracks=len(rows),eligible_unowned_tracks=len(selected),pair_edges=len(edges)))
    bundles.sort(key=lambda b:(-len(b['members']),-b['points'],b['bundle_id']))
    # Ranking is fixed before any candidate ID or position error is evaluated.
    candidates=sorted([b for b in bundles if len(b['members'])>=3 and b['points']<=180],key=lambda b:(-b['points'],b['bundle_id']))
    selected=[];seen=set()
    for b in candidates:
        if b['job']['job_id'] in seen:continue
        selected.append(b);seen.add(b['job']['job_id'])
        if len(selected)>=args.limit:break
    write(args.output/'discovery.json',dict(bundles=bundles,components=components,edges=edge_rows,scans=scan_rows,exclusions=exclusions,
        frozen_inventory_size=len(queue),source_hashes=sources,no_associations_authorized=True,conditional_on_frozen_graph_and_full_CFO_group_selection=True))
    write(args.output/'protocol.json',dict(jobs=selected,selection='largest eligible groups with at least three members and at most 180 points, distinct scans; no ID or GPS selection',
        maximum_cases=args.limit,pair_gap_s=12,noise_floor_hz=150,maximum_polynomial_degree=4,maximum_union_and_member_RMS_hz=250,
        source_sha256=hashlib.sha256((args.output/'discovery.json').read_bytes()).hexdigest(),no_production_change=True))
    print('scans',len(scan_rows),'edges',len(edge_rows),'components',len(components),'eligible',len(bundles),'selected',len(selected),flush=True)
    for b in selected:print(b['job']['label'],b['bundle_id'],len(b['members']),b['points'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--limit',type=int,default=4);args=p.parse_args()
    if not 1<=args.limit<=8:raise ValueError('bounded evaluation requires one to eight groups')
    run(args)
