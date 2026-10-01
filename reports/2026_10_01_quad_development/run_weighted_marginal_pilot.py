"""Matched optimizer-only weighted-curvature single pilot."""
import time
START=time.monotonic()
import argparse
import fcntl
import os
from pathlib import Path
import sys
import run_shared_visibility_pilot as base
from run_marginal_pilot import marginal_setup
from weighted_marginal_optimizer import fit


def main():
    parser=argparse.ArgumentParser();parser.add_argument('unit',choices=base.PILOT)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--audit',action='store_true');parser.add_argument('--seconds',type=float)
    args=parser.parse_args();directory=base.HERE/'weighted-marginal-pilot-v1'/args.unit
    base.START=START;base.setup=marginal_setup
    if args.worker:base.fit=fit;base.worker(args.unit,directory,args.seconds);return
    if args.audit:base.audit(args.unit,directory);return
    with (base.HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        _,cost,inputs=base.baseline(args.unit);seconds=base.allowance(cost)
        for name in ['weighted-curvature-check-v1.json','marginal-window-pilot-summary-v1.json']:
            check=base.HERE/name;verified=base.sealed(check)
            base.verify_sources(verified['source_sha256']);base.verify_sources(verified['inputs']);inputs[str(check)]=base.digest(check)
        sources={str(Path(m.__file__).resolve()):base.digest(m.__file__) for m in tuple(sys.modules.values())
            if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(base.ROOT)}
        for name in ['WEIGHTED_MARGINAL_PILOT_PLAN.md','test_weighted_marginal_optimizer.py','test_weighted_candidate_curvature.py','test_epoch_block_curvature.py']:
            p=base.HERE/name;sources[str(p)]=base.digest(p)
        directory.mkdir(parents=True,exist_ok=False)
        base.save(directory/'sources.json',dict(source_sha256=sources,inputs=inputs,original_cost_s=cost,
            arm='weighted_curvature_marginal',audit_policy='Unchanged full marginal fresh-process audit; only direction computation differs.'))
        if seconds<10:
            base.save(directory/'policy-failure.json',dict(reason='insufficient_budget',remaining_s=seconds));return
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(base.ROOT/'src'))
        command=[sys.executable,str(Path(__file__).resolve()),args.unit]
        launch=base.execute(command+['--worker','--seconds',str(seconds)],directory,args.unit,timeout_s=seconds,env=env)
        output=directory/(args.unit+'.json');launch.update(incremental_seconds=launch['elapsed_seconds'],original_cost_s=cost,
            charged_seconds=cost+launch['elapsed_seconds'],freeze_sha256=base.digest(directory/'sources.json'),
            receipt_sha256=base.digest(output) if output.exists() else None)
        base.save(output.with_suffix('.launch.json'),launch)
        if launch['returncode']!=0 or not output.exists():
            base.save(directory/'evaluation.json',dict(unit=args.unit,accepted=False,reason='worker_failed_or_timed_out'));return
        audited=base.execute(command+['--audit'],directory,'audit',timeout_s=180.,env=env)
        base.save(directory/'audit-launch.json',audited)
        if not (directory/'evaluation.json').exists():
            base.save(directory/'evaluation.json',dict(unit=args.unit,accepted=False,reason='audit_failed_or_timed_out'))
        result=base.sealed(directory/'evaluation.json')
        print({k:result.get(k) for k in ['unit','accepted','scaled_gradient_inf','reason']},flush=True)


if __name__=='__main__':main()
