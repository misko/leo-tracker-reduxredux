"""Bounded, matched numerical-reference inclusion trials; no GPS inference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import numpy as np

from debug_fast_graph_unassociated import read,write
from annotate_predictive_only import context
from phase_reference_checks import phase_refresh,reference_domain

CASES=('DS26-0154','DS26-0044','DS26-0106')
PANEL=Path('/srv/bulk/leo/research/ds26-recovery-validation-20261031/phase-panel')
REPO=Path('/srv/bulk/leo-dev/fast-algo02-production-v1')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select_route(active_calibration, existing_predictive):
    if existing_predictive and not active_calibration:
        raise ValueError('uncalibrated target has existing predictive evidence; separate shared conditioning required')
    return 'shared' if active_calibration else 'new_family'


def check_domains(p,phases,entries):
    checks=dict(curved=reference_domain(p.sky['time_s'],p.flat_times,p.flat_labels,phases))
    if entries:
        from ds23_predictive_linear import linear_geometry
        view,*_=linear_geometry(p,entries)
        checks['predictive']=reference_domain(p.sky['time_s'],view.flat_times,view.flat_labels,phases)
    if not all(v['in_domain'] for v in checks.values()):
        raise ValueError('phase geometry leaves frozen causal orbit bank; extrapolation prohibited')
    return checks


def qualified_points(control_valid,addition_valid,audit_valid,added_points):
    return int(added_points) if control_valid and addition_valid and audit_valid else 0


def source_receipt(paths):
    return {str(p):sha(p) for p in sorted(set(map(Path,paths))) if p.is_file()}


def one(case,out,panel):
    began=time.monotonic();source=panel/case;frozen=read(source/'protocol.json')
    inventory=Path(frozen['inventory']);inv=read(inventory);d=context(inv);base,_=d['problems']['c0']
    validation=source/'reference30/annotation';ann=read(validation/'result.json');pr=read(validation/'protocol.json')
    if ann['annotation']['status']!='conditionally_supported_identity':raise ValueError('30s randomized identity not supported')
    norad=ann['annotation']['norad'];target=pr['target'];i=target['track_index'];track=d['scan'].tracks[i]
    offers=[p for f in ann['folds'] for p in f['proposals'] if p['norad']==norad]
    js={p['candidate_index'] for p in offers};aliases={p['alias'] for p in offers}
    if len(js)!=1 or len(aliases)!=1:raise ValueError('candidate or alias changes across saved partitions')
    j=next(iter(js));active=[dict(component=r['component'],points=int(d['keep'][sl].sum()))
        for r,sl in zip(base.rows,base.slices,strict=True) if r['candidate_index']==j and d['keep'][sl].any()]
    route=select_route(bool(active),any(e['candidate_index']==j for e in d['entries']))
    if route=='shared':
        import include_predictive_annotations as inclusion
        import audit_shared_predictive_inclusion as audit
    else:
        import include_new_predictive_family as inclusion
        import audit_predictive_family_inclusion as audit
    source_paths=[Path(__file__),inventory,source/'protocol.json',source/'annotation_summary.json',validation/'result.json',validation/'protocol.json']
    source_paths += [source/f'reference{limit}/annotation/result.json' for limit in (15,30)]
    for m in (inclusion,audit):source_paths.append(Path(m.__file__))
    write(out/'protocol.json',dict(case=case,inventory=str(inventory),study_root=str(inventory.parents[2]),
        validation=str(validation),route=route,target=target,norad=norad,candidate_index=j,alias=next(iter(aliases)),
        active_calibration=active,reference_limits_s=[15,30],
        same_validated_identity_aliases_priors_masks_starts_and_budgets=True,
        target_physical_phase_support_s=[-15,15] if route=='new_family' else 'unchanged shared causal posterior',
        original_noise_weights_priors_and_receiver_model=True,no_pruning=True,no_gate_relaxation=True,
        reference_rounds=5,position_iterations_per_round=48,new_family_maxfun_per_round=240 if route=='new_family' else None,
        new_family_phase_resolution_audit=True if route=='new_family' else None,
        maximum_seconds=590,threads=1,GPS_used=False,new_RF=False,new_TLE=False,orbit_bank_extension=False,
        source_sha256=source_receipt(source_paths)))
    original_make,original_refresh=inclusion.make_event_problem,inclusion.phase_refresh;current={}
    def capture_problem(*a,**k):
        p=original_make(*a,**k);current['p']=p
        check_domains(p,p.reference,[])
        return p
    inclusion.make_event_problem=capture_problem
    # Check the target's unchanged complete phase box before any new-family
    # integration, including derivative padding at both boundary phases.
    if route=='new_family':
        target_domains=[reference_domain(d['scan'].sky['time_s'],track['times'],np.zeros(len(track['times']),int),[phase]) for phase in (-15.,15.)]
        if not all(v['in_domain'] for v in target_domains):raise ValueError('target phase grid leaves existing bank')
        write(out/'target_phase_domain.json',dict(physical_support_unchanged=True,domains=target_domains))
    try:
        for limit in (15,30):
            def refresh(phases,reference,limit=limit):
                phase,check=phase_refresh(phases,reference,limit_s=limit);p=current['p']
                check['next_reference_domain']=check_domains(p,phase,p.linear_entries)
                return phase,check
            inclusion.phase_refresh=refresh
            folder=out/f'reference{limit}'/'inclusion'
            if route=='shared':
                args=SimpleNamespace(output=folder,inventory=inventory,validation=[validation],native_branches=None,
                    native_from_validation=False,predictive_member=i in base.members,noise_policy='original',
                    position_fit='regional_unconstrained',orphan_phase_refresh=False,orphan_orbit_prior=False,
                    target_orbit_prior=False,shared_satellite_refresh=False,conditional_satellite_refresh=False,joint_only=False)
            else:
                args=SimpleNamespace(output=folder,inventory=inventory,validation=[validation],phase_step=pr['phase_step_s'],
                    uncalibrated_label=j in base.labels,omit_orbit_uncertainty=False,omit_receiver_uncertainty=False,
                    optimizer='lbfgsb',skip_phase_audit=False)
            inclusion.run(args)
            write(folder/'reference_experiment.json',dict(reference_limit_s=limit,source30_nomination_frozen=True,
                before_every_update_bank_checked=True,physical_phase_prior_unchanged=True))
            old_refresh,old_exact=audit.phase_refresh,audit.exact_gate_replay
            exact_domains=[]
            audit.phase_refresh=lambda actual,reference:phase_refresh(actual,reference,limit_s=limit)
            def checked_exact(p,x,entries):
                domain=check_domains(p,p.state(x)['phases'][p.labels],entries)
                result=old_exact(p,x,entries)
                exact_domains.append(dict(norad=int(p.scan.norads[p.explicit_phase_family]),domains=domain))
                return result
            audit.exact_gate_replay=checked_exact
            try:audit.run(SimpleNamespace(trial=folder,study=inventory.parents[2],output=folder/'exact_owner_replay.json'))
            finally:audit.phase_refresh,audit.exact_gate_replay=old_refresh,old_exact
            write(folder/'exact_orbit_domains.json',dict(all_in_domain=True,checks=exact_domains))
            print(case,limit,route,'trial_and_exact_audit_complete',round(time.monotonic()-began,2),flush=True)
    finally:inclusion.make_event_problem,inclusion.phase_refresh=original_make,original_refresh
    # Preserve hashes of all loaded repository code and all inference inputs.
    imported=[Path(m.__file__) for m in sys.modules.values() if getattr(m,'__file__',None)
        and str(m.__file__).startswith(str(REPO)) and str(m.__file__).endswith('.py') and '/.venv/' not in str(m.__file__)]
    write(out/'source_receipts.json',dict(files_sha256=source_receipt(source_paths+imported)))
    files=list(out.glob('reference*/inclusion/*.json'))+[out/'protocol.json',out/'source_receipts.json']
    if (out/'target_phase_domain.json').exists():files.append(out/'target_phase_domain.json')
    write(out/'inference_seal.json',dict(GPS_used=False,artifacts_sha256=source_receipt(files),seconds=time.monotonic()-began))
    write(out/'terminal.json',dict(completed=True,seconds=time.monotonic()-began,budget_seconds=590,route=route))


def batch(out,panel):
    started=time.monotonic();case_root=out/'cases';case_root.mkdir(exist_ok=False)
    write(out/'batch_protocol.json',dict(cases=CASES,panel=str(panel),selection='three RF-selected clipped-phase panel cases; no GPS selection',
        per_case_seconds=590,subprocess_supervisor_seconds=600,threads_per_case=1,parallel_cases=3,
        matched_c_arms=True,reference_limits_s=[15,30],GPS_used=False,new_RF=False,
        source_sha256=source_receipt([Path(__file__),panel/'protocol.json',panel/'summary.json'])))
    def work(case):
        command=[sys.executable,__file__,'one','--case',case,'--output',str(case_root/case),'--panel',str(panel)]
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
        began=time.monotonic();timed_out=False
        with (out/(case+'.log')).open('x') as log:
            process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:code=process.wait(timeout=600)
            except subprocess.TimeoutExpired:
                timed_out=True;os.killpg(process.pid,signal.SIGKILL);code=process.wait()
        r=dict(case=case,command=command,returncode=code,timed_out=timed_out,seconds=time.monotonic()-began)
        write(out/(case+'-receipt.json'),r);print(r,flush=True);return r
    with ThreadPoolExecutor(max_workers=3) as pool:receipts=list(pool.map(work,CASES))
    write(out/'execution.json',dict(rows=receipts,seconds=time.monotonic()-started,all_completed=all(r['returncode']==0 for r in receipts)))
    files=list(case_root.glob('*/inference_seal.json'))+list(case_root.glob('*/terminal.json'))+[out/'batch_protocol.json',out/'execution.json']
    write(out/'batch_inference_seal.json',dict(GPS_used=False,artifacts_sha256=source_receipt(files),sealed_before_position_reporting=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['one','batch']);p.add_argument('--case',choices=CASES)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--panel',type=Path,default=PANEL);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=a.mode=='batch')
    if a.mode=='batch':batch(a.output,a.panel)
    else:
        def timeout(*unused):raise TimeoutError('590-second per-case hard bound')
        began=time.monotonic();signal.signal(signal.SIGALRM,timeout);signal.alarm(590)
        try:one(a.case,a.output,a.panel)
        except Exception as exc:
            write(a.output/'failure.json',dict(type=type(exc).__name__,message=str(exc),seconds=time.monotonic()-began));raise
