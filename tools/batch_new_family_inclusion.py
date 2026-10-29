"""Bounded, evidence-selected new-family validation and position trials."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import sys
from debug_fast_graph_unassociated import read,write
from stress_joint_attachment import supervise


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);queue=args.study/'systematic-annotation-v1';groups={}
    tested={(read(p)['job']['job_id'],read(p)['targets'][0]['norad']) for p in args.study.glob('new-family-inclusion-*-v1/protocol.json')}
    for row in read(queue/'protocol.json')['rows']:
        path=queue/row['track_id']/'result.json'
        if not path.exists():continue
        r=read(path);a=r.get('annotation',{})
        if r.get('inclusion_mode')!='predictive_only' or a.get('status')!='conditionally_supported_identity':continue
        norad=a['norad'];key=(row['job_id'],norad)
        if key in tested:continue
        if not all(q['arms']['c0']['prior']['kind']=='new_family_causal_phase_mixture' for f in r['folds'] for q in f['proposals'] if q['norad']==norad):continue
        group=groups.setdefault(key,dict(job_id=row['job_id'],label=row['label'],norad=norad,inventory=row['inventory'],tracks=[],points=0,primary=False))
        group['tracks'].append(row);group['points']+=row['points'];group['primary']|=('DS24' in row['scopes'] or 'session research' in row['scopes'])
    selected=sorted(groups.values(),key=lambda r:(not r['primary'],-r['points'],r['job_id'],r['norad']))[:args.limit]
    write(args.output/'protocol.json',dict(jobs=selected,workers=4,seconds_per_stage=600,selection='DS24/session then descending points, one joint phase per new family',GPS_used=False))
    def work(job):
        folder=args.output/(job['job_id']+'-'+str(job['norad']));folder.mkdir();validations=[];stages=[]
        for row in job['tracks']:
            target=folder/row['track_id'];cmd=[sys.executable,str(Path(__file__).with_name('annotate_predictive_only.py')),
                '--inventory',job['inventory'],'--track',row['track_id'],'--output',str(target),'--uncalibrated-phase-mixture']
            stage=supervise(cmd,folder/(row['track_id']+'.log'),600);stages.append(stage)
            if stage['status']!='complete':return dict(job=job,stages=stages,status='annotation_execution_failure')
            a=read(target/'result.json')['annotation']
            if a['status']!='conditionally_supported_identity' or a['norad']!=job['norad']:
                return dict(job=job,stages=stages,status='identity_not_preserved',annotation=a)
            validations.append(str(target))
        cmd=[sys.executable,str(Path(__file__).with_name('include_new_predictive_family.py')),'--inventory',job['inventory'],
            '--validation',*validations,'--output',str(folder/'inclusion')]
        stage=supervise(cmd,folder/'inclusion.log',600);stages.append(stage)
        return dict(job=job,stages=stages,status=stage['status'])
    results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(work,j) for j in selected]):
            r=f.result();results.append(r);job=r['job'];write(args.output/(job['job_id']+'-'+str(job['norad'])+'-terminal.json'),r)
            print(job['label'],job['norad'],r['status'],flush=True)
    write(args.output/'execution.json',results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int,default=8);run(p.parse_args())
