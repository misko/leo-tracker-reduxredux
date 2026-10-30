"""Frozen, resumable coverage ledger for every large unassociated graph track."""
import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import sys
from debug_fast_graph_unassociated import read,write
from stress_joint_attachment import supervise


def freeze(args):
    args.output.mkdir(parents=True,exist_ok=False);rows=[]
    known={}
    for p in args.study.glob('predictive-annotation-*-v1/result.json'):
        r=read(p);known[r['track_id']]=str(p.parent)
    for job in read(args.inventory/'protocol.json')['jobs']:
        inv=read(args.inventory/job['job_id']/'inventory.json');diag=read(args.diagnostics/job['job_id']/'result.json')
        lookup={r['track_id']:r for r in diag['tracks']}
        large={r['track_id']:r for r in inv['tracks'] if r['current_large']}
        for track_id,r in large.items():
            t=lookup[track_id];prior=known.get(track_id)
            rows.append(dict(track_id=track_id,job_id=job['job_id'],label=job['label'],scopes=job['scopes'],
                component=r['component'],track_index=r['track_index'],points=len(r['observation_ids']),
                span_s=r['current']['span_s'],engine_member=t['engine_member'],
                inventory=str(args.inventory/job['job_id']/'inventory.json'),known_validation=prior,
                state='evaluated' if prior else 'queued' if t['engine_member'] else 'needs_predictive_only_model'))
    rows.sort(key=lambda r:('DS24' not in r['scopes'] and 'session research' not in r['scopes'],-r['points'],r['track_id']))
    write(args.output/'protocol.json',dict(rows=rows,seeds=[20261029,94721,4081],candidate_limit=3,workers=8,
        seconds_per_case=600,scope='every large track in either c arm; no silent exclusions',
        ordering='DS24 and manual research first, then remaining recordings; point count descending',
        position_inclusion_requires_separate_validation=True))
    print('all tracks',len(rows),'existing',sum(r['state']=='evaluated' for r in rows),'queued',sum(r['state']=='queued' for r in rows),
          'predictive-only required',sum(r['state']=='needs_predictive_only_model' for r in rows),flush=True)


def pending_jobs(protocol,output,limit,predictive_only=False,scope=None,remaining_ids=None):
    if limit<1:raise ValueError('positive job limit required')
    # A selected attempt can still be queued or running without a terminal
    # receipt. Preserve every claim; an incomplete attempt needs diagnosis.
    claimed={r['track_id'] for p in output.glob('attempt-*/selected.json') for r in read(p)}
    jobs=[]
    for r in protocol['rows']:
        if remaining_ids is not None and r['track_id'] not in remaining_ids:continue
        if scope is not None and scope not in r.get('scopes',[]):continue
        eligible='needs_predictive_only_model' if predictive_only else 'queued'
        if r['state']!=eligible or r['track_id'] in claimed or (output/r['track_id']).exists():continue
        if list(output.glob('attempt-*/'+r['track_id']+'-terminal.json')):continue
        jobs.append(r)
        if len(jobs)>=limit:break
    return jobs


def annotation_command(row,output,*,predictive_only=False,predictive_member=False,distinct_partitions=False,inactive_fragment=False,shifted_block_origin=False):
    if predictive_only and predictive_member:
        raise ValueError('choose omitted-track or graph-member predictive queue')
    if inactive_fragment and not predictive_member:raise ValueError('inactive fragments require the graph-member predictive queue')
    if shifted_block_origin and not(distinct_partitions and (predictive_only or predictive_member)):
        raise ValueError('shifted origins require distinct predictive-only validation')
    script='annotate_predictive_only.py' if predictive_only or predictive_member else 'annotate_track_predictively.py'
    cmd=[sys.executable,str(Path(__file__).with_name(script)),
         '--inventory',row['inventory'],'--track',row['track_id'],'--output',str(output/row['track_id'])]
    if predictive_member:cmd+=['--inactive-fragment' if inactive_fragment else '--predictive-member','--uncalibrated-phase-mixture']
    if distinct_partitions:cmd.append('--distinct-partitions')
    if shifted_block_origin:cmd.append('--shifted-block-origin')
    return cmd


def run(args):
    if args.workers<1:raise ValueError('positive worker count required')
    if args.predictive_only and args.predictive_member:raise ValueError('choose omitted-track or graph-member predictive queue')
    if args.split_inactive_fragments and not args.predictive_member:raise ValueError('fragment routing requires predictive-member mode')
    if getattr(args,'shifted_block_origin',False) and not(args.distinct_partitions and (args.predictive_only or args.predictive_member)):
        raise ValueError('shifted origins require distinct predictive-only validation')
    protocol=read(args.output/'protocol.json');attempt=args.output/f'attempt-{len(list(args.output.glob("attempt-*")))+1}'
    remaining_path=getattr(args,'remaining_candidates',None);remaining_ids=None;remaining_receipt=None
    if remaining_path:
        remaining_ids={r['track_id'] for r in read(remaining_path)}
        if not remaining_ids<={r['track_id'] for r in protocol['rows']}:raise ValueError('remaining candidates leave the frozen queue')
        remaining_receipt=dict(path=str(remaining_path),sha256=hashlib.sha256(remaining_path.read_bytes()).hexdigest())
    jobs=pending_jobs(protocol,args.output,args.limit,args.predictive_only,args.scope,remaining_ids);attempt.mkdir()
    write(attempt/'selected.json',jobs)
    write(attempt/'protocol.json',dict(workers=args.workers,seconds_per_case=600,predictive_only=args.predictive_only,
        predictive_member=args.predictive_member,
        shifted_block_origin=getattr(args,'shifted_block_origin',False),
        remaining_candidates_source=remaining_receipt,
        split_inactive_fragments=args.split_inactive_fragments,
        likelihood_role='predictive_only' if args.predictive_only or args.predictive_member else 'calibration_participating',
        selected_tracks=len(jobs),preserves_existing_attempt_claims=True,scope=args.scope,
        distinct_partitions=args.distinct_partitions,partition_policy='timestamp-only distinct schedule' if args.distinct_partitions else 'original three seeds'))
    def work(r):
        fragment=False
        if args.split_inactive_fragments:
            inventory=read(Path(r['inventory']))
            target=next(t for t in inventory['tracks'] if t['track_id']==r['track_id'])
            fragment=not target['current']['wholly_unassociated']
        cmd=annotation_command(r,args.output,predictive_only=args.predictive_only,
            predictive_member=args.predictive_member,distinct_partitions=args.distinct_partitions,inactive_fragment=fragment,
            shifted_block_origin=getattr(args,'shifted_block_origin',False))
        result=dict(track_id=r['track_id'],label=r['label'],command=cmd,inactive_fragment=fragment,**supervise(cmd,attempt/(r['track_id']+'.log'),600))
        write(attempt/(r['track_id']+'-terminal.json'),result);return result
    results=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):
            r=f.result();results.append(r);print(r['label'],r['track_id'],r['status'],round(r['seconds'],2),flush=True)
    write(attempt/'execution.json',results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['freeze','run'])
    for key in ('study','inventory','diagnostics','output'):p.add_argument('--'+key,type=Path,required=key=='output')
    p.add_argument('--limit',type=int,default=16);p.add_argument('--predictive-only',action='store_true')
    p.add_argument('--predictive-member',action='store_true',help='Assess pending graph curves in their intended predictive-only inclusion role')
    p.add_argument('--split-inactive-fragments',action='store_true',help='Route partial graph curves to their disjoint unused observations')
    p.add_argument('--workers',type=int,default=8)
    p.add_argument('--scope',help='Process pending tracks in this recorded scope without altering the full queue')
    p.add_argument('--distinct-partitions',action='store_true')
    p.add_argument('--shifted-block-origin',action='store_true',help='Opt-in seeded block origins with unchanged guards and support requirements')
    p.add_argument('--remaining-candidates',type=Path,help='Reconciled remaining IDs, excluding work completed through other annotation queues')
    a=p.parse_args();freeze(a) if a.mode=='freeze' else run(a)
