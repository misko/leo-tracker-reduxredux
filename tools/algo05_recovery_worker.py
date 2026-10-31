"""Guarded, bounded timing-gap conditional recovery over a private ALGO04 export."""
import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path
from algo03_shadow_worker import read,write
from algo05_cache import relocate,digest
from leo.application.automatic_fast_graph import execute
from leo.contracts.fast_graph_position_v4 import owners,incumbent_proof,qualify

ROOT=Path(__file__).resolve().parents[1]

def eligible(decision,root,incumbent):
    occupied=set().union(*(set(v) for v in owners(incumbent).values()))
    rows=[]
    for attempt in decision['attempts']:
        if not attempt.get('shared_family') or attempt['status']!='RF_rejected':continue
        tid=attempt['track_id'];folder=root/tid/'annotation'
        if not (folder/'result.json').exists():continue
        r=read(folder/'result.json');p=read(folder/'protocol.json')
        if (r['annotation']['status']!='conditionally_supported_identity' or r.get('graph_bundle')
            or r.get('inactive_graph_fragment') or p['target'].get('native_branch_source')
            or set(p['target']['observation_ids']) & occupied):continue
        rows.append(dict(track_id=tid,points=len(p['target']['observation_ids']),validation=str(folder)))
    return rows

def select(rows):
    passed=[r for r in rows if r['qualification']['qualified']]
    return min(passed,key=lambda r:(-r['identity']['minimum_margin'],-r['qualification']['added_points']['fitted_c'],r['track_id'])) if passed else None

def compact(trial,audit,identity,universe,parent_ids):
    rows=[]
    for r in audit['rows']:
        rows.append(dict(role=r['role'],arm=r['arm'],verified=r['verified'],
            gate_slacks={k:v for f in r['exact_family_replays'] for k,v in f['all_gate_slacks'].items()},
            phase_reference_check=r['phase_reference_check'],incumbent_ownership_changes=r['incumbent_ownership_changes']))
    return dict(policy='gap_conditional',identity=identity,observation_ids=sorted(universe),
        target_ids=trial['target_entries'][0]['observation_ids'],parent_ids=parent_ids,
        target_times_s=trial['arms']['fitted_c']['target_diagnostics'][0]['times_s'],
        trial=dict(paired_valid=trial['paired_valid'],arms={a:{k:r[k] for k in
            ('endpoint_latlon','proposed_owners','proposed_associated_ids','final_phase_change_s')} for a,r in trial['arms'].items()}),
        audit=dict(all_verified=audit['all_verified'],rows=rows))

def run(output,maximum_seconds):
    began=time.monotonic();deadline=began+maximum_seconds
    descriptor=read(output/'source-export/descriptor.json');export=output/'source-export'
    if descriptor['root']!=str(export):raise ValueError('Wrong private export root')
    for name,h in descriptor['files'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts or digest(export/name)!=h.removeprefix('sha256:'):
            raise ValueError('Export member changed')
    current=output/'current'
    receipt=relocate(export/'recovery',current,descriptor['source_recovery_root'],
        {k.removeprefix('recovery/'):v for k,v in descriptor['files'].items() if k.startswith('recovery/')})
    write(output/'relocation.json',receipt)
    incumbent=descriptor['incumbent'];decision=read(current/'decision.json')
    inventories=list((current/'all-large-track-recovery').glob('*/inventory.json'))
    if len(inventories)!=1:raise ValueError('One retained recovery inventory required')
    inventory=inventories[0];inv=read(inventory)
    obs=read(Path(inv['job']['root'])/inv['job']['case']/'observations.json');universe={o['observation_id'] for o in obs}
    targets=eligible(decision,current,incumbent);rows=[];stages=[];excluded=[]
    write(output/'protocol.json',dict(policy='gap_conditional',targets=targets,gap_s=5,min_points=12,min_span_s=10,
        maximum_seconds=maximum_seconds,source_inventory_sha256=digest(inventory),
        no_GPS_inference=True,causal_only=True,one_selected_fit=True,both_c_arms=True))
    def stage(script,args,log,cap):
        remaining=int(deadline-time.monotonic()-20)
        if remaining<1:raise TimeoutError('ALGO05 recovery deadline')
        limit=min(cap,remaining);start=time.monotonic()
        cmd=[sys.executable,'-B',str(ROOT/'tools/algo05_gap_stage.py'),script,*map(str,args)]
        log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('xb') as stream:code=execute(cmd,log=stream,timeout=limit)
        rec=dict(command=cmd,returncode=code,seconds=time.monotonic()-start,timeout_s=limit)
        stages.append(rec);write(output/'stages'/f'{len(stages):04d}.json',rec)
        return code==0
    try:
        for t in targets:
            folder=output/'targets'/t['track_id'];folder.mkdir(parents=True)
            source=folder/'source.json';write(source,dict(t,inventory=str(inventory)))
            if not stage('prepare',[source,folder/'gap-source'],folder/'prepare.log',180):continue
            parent_ids=read(folder/'gap-source/protocol.json')['parent_observation_ids']
            for branch in read(folder/'gap-source/branches.json')['branches']:
                if len(branch['observation_ids'])==t['points']:continue
                root=folder/branch['branch_id'];validation=root/'annotation';trial=root/'trial'
                if not stage('annotate_predictive_only.py',['--inventory',inventory,'--output',validation,
                    '--track',branch['branch_id'],'--native-branches',folder/'gap-source/branches.json',
                    '--distinct-partitions','--candidates','3','--folds','3','--uncalibrated-phase-mixture'],root/'annotation.log',240):continue
                identity=read(validation/'result.json')['annotation']
                if identity['status']!='conditionally_supported_identity':
                    excluded.append(dict(track_id=t['track_id'],branch_id=branch['branch_id'],identity=identity));continue
                if not stage('include_predictive_annotations.py',['--inventory',inventory,'--validation',validation,
                    '--output',trial,'--native-from-validation','--conditional-satellite-refresh'],root/'trial.log',240):continue
                if not stage('audit_shared_predictive_inclusion.py',['--study',current,'--trial',trial,
                    '--output',trial/'exact_owner_replay.json'],root/'audit.log',180):continue
                fit=read(trial/'target_0.json');audit=read(trial/'exact_owner_replay.json')
                q=qualify(fit,audit,owners(incumbent),universe)
                row=dict(track_id=t['track_id'],branch_id=branch['branch_id'],identity=identity,qualification=q,path=str(trial))
                rows.append(row)
                if q['qualified']:write(root/'candidate.json',compact(fit,audit,identity,universe,parent_ids))
                write(output/f'partial-{len(rows):04d}.json',rows)
    except (TimeoutError, subprocess.TimeoutExpired) as error:
        excluded.append(dict(budget_exhausted=str(error)))
    chosen=select(rows)
    candidate=read(Path(chosen['path']).parent/'candidate.json') if chosen else None
    write(output/'decision.json',dict(selected=chosen,candidate=candidate,trials=rows,excluded=excluded,stages=stages,
        no_GPS_inference=True,causal_only=True))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--maximum-seconds',type=int,required=True);a=p.parse_args()
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(TimeoutError('ALGO05 terminated')))
    run(a.output.resolve(),a.maximum_seconds)
