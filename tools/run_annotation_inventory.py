"""Frozen, resumable coverage ledger for every large unassociated graph track."""
import argparse
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


def run(args):
    protocol=read(args.output/'protocol.json');attempt=args.output/f'attempt-{len(list(args.output.glob("attempt-*")))+1}'
    attempt.mkdir();jobs=[]
    for r in protocol['rows']:
        if r['state']!='queued' or (args.output/r['track_id']/'result.json').exists():continue
        # Any prior terminal is visible and needs diagnosis before another try.
        if list(args.output.glob('attempt-*/'+r['track_id']+'-terminal.json')):continue
        jobs.append(r)
        if len(jobs)>=args.limit:break
    write(attempt/'selected.json',jobs)
    def work(r):
        cmd=[sys.executable,str(Path(__file__).with_name('annotate_track_predictively.py')),
             '--inventory',r['inventory'],'--track',r['track_id'],'--output',str(args.output/r['track_id'])]
        result=dict(track_id=r['track_id'],label=r['label'],**supervise(cmd,attempt/(r['track_id']+'.log'),600))
        write(attempt/(r['track_id']+'-terminal.json'),result);return result
    results=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):
            r=f.result();results.append(r);print(r,flush=True)
    write(attempt/'execution.json',results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['freeze','run'])
    for key in ('study','inventory','diagnostics','output'):p.add_argument('--'+key,type=Path,required=key=='output')
    p.add_argument('--limit',type=int,default=16);a=p.parse_args();freeze(a) if a.mode=='freeze' else run(a)
