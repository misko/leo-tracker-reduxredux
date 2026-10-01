"""Supervised fixed-width warm discrepancy pilot with charged original work."""
import time
START=time.monotonic()
import argparse
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import resource
import sys
import numpy as np
from discrepancy_window_inputs import prepare_discrepancy_window,initial_state
from run_window import fit_localization_fast
from regression_batch import execute,verify_sources
from screen_seed_prefix import sealed,digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PILOT=tuple(f'{d}-B01-{s}' for d in ('DS9','DS10','DS11') for s in ('S1','D1','Q'))
ARMS=('baseline','sigma1')


def save(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2,allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')


def remaining_budget(original_seconds,size):
    if size not in (1,2,4) or not np.isfinite(original_seconds) or original_seconds<0:
        raise ValueError('Invalid original work accounting')
    remaining=90*size-original_seconds
    if remaining<10:raise ValueError('Insufficient remaining inference budget')
    return remaining


def worker(unit,arm,directory,seconds):
    freeze=sealed(directory/'sources.json')
    verify_sources(freeze['source_sha256']);verify_sources(freeze['inputs'])
    assert freeze['discrepancy_arm']==arm
    parent=Path(freeze['parent_receipt']);original=sealed(parent)
    binding,scans,columns,precision,ports=prepare_discrepancy_window(unit,arm)
    assert binding==original['binding'] and [c.tolist() for c in columns]==original['columns']
    assert precision[:len(original['precision'])].tolist()==original['precision']
    assert [list(p.observation_ids) for p in ports]==original['observations']
    state=initial_state(original,arm)
    assert state.tolist()==freeze['initial_state'] and precision.tolist()==freeze['precision']
    fit=fit_localization_fast(state,ports,precision,lambda x:np.linalg.norm(x[:2])<=250,
        max_iterations=64,deadline=START+seconds-5,degrees_of_freedom=4.)
    fitted=dict(seed_index=original['best']['seed_index'],mean=fit.mean.tolist(),objectives=list(fit.objectives),
        converged=fit.converged,reason=fit.reason,iterations=fit.iterations,associations=list(fit.associations),seconds=time.monotonic()-START)
    result=deepcopy(original)
    result.update(best=fitted,fits=[fitted],status='converged_local_mode' if fit.converged else 'unresolved',
        precision=precision.tolist(),source_sha256=freeze['source_sha256'],
        model='original_window_warm_control' if arm=='baseline' else 'shared_position_gaussian_scan_discrepancy_1km',
        qualification='Warm fixed-width sensitivity; original inference work charged. Same parent state, eight-point evidence and original nuisance priors. No geographic selection.',
        discrepancy_pilot=dict(arm=arm,sigma_km=0. if arm=='baseline' else 1.,parent_sha256=digest(parent),
            initial_state=state.tolist(),max_iterations=64,original_seconds=freeze['original_seconds'],extra_limit_s=seconds,
            base_dimension=len(original['precision'])))
    usage=resource.getrusage(resource.RUSAGE_SELF)
    result.update(wall_seconds=freeze['original_seconds']+time.monotonic()-START,
        cpu_seconds=original['cpu_seconds']+usage.ru_utime+usage.ru_stime)
    verify_sources(freeze['source_sha256']);verify_sources(freeze['inputs'])
    save(directory/(unit+'.json'),result)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('unit',choices=PILOT)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--arm',choices=ARMS)
    parser.add_argument('--seconds',type=float);args=parser.parse_args()
    directory=HERE/'scan-discrepancy-pilot-v1'/args.unit
    if args.worker:
        worker(args.unit,args.arm,directory/args.arm,args.seconds);return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        sources={};inputs={}
        summary_path=HERE/'scan-discrepancy-port-summary-v1.json';summary=sealed(summary_path)
        assert {r['unit'] for r in summary['rows']}==set(PILOT)
        assert all(r['maximum_gradient_error']<.002 for r in summary['rows'])
        assert digest(HERE/'summarize_discrepancy_ports.py')==summary['source_sha256']
        inputs[str(summary_path)]=digest(summary_path)
        verify_sources(summary['inputs'])
        for path in summary['inputs']:
            gate=sealed(Path(path));verify_sources(gate['sources']);verify_sources(gate['inputs'])
            sources.update(gate['sources']);inputs.update(gate['inputs']);inputs[path]=digest(path)
        for name in ('run_discrepancy_pilot.py','evaluate_discrepancy_pilot.py','discrepancy_window_inputs.py',
                     'evaluate_pilot.py','evaluate_variant.py','SCAN_DISCREPANCY_FIT_PLAN.md',
                     'test_discrepancy_pilot_policy.py','test_scan_discrepancy_ports.py','summarize_discrepancy_ports.py'):
            sources[str(HERE/name)]=digest(HERE/name)
        parent=HERE/'independent-v2'/args.unit.rsplit('-',1)[0]/(args.unit+'.json');original=sealed(parent)
        launch_path=parent.with_suffix('.launch.json');launch=json.loads(launch_path.read_text())
        assert launch['receipt_sha256']==digest(parent) and launch['returncode']==0 and launch['within_budget'] and not launch['timed_out']
        audit_path=parent.parent/'evaluation.json'
        audited=next(r for r in sealed(audit_path)['rows'] if r['unit']==args.unit)
        assert audited['accepted'] and audited['receipt_sha256']==digest(parent)
        original_seconds=launch['elapsed_seconds'];size=original['binding']['size']
        seconds=remaining_budget(original_seconds,size)
        inputs.update({str(p):digest(p) for p in (parent,launch_path,audit_path)})
        verify_sources(sources);verify_sources(inputs)
        directory.mkdir(parents=True,exist_ok=False)
        save(directory/'plan.json',dict(unit=args.unit,order=ARMS,sources=sources,inputs=inputs,original_seconds=original_seconds,extra_limit_s=seconds))
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(ROOT/'src'))
        for arm in ARMS:
            target=directory/arm;target.mkdir();freeze=target/'sources.json'
            prepared=prepare_discrepancy_window(args.unit,arm)
            save(freeze,dict(source_sha256=sources,inputs=inputs,units=[original['binding']],discrepancy_arm=arm,
                parent_receipt=str(parent),original_seconds=original_seconds,initial_state=initial_state(original,arm).tolist(),precision=prepared[3].tolist()))
            launch=execute([sys.executable,str(Path(__file__).resolve()),args.unit,'--worker','--arm',arm,'--seconds',str(seconds)],
                target,args.unit,timeout_s=seconds,env=env)
            output=target/(args.unit+'.json');extra=launch['elapsed_seconds']
            launch.update(incremental_seconds=extra,original_seconds=original_seconds,elapsed_seconds=original_seconds+extra,
                within_budget=launch['within_budget'] and original_seconds+extra<=90*size,
                freeze_sha256=digest(freeze),receipt_sha256=digest(output) if output.exists() else None)
            save(output.with_suffix('.launch.json'),launch)
            audit_launch=execute([sys.executable,str(HERE/'evaluate_discrepancy_pilot.py'),str(target)],target,'audit',timeout_s=90,env=env)
            save(target/'audit-launch.json',audit_launch)
            verify_sources(sources);verify_sources(inputs)
            evaluation=sealed(target/'evaluation.json') if (target/'evaluation.json').exists() else None
            save(target/'outcome.json',dict(launch=launch,audit_launch=audit_launch,evaluation=evaluation))
            print(json.dumps(dict(unit=args.unit,arm=arm,audit_returncode=audit_launch['returncode'],evaluation=evaluation)),flush=True)


if __name__=='__main__':main()
