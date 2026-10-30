"""Bounded position tests for supported curves missing from saved trial links."""
import argparse,hashlib,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from debug_fast_graph_unassociated import read,write
from run_predictive_queue_inclusions import require_predictive_result
from run_supported_graph_inclusions import supported_jobs
from test_predictive_graph_transfer import shared_family_route
from stress_joint_attachment import supervise
from leo.analysis.research.grouped_prediction import identity_consensus
from annotation_partition_plan import require_distinct_annotation


def pending_subset(original,pending):
    known={r['track_id']:r for r in original}
    if len(known)!=len(original) or len({r['track_id'] for r in pending})!=len(pending):
        raise ValueError('duplicate curve in pending manifest')
    if any(known.get(r['track_id'])!=r for r in pending):
        raise ValueError('pending manifest is not an unchanged subset of the source registry')
    return pending


def run(args):
    if not 1<=args.limit<=16 or not 1<=args.workers<=8:raise ValueError('bounded limit 1..16 and workers 1..8 required')
    source=args.registry/'pending_candidates.json';candidates=read(source)
    pending=getattr(args,'pending',None)
    if pending:candidates=pending_subset(candidates,read(pending))
    jobs=sorted(candidates,key=lambda r:(-r['points'],r['track_id']))[:args.limit]
    results={j['track_id']:read(Path(j['validation'])/'result.json') for j in jobs}
    for j in jobs:
        r=results[j['track_id']];require_predictive_result(r)
        if r['track_id']!=j['track_id']:raise ValueError('validation identity mismatch')
    eligible=supported_jobs(jobs,results,require_engine_member=False)
    if len(eligible)!=len(jobs):raise ValueError('frozen pending list contains an unsupported identity')
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    paths=[source,args.registry/'summary.json']+[Path(j['validation'])/n for j in jobs for n in ('protocol.json','result.json')]
    if pending:paths.append(pending)
    write(out/'protocol.json',dict(jobs=eligible,source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        selection='largest curves with supported predictive identity and no full predictive trial in reconciled source registry',
        omitted_engine_curves_eligible=True,workers=args.workers,seconds_per_stage=600,
        refreshed_distinct_annotation_required=True,annotation_partitions='three distinct timestamp-selected random scanwide 12-second blocks with 2-second guards',
        matched_c_arms=True,GPS_used=False,future_TLE=False,new_family_phase_step_s=.025,no_production_change=True))
    def work(job):
        tid=job['track_id'];folder=out/tid;folder.mkdir();validation=Path(job['validation'])
        stages=[];shared=None
        def stage(name,script,options):
            cmd=[sys.executable,str(Path(__file__).with_name(script)),*options]
            r=dict(stage=name,command=cmd,**supervise(cmd,folder/(name+'.log'),600))
            write(folder/(name+'-terminal.json'),r);stages.append(r);return r['status']=='complete'
        ok=stage('annotation','annotate_predictive_only.py',
            ['--inventory',job['inventory'],'--track',tid,'--output',str(folder/'annotation'),
             '--predictive-member','--uncalibrated-phase-mixture','--distinct-partitions'])
        vote=None
        if ok:
            refreshed=read(folder/'annotation/result.json');require_predictive_result(refreshed)
            vote=identity_consensus(refreshed['folds'],score_name='conditional_target')
        if not ok or vote['status']!='conditionally_supported_identity':
            result=dict(job=job,shared_family=None,stages=stages,status='annotation_execution_failed' if not ok else 'refreshed_identity_not_supported',annotation=vote)
            write(out/(tid+'-terminal.json'),result);print(job['label'],result['status'],flush=True);return result
        validation=folder/'annotation';shared=shared_family_route(refreshed['folds'],vote['norad'])
        require_distinct_annotation(refreshed,read(validation/'protocol.json'))
        extra=['--predictive-member'] if shared else ['--uncalibrated-label','--phase-step','0.025']
        ok=stage('inclusion','include_predictive_annotations.py' if shared else 'include_new_predictive_family.py',
            ['--inventory',job['inventory'],'--validation',str(validation),'--output',str(folder/'trial'),*extra])
        if ok:ok=stage('replay','audit_shared_predictive_inclusion.py' if shared else 'audit_predictive_family_inclusion.py',
            ['--study',str(args.study),'--trial',str(folder/'trial'),'--output',str(folder/'trial/exact_owner_replay.json')])
        status='execution_failed'
        if ok:
            control=read(folder/'trial/control.json');trial=read(folder/'trial'/('target_0.json' if shared else 'new_family.json'))
            replay=read(folder/'trial/exact_owner_replay.json')
            status='RF_verified_research_candidate' if control['paired_valid'] and trial['paired_valid'] and replay['all_verified'] else 'inclusion_rejected'
        result=dict(job=job,shared_family=shared,stages=stages,status=status,annotation=vote)
        write(out/(tid+'-terminal.json'),result);print(job['label'],status,flush=True);return result
    with ThreadPoolExecutor(max_workers=args.workers) as pool:execution=list(pool.map(work,eligible))
    write(out/'execution.json',execution)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('study','registry','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--limit',type=int,default=8);p.add_argument('--workers',type=int,default=4)
    p.add_argument('--pending',type=Path,help='Previously published remaining manifest; must match an unchanged subset of the registry')
    run(p.parse_args())
