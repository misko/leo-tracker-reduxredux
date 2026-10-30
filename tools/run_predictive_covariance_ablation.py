"""Matched 2x2 diagnostic removal of orbital/receiver predictive covariance."""
import argparse
import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from debug_fast_graph_unassociated import read, write
from stress_joint_attachment import supervise


def run(args):
    source = read(args.source/'protocol.json'); validation = source['validation']
    phase_step=source['phase_step_s'] if args.phase_step is None else args.phase_step
    if phase_step not in (.1,.05,.025):raise ValueError('predeclared phase refinement required')
    inventory = args.study/'all-large-track-recovery'/source['job']['job_id']/'inventory.json'
    args.output.mkdir(parents=True,exist_ok=False)
    jobs = [dict(name=name,orbit=o,receiver=r) for name,o,r in
            [('both',True,True),('orbit_only',True,False),('receiver_only',False,True),('neither',False,False)]]
    write(args.output/'protocol.json',dict(jobs=jobs,source=str(args.source),inventory=str(inventory),validation=validation,
        source_sha256=hashlib.sha256((args.source/'protocol.json').read_bytes()).hexdigest(),
        workers=4,seconds_per_stage=600,phase_step_s=phase_step,GPS_used=False,future_TLE=False,c0_vs_fitted_c=True,
        same_target_ids_aliases_noise_phase_priors_optimizer_and_budgets=True,
        target_calibrates_receiver=False,diagnostic_only=True,no_production_change=True))
    def work(job):
        root=args.output/job['name'];stages=[]
        cmd=[sys.executable,str(Path(__file__).with_name('include_new_predictive_family.py')),
             '--inventory',str(inventory),'--validation',*validation,'--output',str(root),
             '--phase-step',str(phase_step)]
        if source.get('uncalibrated_label'):cmd.append('--uncalibrated-label')
        if not job['orbit']:cmd.append('--omit-orbit-uncertainty')
        if not job['receiver']:cmd.append('--omit-receiver-uncertainty')
        r=dict(stage='inclusion',command=cmd,**supervise(cmd,args.output/(job['name']+'.log'),600));stages.append(r)
        if r['status']=='complete':
            cmd=[sys.executable,str(Path(__file__).with_name('audit_predictive_family_inclusion.py')),
                 '--study',str(args.study),'--trial',str(root),'--output',str(root/'exact_owner_replay.json')]
            stages.append(dict(stage='replay',command=cmd,**supervise(cmd,args.output/(job['name']+'-replay.log'),600)))
        result=dict(job=job,stages=stages,status=stages[-1]['status'])
        write(args.output/(job['name']+'-terminal.json'),result)
        return result
    results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):
            r=f.result();results.append(r);print(r['job']['name'],r['status'],flush=True)
    write(args.output/'execution.json',results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('study','source','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--phase-step',type=float)
    run(p.parse_args())
