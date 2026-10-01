"""Bounded shared-visibility multi-window pilots with explicit failure admission."""
import time
START=time.monotonic()
import argparse
import fcntl
import os
from pathlib import Path
import sys
import numpy as np
from run_shared_visibility_pilot import HERE,ROOT,sealed,baseline,setup,audit_directions,acceptance,save,digest,verify_sources,execute
from shared_visibility_curvature_optimizer import fit

BOUNDARY='DS11-B03-D2'
PILOT=(BOUNDARY,)+tuple(f'{dataset}-B01-{suffix}' for dataset in ['DS9','DS10','DS11'] for suffix in ['D1','Q'])


def budget(size,cost):
    if size not in [2,4] or not np.isfinite(cost) or cost<0:raise ValueError('invalid window budget')
    return 90.*size,max(0.,90.*size-cost)


def admit(unit):
    if unit!=BOUNDARY:return baseline(unit)
    directory=HERE/'constituent-pair-v3'/unit;path=directory/(unit+'.json')
    receipt=sealed(path);audit_path=directory/'evaluation.json';audit=sealed(audit_path)
    row=next(r for r in audit['rows'] if r['unit']==unit)
    launch_path=path.with_suffix('.launch.json');launch=sealed(launch_path)
    freeze_path=directory/'sources.json';frozen=sealed(freeze_path)
    if not (row['accepted'] is False and row['gradient_error']>.9 and
            row['receipt_sha256']==digest(path)==launch['receipt_sha256'] and
            launch['freeze_sha256']==digest(freeze_path)==audit['freeze_sha256'] and
            launch['returncode']==0 and launch['within_budget'] and not launch['timed_out'] and
            receipt['best']['converged'] and receipt['binding']['unit_id']==unit):
        raise ValueError('unexpected rejected boundary source')
    verify_sources(receipt['source_sha256']);verify_sources(receipt['inputs'])
    verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    inputs={str(p):digest(p) for p in [path,audit_path,launch_path,freeze_path]};inputs.update(receipt['inputs'])
    return receipt,float(launch['elapsed_seconds']),inputs


def worker(unit,directory,seconds):
    frozen=sealed(directory/'sources.json');verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    original,cost,_=admit(unit);model=setup(unit,original);initial=np.asarray(original['best']['mean'])
    best=fit(model,initial,START+seconds-5)
    verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    save(directory/(unit+'.json'),dict(unit=unit,binding=original['binding'],best=best,
        initial_state=initial.tolist(),source_sha256=frozen['source_sha256'],inputs=frozen['inputs'],
        original_cost_s=cost,incremental_worker_s=time.monotonic()-START,width_deg=.1,
        qualification='Failure-selected rejected-state diagnostic' if unit==BOUNDARY else 'Metadata-first warm multi-window pilot'))


def audit(unit,directory):
    frozen=sealed(directory/'sources.json');verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    path=directory/(unit+'.json');receipt=sealed(path);launch=sealed(path.with_suffix('.launch.json'))
    original,cost,_=admit(unit);limit,_=budget(original['binding']['size'],cost)
    model=setup(unit,original);best=receipt['best'];state=np.asarray(best['mean'])
    value,g,labels=model.evaluate(state);initial=np.asarray(original['best']['mean'])
    initial_value=model.evaluate(initial,gradient=False)[0]
    scale=np.ones_like(state);mask=model.precision>0;scale[mask]=1/np.sqrt(model.precision[mask]);scale[:2]=10.
    grad_inf=float(np.max(abs(g*scale)));differences=[]
    # Include all scan clock/drift and one epoch column, plus the fixed global directions.
    directions=audit_directions(len(state));seen={int(name.split('_')[-1]) for name,_ in directions if name.startswith('coordinate_')}
    for columns in original['columns']:
        for i in columns[2:6]:
            if i not in seen:directions.append((f'coordinate_{i}',np.eye(1,len(state),i)[0]));seen.add(i)
    for name,d in directions:
        for h in [.0005,.0001]:
            numeric=(model.evaluate(state+h*d,labels,False)[0]-model.evaluate(state-h*d,labels,False)[0])/(2*h)
            differences.append(dict(direction=name,step=h,analytic=float(g@d),numeric=numeric,error=abs(numeric-float(g@d))))
    checks=dict(source_binding=receipt['source_sha256']==frozen['source_sha256'],
        input_binding=receipt['inputs']==frozen['inputs'],binding=receipt['binding']==original['binding'],
        receipt_binding=launch['receipt_sha256']==digest(path),freeze_binding=launch['freeze_sha256']==digest(directory/'sources.json'),
        launch=launch['returncode']==0 and not launch['timed_out'] and launch['within_budget'],
        charged_budget=cost+launch['incremental_seconds']<=limit,converged=best['converged'] is True,
        stationary=grad_inf<1e-4,assignments=list(labels)==best['associations'],
        objective=abs(value-best['objectives'][-1])<1e-7,initial_objective=abs(initial_value-best['objectives'][0])<1e-7,
        initial_state=receipt['initial_state']==original['best']['mean'],monotone=bool(np.all(np.diff(best['objectives'])<=1e-10)),
        derivatives=max(r['error'] for r in differences)<.002)
    verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    save(directory/'evaluation.json',dict(unit=unit,accepted=acceptance(checks),checks=checks,
        scaled_gradient_inf=grad_inf,objective=value,initial_objective=initial_value,
        label_changes_from_source=sum(a!=b for a,b in zip(labels,original['best']['associations'],strict=True)),
        finite_differences=differences,seconds=time.monotonic()-START,
        qualification='Fresh-process complete objective audit, selected coordinates/directions, no geographic reference read.'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('unit',choices=PILOT)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--audit',action='store_true');parser.add_argument('--seconds',type=float)
    args=parser.parse_args();directory=HERE/'shared-window-pilot-v1'/args.unit
    if args.worker:worker(args.unit,directory,args.seconds);return
    if args.audit:audit(args.unit,directory);return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        original,cost,inputs=admit(args.unit);size=original['binding']['size'];limit,seconds=budget(size,cost)
        sources={str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
            if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)}
        for name in ['SHARED_WINDOW_PILOT_PLAN.md','test_shared_window_pilot.py']:
            p=HERE/name;sources[str(p)]=digest(p)
        directory.mkdir(parents=True,exist_ok=False)
        save(directory/'sources.json',dict(source_sha256=sources,inputs=inputs,original_cost_s=cost,
            binding=original['binding'],role='failure_selected' if args.unit==BOUNDARY else 'metadata_first',limit_s=limit))
        if seconds<10:
            save(directory/'policy-failure.json',dict(reason='insufficient_budget',remaining_s=seconds));return
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(ROOT/'src'))
        command=[sys.executable,str(Path(__file__).resolve()),args.unit]
        launch=execute(command+['--worker','--seconds',str(seconds)],directory,args.unit,timeout_s=seconds,env=env)
        output=directory/(args.unit+'.json');launch.update(incremental_seconds=launch['elapsed_seconds'],original_cost_s=cost,
            charged_seconds=cost+launch['elapsed_seconds'],freeze_sha256=digest(directory/'sources.json'),
            receipt_sha256=digest(output) if output.exists() else None)
        save(output.with_suffix('.launch.json'),launch)
        if launch['returncode']!=0 or not output.exists():
            save(directory/'evaluation.json',dict(unit=args.unit,accepted=False,reason='worker_failed_or_timed_out'));return
        audited=execute(command+['--audit'],directory,'audit',timeout_s=90.*size,env=env)
        save(directory/'audit-launch.json',audited)
        if not (directory/'evaluation.json').exists():
            save(directory/'evaluation.json',dict(unit=args.unit,accepted=False,reason='audit_failed_or_timed_out'))
        result=sealed(directory/'evaluation.json')
        print({k:result.get(k) for k in ['unit','accepted','scaled_gradient_inf','reason']},flush=True)


if __name__=='__main__':main()
