"""Enumerate and test all small nonoverlapping native recovery subsets per scan."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from itertools import combinations
import csv,hashlib,sys
from pathlib import Path
from debug_fast_graph_unassociated import read,write
from stress_joint_attachment import supervise


def nonoverlapping_subsets(rows):
    """Exact enumeration of this bounded cohort, with no satellite/error ranking."""
    if len(rows)>12:raise ValueError('exhaustive subset audit capped at twelve proposals per scan')
    rows=sorted(rows,key=lambda r:r['branch_id']);result=[]
    for n in range(1,len(rows)+1):
        for selected in combinations(rows,n):
            owned=set();valid=True
            for r in selected:
                ids=set(r['observation_ids'])
                if len(ids)!=len(r['observation_ids']):raise ValueError('duplicate native identity within a branch')
                if owned&ids:valid=False;break
                owned.update(ids)
            if valid:result.append(dict(branch_ids=[r['branch_id'] for r in selected],points=len(owned)))
    return result


def select_valid_subset(rows):
    """Maximum native coverage among fully passing tested subsets; no GPS field."""
    valid=[r for r in rows if r['paired_valid']]
    return min(valid,key=lambda r:(-r['points'],len(r['branch_ids']),tuple(r['branch_ids']))) if valid else None


def run(args):
    rows=list(csv.DictReader(args.annotations.open()));eligible=read(args.study/'omitted-branch-annotations-v1/protocol.json')['all_eligible']
    for cohort in args.extra_cohort:eligible+=read(cohort/'protocol.json')['all_eligible']
    lookup={j['branch']['branch_id']:j for j in eligible};groups={}
    for r in rows:
        if r['status']!='conditionally_supported_identity':continue
        from native_predictive_branch import validated_native_source
        validated_native_source(Path(r['source']))
        j=lookup[r['branch_id']]
        groups.setdefault(j['job']['job_id'],[]).append(dict(branch_id=r['branch_id'],observation_ids=j['branch']['observation_ids'],
            validation=r['source'],job=j['job'],individual_status=r['inclusion_status']))
    jobs=[];inventory=[]
    for jid,rr in sorted(groups.items()):
        for subset in nonoverlapping_subsets(rr):
            bid=hashlib.sha256(('\n'.join(subset['branch_ids'])).encode()).hexdigest()[:20]
            row=dict(subset,subset_id=bid,job_id=jid,job=rr[0]['job'],validation=[r['validation'] for r in rr if r['branch_id'] in subset['branch_ids']])
            if len(subset['branch_ids'])>1 and args.reuse_joint:
                path=args.reuse_joint/bid/'combined.json';receipt=args.reuse_joint/(bid+'-terminal.json')
                if path.exists() and receipt.exists() and read(receipt)['status']=='complete':
                    old=read(path);old_ids=sorted(e['component'].split('-NATIVE-')[-1] for e in old['target_entries'])
                    if old_ids!=sorted(subset['branch_ids']):raise ValueError('joint reuse membership mismatch')
                    if old.get('noise_policy','original')!='original' or any(old.get(k,False) for k in ['target_orbit_prior','shared_satellite_refresh','orphan_phase_refresh']):raise ValueError('joint reuse model changed')
                    row['reuse_source']=str(path);row['reuse_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            inventory.append(row)
            if len(subset['branch_ids'])>1:jobs.append(row)
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(jobs=jobs,all_subsets=inventory,scans=len(groups),
        candidate_annotations=len(rows),supported_identities=sum(len(v) for v in groups.values()),
        extra_cohorts=[str(p) for p in args.extra_cohort],reuse_joint=str(args.reuse_joint) if args.reuse_joint else None,
        annotations_source=str(args.annotations),annotations_sha256=hashlib.sha256(args.annotations.read_bytes()).hexdigest(),
        selection='Every nonoverlapping subset of all supported identities; include individually rejected branches',
        singleton_receipts='Reuse frozen individually tested controls and trials; no numerical model change',
        workers=8,seconds_per_case=600,GPS_used=False,matched_c_arms=True))
    def work(j):
        sid=j['subset_id'];cmd=[sys.executable,str(Path(__file__).with_name('include_predictive_annotations.py')),
            '--inventory',j['job']['inventory'],'--native-from-validation','--validation',*j['validation'],
            '--joint-only','--output',str(args.output/sid)]
        execution=dict(status='reused',reason='Unchanged previously completed joint subset',source=j['reuse_source'],sha256=j['reuse_sha256']) if j.get('reuse_source') else supervise(cmd,args.output/(sid+'.log'),600)
        r=dict(job=j,command=cmd,**execution);write(args.output/(sid+'-terminal.json'),r)
        return j['job']['label'],len(j['branch_ids']),r['status']
    print('scans',len(groups),'subsets',len(inventory),'new joint fits',sum(not j.get('reuse_source') for j in jobs),flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['study','annotations','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--extra-cohort',type=Path,nargs='*',default=[]);p.add_argument('--reuse-joint',type=Path)
    run(p.parse_args())
