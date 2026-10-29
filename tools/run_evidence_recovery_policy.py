"""One bounded maximum-coverage joint trial per scan, preserving prior native IDs."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import csv,hashlib,sys
from pathlib import Path
from debug_fast_graph_unassociated import read,write
from run_native_joint_subsets import nonoverlapping_subsets
from stress_joint_attachment import supervise


def choose_preserving_subset(rows,old_owners):
    eligible=[];conflicts=[]
    for row in rows:
        if any(o in old_owners and old_owners[o]!=row['norad'] for o in row['observation_ids']):
            conflicts.append(row['branch_id'])
        else:eligible.append(row)
    lookup={r['branch_id']:r for r in eligible};feasible=[]
    for subset in nonoverlapping_subsets(eligible):
        ids={o for bid in subset['branch_ids'] for o in lookup[bid]['observation_ids']}
        if set(old_owners)<=ids:feasible.append(subset)
    chosen=min(feasible,key=lambda r:(-r['points'],len(r['branch_ids']),tuple(r['branch_ids']))) if feasible else None
    return chosen,conflicts


def run(args):
    previous=list(csv.DictReader(args.previous_policy.open()));old_annotations={r['branch_id']:r for r in csv.DictReader(args.previous_annotations.open())}
    new_annotations={r['branch_id']:r for r in csv.DictReader((args.annotations/'annotations.csv').open())}
    new_jobs=read(args.inclusions/'protocol.json')['jobs'];by_scan={};sources={}
    def load(path):
        path=Path(path);sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return read(path)
    for job in new_jobs:
        bid=job['branch_id'];terminal=load(args.inclusions/(bid+'-terminal.json'))
        path=args.inclusions/bid/'target_0.json'
        if terminal['status']=='complete':
            r=load(path)
            if r['paired_valid']:by_scan.setdefault(job['scan'],[]).append((job,r,path))
    choices=[];jobs=[]
    for old in previous:
        scan=old['scan'];fresh=by_scan.get(scan,[])
        if not fresh:continue
        old_branches=[b for b in old['branch_ids'].split(';') if b];old_owners={};rows=[]
        if old_branches:
            prior=load(Path(old['source']))
            for entry in prior['target_entries']:
                for oid in entry['observation_ids']:
                    if oid in old_owners and old_owners[oid]!=entry['norad']:raise ValueError('old policy has conflicting owners')
                    old_owners[oid]=entry['norad']
            for bid in old_branches:
                validation=Path(old_annotations[bid]['source']);pr=load(validation/'protocol.json');a=load(validation/'result.json')['annotation']
                rows.append(dict(branch_id=bid,observation_ids=pr['target']['observation_ids'],norad=a['norad'],validation=str(validation)))
        for job,r,path in fresh:
            entry=r['target_entries'][0];bid=job['branch_id']
            rows.append(dict(branch_id=bid,observation_ids=entry['observation_ids'],norad=entry['norad'],validation=new_annotations[bid]['source'],singleton_source=str(path)))
        chosen,conflicts=choose_preserving_subset(rows,old_owners)
        choice=dict(scan=scan,old_policy=old,old_native_points=len(old_owners),candidate_rows=rows,
                    ownership_conflicts=conflicts,chosen=chosen,changed=False)
        if chosen and chosen['points']>len(old_owners):
            lookup={r['branch_id']:r for r in rows};selected=[lookup[bid] for bid in chosen['branch_ids']]
            sid=hashlib.sha256(('\n'.join(chosen['branch_ids'])).encode()).hexdigest()[:20]
            choice.update(changed=True,subset_id=sid,validation=[r['validation'] for r in selected],inventory=fresh[0][0]['inventory'])
            if len(selected)==1:
                if 'singleton_source' not in selected[0]:raise ValueError('changed singleton lacks completed trial')
                choice['reuse_source']=selected[0]['singleton_source']
            jobs.append(choice)
        choices.append(choice)
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(jobs=jobs,choices=choices,source_sha256=sources,previous_policy=str(args.previous_policy),
        previous_policy_sha256=hashlib.sha256(args.previous_policy.read_bytes()).hexdigest(),workers=4,seconds_per_case=600,
        selection='Largest nonoverlapping subset of individually passing new proposals plus prior selected branches; preserve all prior native IDs and satellite owners',
        failure_fallback='retain previous policy; untested smaller subsets remain unresolved',
        maximum_one_new_joint_configuration_per_scan=True,GPS_used=False,no_production_change=True))
    def work(job):
        sid=job['subset_id'];cmd=[sys.executable,str(Path(__file__).with_name('include_predictive_annotations.py')),
            '--inventory',job['inventory'],'--native-from-validation','--validation',*job['validation'],'--joint-only','--output',str(args.output/sid)]
        if job.get('reuse_source'):
            path=Path(job['reuse_source']);execution=dict(status='reused',source=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        else:execution=supervise(cmd,args.output/(sid+'.log'),600)
        result=dict(scan=job['scan'],subset_id=sid,command=cmd,**execution);write(args.output/(sid+'-terminal.json'),result)
        return result
    print('changed scans',len(jobs),'new joint fits',sum(not j.get('reuse_source') for j in jobs),flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['previous-policy','previous-annotations','annotations','inclusions','output']:p.add_argument('--'+k,type=Path,required=True)
    run(p.parse_args())
