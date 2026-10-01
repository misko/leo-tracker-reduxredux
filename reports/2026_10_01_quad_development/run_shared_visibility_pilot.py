"""Supervised, charged warm pilot; audit in a fresh bounded process."""
import time
START = time.monotonic()
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import numpy as np
from run_window import prepare_window
from run_constituent_pair import save, digest, verify_sources, execute
from shared_visibility_port import SharedVisibilityPort
from shared_window_objective import WindowObjective
from shared_visibility_optimizer import fit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PILOT = ('DS9-B01-S1', 'DS10-B01-S1', 'DS11-B01-S1')


def sealed(path):
    if digest(path) != path.with_suffix('.sha256').read_text().strip():
        raise ValueError('seal mismatch: '+str(path))
    return json.loads(path.read_text())


def allowance(cost):
    if not np.isfinite(cost) or cost < 0:
        raise ValueError('invalid historical cost')
    return max(0., 90.-cost)


def baseline(unit):
    path = HERE/'independent-v2'/unit.rsplit('-', 1)[0]/(unit+'.json')
    receipt = sealed(path)
    audit_path = path.parent/'evaluation.json'
    audit = next(r for r in sealed(audit_path)['rows'] if r['unit'] == unit)
    launch_path = path.with_suffix('.launch.json')
    launch = json.loads(launch_path.read_text())
    freeze_path = path.parent/'sources.json'
    frozen = sealed(freeze_path)
    if not (audit['accepted'] and receipt['best']['converged'] and
            audit['receipt_sha256'] == digest(path) == launch['receipt_sha256'] and
            launch['returncode'] == 0 and launch['within_budget'] and not launch['timed_out'] and
            launch['freeze_sha256'] == digest(freeze_path)):
        raise ValueError('baseline not admitted')
    verify_sources(receipt['source_sha256']); verify_sources(receipt['inputs'])
    verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
    inputs = {str(p): digest(p) for p in [path, audit_path, launch_path, freeze_path]}
    inputs.update(receipt['inputs'])
    return receipt, float(launch['elapsed_seconds']), inputs


def setup(unit, receipt):
    binding, scans, columns, precision, ports = prepare_window(unit)
    inputs = {k:v for s,_,_ in scans for k,v in s.inputs.items()}
    if binding != receipt['binding'] or inputs != receipt['inputs']:
        raise ValueError('baseline window mismatch')
    if not np.array_equal(precision, receipt['precision']):
        raise ValueError('prior precision mismatch')
    if [c.tolist() for c in columns] != receipt['columns']:
        raise ValueError('column map mismatch')
    if [list(p.observation_ids) for p in ports] != receipt['observations']:
        raise ValueError('physical observation mismatch')
    return WindowObjective([SharedVisibilityPort(p.local,.1) for p in ports],
                           [p.columns for p in ports],precision)


def audit_directions(dimensions):
    # Fixed before fitting: first five coordinates, three spread epoch columns,
    # and three nuisance directions with seed 402. No fitted-value selection.
    coords = sorted(set([0,1,2,3,4,5,dimensions//2,dimensions-1]))
    directions = [(f'coordinate_{i}',np.eye(1,dimensions,i)[0]) for i in coords]
    rng = np.random.default_rng(402)
    for i in range(3):
        d = rng.normal(size=dimensions); d[:2] = 0; d /= np.linalg.norm(d)
        directions.append((f'nuisance_direction_{i}',d))
    return directions


def acceptance(checks):
    return bool(checks) and all(v is True for v in checks.values())


def worker(unit, directory, seconds):
    frozen = sealed(directory/'sources.json')
    verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
    original, cost, _ = baseline(unit)
    model = setup(unit, original)
    initial = np.asarray(original['best']['mean'])
    result = fit(model,initial,START+seconds-5)
    verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
    save(directory/(unit+'.json'),dict(unit=unit,best=result,
        source_sha256=frozen['source_sha256'],inputs=frozen['inputs'],
        original_cost_s=cost,incremental_worker_s=time.monotonic()-START,
        initial_state=initial.tolist(),width_deg=.1,
        qualification='Warm baseline-state refinement; original work charged. Model and optimizer both changed.'))


def audit(unit, directory):
    frozen = sealed(directory/'sources.json')
    verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
    path = directory/(unit+'.json'); receipt = sealed(path)
    launch = sealed(path.with_suffix('.launch.json'))
    original,cost,_ = baseline(unit)
    model = setup(unit,original); best = receipt['best']; state = np.asarray(best['mean'])
    value,g,labels = model.evaluate(state)
    initial_value = model.evaluate(np.asarray(original['best']['mean']),gradient=False)[0]
    scale = np.ones_like(state); positive = model.precision>0
    scale[positive] = 1/np.sqrt(model.precision[positive]); scale[:2] = 10.
    grad_inf = float(np.max(abs(g*scale)))
    differences = []
    for name,d in audit_directions(len(state)):
        for h in [.0005,.0001]:
            numeric = (model.evaluate(state+h*d,labels,False)[0]-
                       model.evaluate(state-h*d,labels,False)[0])/(2*h)
            differences.append(dict(direction=name,step=h,analytic=float(g@d),
                                    numeric=numeric,error=abs(numeric-float(g@d))))
    checks = dict(source_binding=receipt['source_sha256']==frozen['source_sha256'],
        input_binding=receipt['inputs']==frozen['inputs'],
        receipt_binding=launch['receipt_sha256']==digest(path),
        freeze_binding=launch['freeze_sha256']==digest(directory/'sources.json'),
        launch=launch['returncode']==0 and not launch['timed_out'] and launch['within_budget'],
        charged_budget=cost+launch['incremental_seconds']<=90.,
        converged=best['converged'] is True,stationary=grad_inf<1e-4,
        assignments=list(labels)==best['associations'],
        objective=abs(value-best['objectives'][-1])<1e-7,
        initial_objective=abs(initial_value-best['objectives'][0])<1e-7,
        initial_state=receipt['initial_state']==original['best']['mean'],
        monotone=bool(np.all(np.diff(best['objectives'])<=1e-10)),
        derivatives=max(r['error'] for r in differences)<.002)
    verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
    save(directory/'evaluation.json',dict(unit=unit,accepted=acceptance(checks),checks=checks,
        scaled_gradient_inf=grad_inf,objective=value,initial_objective=initial_value,
        label_changes_from_baseline=sum(a!=b for a,b in zip(labels,original['best']['associations'],strict=True)),
        finite_differences=differences,seconds=time.monotonic()-START,
        qualification='Fresh-process numerical audit with selected coordinates and directions, not exhaustive curvature or calibrated uncertainty. No geographic reference read.'))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('unit',choices=PILOT)
    parser.add_argument('--worker',action='store_true'); parser.add_argument('--audit',action='store_true')
    parser.add_argument('--seconds',type=float); args = parser.parse_args()
    directory = HERE/'shared-visibility-pilot-v1'/args.unit
    if args.worker: worker(args.unit,directory,args.seconds); return
    if args.audit: audit(args.unit,directory); return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        original,cost,inputs = baseline(args.unit); seconds = allowance(cost)
        sources = {str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
                   if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py'
                   and Path(m.__file__).resolve().is_relative_to(ROOT)}
        for name in ['SHARED_VISIBILITY_PILOT_PLAN.md','test_shared_visibility_pilot.py']:
            p=HERE/name; sources[str(p)]=digest(p)
        directory.mkdir(parents=True,exist_ok=False)
        save(directory/'sources.json',dict(source_sha256=sources,inputs=inputs,original_cost_s=cost,
            audit_policy='coordinates 0..5, floor(D/2), D-1; three seed402 nuisance directions; steps .0005/.0001; derivative tolerance .002; audit cap 180s'))
        if seconds<10:
            save(directory/'policy-failure.json',dict(reason='insufficient_budget',remaining_s=seconds)); return
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(ROOT/'src'))
        command=[sys.executable,str(Path(__file__).resolve()),args.unit]
        launch=execute(command+['--worker','--seconds',str(seconds)],directory,args.unit,timeout_s=seconds,env=env)
        output=directory/(args.unit+'.json')
        launch.update(incremental_seconds=launch['elapsed_seconds'],original_cost_s=cost,
            charged_seconds=cost+launch['elapsed_seconds'],freeze_sha256=digest(directory/'sources.json'),
            receipt_sha256=digest(output) if output.exists() else None)
        save(output.with_suffix('.launch.json'),launch)
        if launch['returncode']!=0 or not output.exists():
            save(directory/'evaluation.json',dict(unit=args.unit,accepted=False,reason='worker_failed_or_timed_out')); return
        audited=execute(command+['--audit'],directory,'audit',timeout_s=180.,env=env)
        save(directory/'audit-launch.json',audited)
        if not (directory/'evaluation.json').exists():
            save(directory/'evaluation.json',dict(unit=args.unit,accepted=False,reason='audit_failed_or_timed_out'))
        print((directory/'evaluation.json').read_text(),flush=True)


if __name__=='__main__': main()
