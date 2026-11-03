"""Distinguish shared-probe evidence from exact acquisition-candidate reuse."""
import collections
import hashlib
import itertools
import json
import statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
BASE=HILL.parent/'2026_09_30_ds11_single10'


def read(p):
    return json.loads(Path(p).read_text())


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def components(support):
    adjacent={k:set() for k in support}
    for a,b in itertools.combinations(support,2):
        if support[a]&support[b]:
            adjacent[a].add(b);adjacent[b].add(a)
    todo=set(support);result=[]
    while todo:
        first=min(todo);todo.remove(first);found={first};pending=[first]
        while pending:
            for nxt in sorted(adjacent[pending.pop()]&todo):
                todo.remove(nxt);found.add(nxt);pending.append(nxt)
        result.append(sorted(found))
    return result


def main():
    sidecar_path=HILL/'source_consistency/source_groups.json'
    diagnostic_path=HILL/'source_consistency/diagnostic.json'
    sidecar,diagnostic,plan=map(read,(sidecar_path,diagnostic_path,BASE/'plan.json'))
    assert sidecar['plan_sha256']==digest(BASE/'plan.json')
    for path,h in diagnostic['source_sha256'].items():
        assert digest(path)==h,path
    sources=dict(diagnostic['source_sha256'])
    for path in (sidecar_path,diagnostic_path,Path(__file__),HERE/'test_run.py'):
        sources[str(path)]=digest(path)
    scans=[];all_frequency_differences=[];all_time_differences=[]
    for label,scan in sorted(sidecar['scans'].items(),key=lambda r:int(r[0])):
        index=int(label);entry=plan['inputs'][index]
        artifact=next(a for a in entry['artifacts'] if a['kind']=='observations')
        path=Path(artifact['path']); h=digest(path)
        assert h==scan['observation_sha256']==artifact['sha256'].removeprefix('sha256:')
        doc=read(path);sources[str(path)]=h
        assert doc['session_id']==entry['session_id']==scan['session_id']
        assert {t['track_id'] for t in doc['tracks']}==set(scan['tracks'])
        groups=collections.defaultdict(list); candidates=collections.defaultdict(list)
        support={}; observations={}
        for track in doc['tracks']:
            tid=track['track_id']; points=scan['tracks'][tid]
            assert len(points)==len(track['times_s'])
            assert [p['training'] for p in points]==track['training_mask']
            support[tid]={p['source_group_id'] for p in points if p['training']}
            for i,p in enumerate(points):
                row=dict(track_id=tid,index=i,training=p['training'],candidate_id=p['candidate_id'],
                         source_group_id=p['source_group_id'],time_s=track['times_s'][i],
                         measured_hz=track['measured_hz'][i],rf_hz=track['rf_hz'],receiver=track['receiver_id'])
                candidates[p['candidate_id']].append(row)
                if p['training']:
                    groups[p['source_group_id']].append(row)
        conflicts={g:rs for g,rs in groups.items() if len(rs)>1}
        duplicates={c:rs for c,rs in candidates.items() if sum(r['training'] for r in rs)>1}
        mixed={c:rs for c,rs in candidates.items() if any(r['training'] for r in rs) and any(not r['training'] for r in rs)}
        pairs=[]
        for group,rows in conflicts.items():
            for a,b in itertools.combinations(rows,2):
                assert a['rf_hz']==b['rf_hz'] and a['receiver']==b['receiver']
                period=1/4.4e-6
                delta=(a['measured_hz']-b['measured_hz'])*a['rf_hz']/11.2e9
                wrapped=abs((delta+period/2)%period-period/2)
                dt=abs(a['time_s']-b['time_s'])
                all_frequency_differences.append(wrapped);all_time_differences.append(dt)
                pairs.append(dict(source_group_id=group,left_track=a['track_id'],right_track=b['track_id'],
                                  same_candidate=a['candidate_id']==b['candidate_id'],
                                  wrapped_native_frequency_difference_hz=wrapped,time_difference_s=dt))
        edges=[(a,b) for a,b in itertools.combinations(support,2) if support[a]&support[b]]
        scans.append(dict(index=index,tracks=len(support),training_rows=sum(len(s) for s in support.values()),
                          shared_probe_groups=len(conflicts),rows_in_shared_probes=sum(map(len,conflicts.values())),
                          shared_probe_pairs=len(pairs),different_candidate_groups=sum(len({r['candidate_id'] for r in rows})>1 for rows in conflicts.values()),
                          exact_candidate_reuse_groups=len(duplicates),
                          exact_candidate_reuse_training_rows=sum(sum(r['training'] for r in rs) for rs in duplicates.values()),
                          exact_candidate_train_held_reuse_groups=len(mixed),
                          conflict_edges=len(edges),equal_training_support_edges=sum(support[a]==support[b] for a,b in edges),
                          subset_training_support_edges=sum(support[a]<support[b] or support[b]<support[a] for a,b in edges),
                          components=[c for c in components(support) if len(c)>1],pairs=pairs,
                          exact_candidate_reuse=duplicates,exact_candidate_train_held_reuse=mixed))
    keys=('tracks','training_rows','shared_probe_groups','rows_in_shared_probes','shared_probe_pairs',
          'different_candidate_groups','exact_candidate_reuse_groups','exact_candidate_reuse_training_rows',
          'exact_candidate_train_held_reuse_groups','conflict_edges','equal_training_support_edges','subset_training_support_edges')
    totals={k:sum(s[k] for s in scans) for k in keys}
    totals.update(median_wrapped_native_frequency_difference_hz=statistics.median(all_frequency_differences),
                  median_time_difference_s=statistics.median(all_time_differences),
                  pairs_with_wrapped_frequency_difference_below_1hz=sum(x<1 for x in all_frequency_differences),
                  maximum_component_tracks=max(len(c) for s in scans for c in s['components']))
    output=dict(schema='ds11-probe-versus-candidate-overlap/v1',reference_used=False,position_fits=0,
                totals=totals,scans=scans,sources=sources)
    with (HERE/'outcome.json').open('x') as stream:
        json.dump(output,stream,indent=2,allow_nan=False)
    print(json.dumps(totals,indent=2))


if __name__=='__main__':
    main()
