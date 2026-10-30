"""Matched Powell retries selected by numerical failure, never position error."""
import argparse,hashlib,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from debug_fast_graph_unassociated import read,write
from algo02_scan import pair_passes
from stress_joint_attachment import supervise
from run_reconciled_predictive_inclusions import require_distinct_annotation


def numerical_only(control,addition,replay):
    pairs=(control['arms'],addition['arms'])
    return bool(replay.get('all_verified') and
        not (control['paired_valid'] and addition['paired_valid']) and
        all(pair_passes(pair,include_linear=True) for pair in pairs) and
        all(v['lost_points']==0 for pair in pairs for v in pair.values()) and
        any(not v['history'][-1]['success'] for pair in pairs for v in pair.values()) and
        all(v['phase_resolution_audit']['local_agreement'] and v['family']['phase_boundary_mass']<.01
            for v in addition['arms'].values()))


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);jobs=[];hashes={}
    for row in read(args.trials/'execution.json'):
        if row['shared_family'] or row['status']!='inclusion_rejected':continue
        j=row['job'];root=args.trials/j['track_id'];trial=root/'trial';paths=[trial/n for n in ('control.json','new_family.json','exact_owner_replay.json')]
        c,a,replay=[read(p) for p in paths]
        if not numerical_only(c,a,replay):continue
        validation=root/'annotation';require_distinct_annotation(read(validation/'result.json'),read(validation/'protocol.json'))
        jobs.append(dict(job=j,source_trial=str(trial),validation=str(validation)))
        for p in paths:hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    if len(jobs)>8:raise ValueError('at most eight numerical followups per bounded iteration')
    write(out/'protocol.json',dict(jobs=jobs,source_hashes=hashes,
        selection='all rejected new-family trials passing RF, exact replay, phase quadrature and ownership but failing optimizer completion',
        optimizer='Powell for matched control and addition, both c arms',workers=3,seconds_per_stage=600,
        phase_step_s=.025,phase_rounds=5,maxiter=48,maxfev=240,GPS_used=False,future_TLE=False,no_physical_gate_relaxation=True))
    def work(job):
        j=job['job'];folder=out/j['track_id'];folder.mkdir();stages=[]
        def stage(name,script,options):
            cmd=[sys.executable,str(Path(__file__).with_name(script)),*options]
            r=dict(stage=name,command=cmd,**supervise(cmd,folder/(name+'.log'),600))
            write(folder/(name+'-terminal.json'),r);stages.append(r);return r['status']=='complete'
        ok=stage('inclusion','include_new_predictive_family.py',['--inventory',j['inventory'],'--validation',job['validation'],
            '--output',str(folder/'trial'),'--uncalibrated-label','--phase-step','0.025','--optimizer','powell'])
        if ok:ok=stage('replay','audit_predictive_family_inclusion.py',['--study',str(args.study),'--trial',str(folder/'trial'),
            '--output',str(folder/'trial/exact_owner_replay.json')])
        status='execution_failed'
        if ok:
            c=read(folder/'trial/control.json');a=read(folder/'trial/new_family.json');replay=read(folder/'trial/exact_owner_replay.json')
            status='RF_verified_research_candidate' if c['paired_valid'] and a['paired_valid'] and replay['all_verified'] else 'inclusion_rejected'
        result=dict(job=j,source_trial=job['source_trial'],shared_family=False,stages=stages,status=status)
        write(out/(j['track_id']+'-terminal.json'),result);print(j['label'],status,flush=True);return result
    with ThreadPoolExecutor(max_workers=3) as pool:execution=list(pool.map(work,jobs))
    write(out/'execution.json',execution)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('study','trials','output'):p.add_argument('--'+n,type=Path,required=True)
    run(p.parse_args())
