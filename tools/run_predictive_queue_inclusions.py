"""Reuse completed predictive annotations in bounded matched position trials."""
import argparse,hashlib,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from debug_fast_graph_unassociated import read,write
from run_supported_graph_inclusions import completed_rows,supported_jobs
from test_predictive_graph_transfer import shared_family_route
from stress_joint_attachment import supervise
from annotation_partition_plan import require_distinct_annotation


def require_predictive_result(result):
    if result.get('inclusion_mode')!='predictive_only' or result.get('identity_score_name')!='conditional_target':
        raise ValueError('position routing requires an annotation in the predictive-only likelihood role')


def reassessment_rows(root):
    """Require a terminal separate reassessment, never substitute old partial trials."""
    execution=read(root/'execution.json')
    jobs=read(root/'protocol.json')['jobs'];byid={r['job']['track_id']:r for r in execution}
    if len(byid)!=len(execution) or set(byid)!={j['track_id'] for j in jobs}:
        raise ValueError('reassessment execution does not match its frozen jobs')
    rows=[];excluded=[];sources=[root/'protocol.json',root/'execution.json']
    for job in jobs:
        path=root/(job['track_id']+'-terminal.json');receipt=read(path);sources.append(path)
        if receipt['status']!=byid[job['track_id']]['status']:
            raise ValueError('inconsistent reassessment terminal receipt')
        if receipt['status']=='complete':rows.append(job)
        else:excluded.append(dict(track_id=job['track_id'],label=job['label'],execution=receipt['status']))
    return rows,excluded,sources


def run(args):
    if not 1<=args.workers<=8:raise ValueError('one to eight workers required')
    if args.reassessment:
        q=args.reassessment;rows,excluded,receipts=reassessment_rows(q)
    else:
        q=args.study/'systematic-annotation-v1';rows,excluded,receipts=completed_rows(q,args.attempts)
    if len(rows)+len(excluded)>128:raise ValueError('at most 128 frozen annotations per bounded iteration')
    results={r['track_id']:read(q/r['track_id']/'result.json') for r in rows}
    for r in results.values():require_predictive_result(r)
    # Predictive-only evidence may come from curves omitted by the calibration
    # engine. Identity/ownership checks, not engine membership, authorize a trial.
    jobs=supported_jobs(rows,results,require_engine_member=False)
    for job in jobs:
        if not job['engine_member']:
            require_distinct_annotation(results[job['track_id']],read(q/job['track_id']/'protocol.json'))
    if len(jobs)>32:raise ValueError('at most 32 position cases per bounded iteration')
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    sources=receipts+[q/j['track_id']/name for j in jobs for name in ('result.json','protocol.json')]
    write(out/'protocol.json',dict(jobs=jobs,attempts=args.attempts,reassessment_source=str(args.reassessment) if args.reassessment else None,excluded_annotation_executions=excluded,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        workers=args.workers,seconds_per_stage=600,selection='all supported predictive-role identities in specified complete attempts; no GPS selection',
        omitted_engine_curves_eligible=True,
        omitted_engine_curves_require_distinct_holdouts=True,
        matched_c_arms=True,causal_only=True,no_production_change=True))
    def work(job):
        folder=out/job['track_id'];folder.mkdir();validation=q/job['track_id'];r=results[job['track_id']]
        shared=shared_family_route(r['folds'],job['annotation']['norad']);stages=[]
        def stage(name,script,options):
            cmd=[sys.executable,str(Path(__file__).with_name(script)),*options]
            result=dict(stage=name,command=cmd,**supervise(cmd,folder/(name+'.log'),600))
            write(folder/(name+'-terminal.json'),result);stages.append(result);return result['status']=='complete'
        ok=stage('inclusion','include_predictive_annotations.py' if shared else 'include_new_predictive_family.py',
            ['--inventory',job['inventory'],'--validation',str(validation),'--output',str(folder/'trial'),
             '--predictive-member' if shared else '--uncalibrated-label'])
        if ok:ok=stage('replay','audit_shared_predictive_inclusion.py' if shared else 'audit_predictive_family_inclusion.py',
            ['--study',str(args.study),'--trial',str(folder/'trial'),'--output',str(folder/'trial/exact_owner_replay.json')])
        result=dict(job=job,shared_family=shared,stages=stages,status='complete' if ok else 'execution_failed')
        write(folder/'execution.json',result);print(job['label'],result['status'],flush=True);return result
    with ThreadPoolExecutor(max_workers=args.workers) as pool:execution=list(pool.map(work,jobs))
    write(out/'execution.json',execution)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','output'):p.add_argument('--'+name,type=Path,required=True)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--attempts',nargs='+');source.add_argument('--reassessment',type=Path)
    p.add_argument('--workers',type=int,default=4)
    run(p.parse_args())
