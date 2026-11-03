"""Durable recovery of a frozen campaign; interrupted trials retain their budget.

The original inference implementation is unchanged. Abruptly interrupted cases
keep their last qualified checkpoint and remain explicitly incomplete. Since
their full elapsed computation is unobservable, their entire original budget
is conservatively charged rather than granting an unrecorded second search.
Only cases outside the possibly dispatched prefix receive fresh inference.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import fcntl
import os
from pathlib import Path
import time

import numpy as np

from run_algo01_ds23_sample import read, write, sha
import run_ds23_combined_recovery_full as inference


def interrupted_cases(available, terminal, workers):
    if workers<1 or len(available)!=len(set(available)):
        raise ValueError('unique ordered cases and positive worker count required')
    terminal=set(terminal)
    if not terminal<=set(available):raise ValueError('terminal case outside population')
    prefix=available[:min(len(available),len(terminal)+workers)]
    if not terminal<=set(prefix):
        raise ValueError('completed cases do not match the original FIFO dispatch')
    return sorted(set(prefix)-terminal),available[len(prefix):]


def terminal_from_checkpoint(record, checkpoint_digest, budget):
    result=dict(record)
    result.update(status='interrupted',error='Original inference processes disappeared without a completion receipt; last qualified checkpoint retained.',
        interrupted_checkpoint_sha256=checkpoint_digest,
        charged_inference_budget_seconds=budget,seconds_is_checkpoint_lower_bound=True,
        no_additional_inference_budget_granted=True)
    return result


def atomic_write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.recovery-writing')
    write(temporary,data);os.replace(temporary,path)


def recover_interrupted(case,protocol):
    out=inference.OUT;directory=out/case;final=directory/'result.json'
    if final.exists():return dict(case=case,cached=True)
    checkpoint=directory/'checkpoint.json';budget=protocol['per_scan_seconds']
    if checkpoint.exists():
        record=read(checkpoint)
        if record['source_protocol_sha256']!=sha(out/'protocol.json'):
            raise ValueError('interrupted checkpoint belongs to another protocol')
        record=terminal_from_checkpoint(record,sha(checkpoint),budget)
    else:
        # No trial is run here: restore the already qualified original model.
        from investigate_ds23_adaptive_failures import phase_widths
        from probe_ds23_causal_phase_mean import forecast_phase_mean
        scan,node,mask,base,old=inference.context(case)
        _,receipts=phase_widths(scan,list(range(len(scan.norads))))
        hyper=old['hyperparameters_from_pre_RF_TLE_only']
        means=forecast_phase_mean(receipts,hyper['shrinkage'])
        record=dict(case=case,input_root=protocol['input_roots'][case],
            baseline_arms=old['policy_arms'],policy_arms=old['policy_arms'],original_mask=mask,
            policy_model=dict(fine_basis=False,events=[],node=node,mask=mask,
                entries=old['linear_entries'] if old['linear_paired_valid'] else [],
                powers=old['weights'],means=means,hyper=hyper),
            stages=[],status='interrupted_before_checkpoint',seconds=0.,
            error='Case may have been dispatched when original inference disappeared; no checkpoint exists. Original qualified model retained.',
            source_protocol_sha256=sha(out/'protocol.json'),
            charged_inference_budget_seconds=budget,seconds_is_checkpoint_lower_bound=True,
            no_additional_inference_budget_granted=True,GPS_used=False,future_TLE_used=False,
            original_points_never_removed=True)
    atomic_write(final,record)
    return dict(case=case,status=record['status'],last_checkpoint_seconds=record['seconds'])


def receipt(case,path):
    r=read(path)
    return dict(case=case,status=r['status'],seconds=r['seconds'],error=r.get('error'),
        retained_points=int(np.asarray(r['policy_model']['mask']).sum()),
        accepted_stages=[s['name'] for s in r['stages'] if s.get('accepted')])


def main(workers):
    out=inference.OUT;out.mkdir(parents=True,exist_ok=True)
    with (out/'durable_recovery.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        protocol=inference.prepare();plan_path=out/'durable_recovery_plan.json'
        if plan_path.exists():
            plan=read(plan_path)
            if plan['protocol_sha256']!=sha(out/'protocol.json') or plan['wrapper_sha256']!=sha(Path(__file__)):
                raise ValueError('durable recovery plan source changed')
        else:
            terminal={p.parent.name for p in out.glob('DS23-*/result.json')}
            interrupted,remaining=interrupted_cases(protocol['available_cases'],terminal,protocol['workers'])
            plan=dict(original_terminal_cases=sorted(terminal),interrupted_cases=interrupted,
                fresh_cases=remaining,protocol_sha256=sha(out/'protocol.json'),
                wrapper_sha256=sha(Path(__file__)),workers=workers,
                original_process_exit_reason='unavailable; no execution receipt or kernel OOM record found',
                dispatch_prefix_is_conservative=True,interrupted_cases_receive_no_fresh_search=True,
                interrupted_full_budget_conservatively_charged=True,
                runtime_of_interrupted_cases_is_only_a_checkpoint_lower_bound=True)
            atomic_write(plan_path,plan)
        started=time.monotonic();receipts=[]
        for case in plan['interrupted_cases']:
            r=recover_interrupted(case,protocol);print('RECOVER_INTERRUPTED',r,flush=True)
        completed={p.parent.name for p in out.glob('DS23-*/result.json')}
        fresh=[c for c in plan['fresh_cases'] if c not in completed]
        atomic_write(out/'progress.json',dict(completed=len(completed),total=len(protocol['available_cases']),
            recovery_active=True,interrupted=len(plan['interrupted_cases']),remaining_fresh=len(fresh),
            seconds_since_recovery=0.))
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures={executor.submit(inference.run_case,c):c for c in fresh}
            for future in as_completed(futures):
                case=futures[future]
                try:r=future.result()
                except Exception as exc:r=dict(case=case,status='worker_failed',error=repr(exc))
                receipts.append(r)
                completed={p.parent.name for p in out.glob('DS23-*/result.json')}
                atomic_write(out/'progress.json',dict(completed=len(completed),total=len(protocol['available_cases']),
                    recovery_active=True,receipts=receipts,interrupted=len(plan['interrupted_cases']),
                    seconds_since_recovery=time.monotonic()-started))
        missing=[c for c in protocol['available_cases'] if not(out/c/'result.json').exists()]
        if missing:
            atomic_write(out/'durable_recovery_failure.json',dict(missing_results=missing,receipts=receipts))
            raise RuntimeError('missing terminal results after recovery; inspect durable_recovery_failure.json')
        terminal=[receipt(c,out/c/'result.json') for c in protocol['available_cases']]
        atomic_write(out/'execution.json',dict(receipts=terminal,all_terminal=True,
            missing_cases=protocol['missing_cases'],external_interruption_preserved=True,
            recovery_seconds=time.monotonic()-started,wrapper_sha256=sha(Path(__file__))))
        # Geographic truth is first read here, after all inference has finished.
        from evaluate_ds23_combined_recovery_full import collect,paired_changes,paired_comparison_statistics,summarize_rows
        result=collect(out,workers=workers)
        rows=result['all_rows'];strata={}
        for status in sorted({r.get('recovery_pipeline_status') for r in rows if r['method']=='combined_recovery' and r['status']=='accepted'}):
            cases={r['case'] for r in rows if r['method']=='combined_recovery' and r.get('recovery_pipeline_status')==status}
            selected=[r for r in rows if r['case'] in cases]
            strata[status]=dict(count=len(cases),cases=sorted(cases),statistics=summarize_rows(selected,len(cases)),
                paired_comparisons=paired_comparison_statistics(paired_changes(selected)))
        atomic_write(out/'pipeline_completion_audit.json',dict(population=413,available=410,
            qualified_incumbent_evaluation_covers_all_available=True,
            full_algorithm_completed_all_available=all(r['status']=='complete' for r in terminal),
            completion_strata=strata,interrupted_budget_policy=plan,
            evaluation_sha256=sha(out/'evaluation.json')))
        print('FULL_EVALUATION_COMPLETE',result['statistics'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=30)
    main(parser.parse_args().workers)
