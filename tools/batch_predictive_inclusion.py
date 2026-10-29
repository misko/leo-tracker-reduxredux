"""Bounded DS24 inclusion checks selected by predictive evidence, never GPS."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import sys
from debug_fast_graph_unassociated import read,write
from stress_joint_attachment import supervise


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);jobs={};already=set()
    for folder in args.study.glob('predictive-only-inclusion-*-v1'):
        if (folder/'protocol.json').exists():already.add(read(folder/'protocol.json')['job']['job_id'])
    for row in read(args.queue/'protocol.json')['rows']:
        path=args.queue/row['track_id']/'result.json'
        if 'DS24' not in row['scopes'] or row['job_id'] in already or not path.exists():continue
        result=read(path);annotation=result.get('annotation',{})
        if result.get('inclusion_mode')!='predictive_only' or annotation.get('status')!='conditionally_supported_identity':continue
        winners=[next(q for q in f['proposals'] if q['norad']==annotation['norad']) for f in result['folds']]
        if not all(q['arms']['c0']['prior']['kind']=='existing_shared_posterior' for q in winners):continue
        job=jobs.setdefault(row['job_id'],dict(job_id=row['job_id'],label=row['label'],inventory=row['inventory'],validations=[],points=0))
        job['validations'].append(str(path.parent));job['points']+=row['points']
    selected=sorted(jobs.values(),key=lambda r:(-r['points'],r['job_id']))[:args.limit]
    write(args.output/'protocol.json',dict(jobs=selected,scope='DS24; conditionally supported existing family; previously tested scans excluded',
        ordering='target point count descending',workers=4,seconds_per_case=600,GPS_used_for_selection=False))
    def work(job):
        cmd=[sys.executable,str(Path(__file__).with_name('include_predictive_annotations.py')),
             '--inventory',job['inventory'],'--output',str(args.output/job['job_id']),'--validation',*job['validations']]
        r=dict(job_id=job['job_id'],label=job['label'],**supervise(cmd,args.output/(job['job_id']+'.log'),600))
        write(args.output/(job['job_id']+'-terminal.json'),r);return r
    results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(work,j) for j in selected]):
            r=f.result();results.append(r);print(r,flush=True)
    write(args.output/'execution.json',results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['study','queue','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--limit',type=int,default=8);run(p.parse_args())
