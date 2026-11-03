"""Budget-accounted warm pair pilot, initialized only from constituent scans."""
import time
START = time.monotonic()
import argparse
import fcntl
import json
import os
from pathlib import Path
import resource
import sys
import numpy as np
from run_window import prepare_window, fit_localization_fast
from regression_batch import digest, execute, verify_sources
from leo.analysis.localization_window_starts import constituent_window_starts
from evaluate_variant import evaluate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GOAL = HERE.parent/'2026_10_01_localization_goal'
PILOT = ('DS9-B01-D1','DS10-B01-D1','DS11-B01-D1','DS9-B03-D2')


def save(path, value):
    with path.open('x') as stream: json.dump(value,stream,indent=2,allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')


def constituents(unit):
    selection_path = HERE/'selection.json'
    assert digest(selection_path) == selection_path.with_suffix('.sha256').read_text().strip()
    selection = json.loads(selection_path.read_text())
    binding = next(u for u in selection['evaluation_units'] if u['unit_id'] == unit)
    assert binding['size'] == 2
    singles = [next(u for u in selection['evaluation_units'] if u['scans'] == [scan]) for scan in binding['scans']]
    records = []; inputs = {str(selection_path):digest(selection_path)}; sources = {}
    for single in singles:
        name = single['unit_id']; directory = HERE/'independent-v2'/single['block_id']
        baseline_path = directory/(name+'.json')
        original = json.loads(baseline_path.read_text())
        if original['status'] == 'unresolved' and original['best']['reason'] == 'iteration_limit':
            directory = HERE/'continuation-v1'/name
        path = directory/(name+'.json'); audit_path = directory/'evaluation.json'
        for p in [path,audit_path,directory/'sources.json']:
            assert digest(p) == p.with_suffix('.sha256').read_text().strip()
            inputs[str(p)] = digest(p)
        audited = next(r for r in json.loads(audit_path.read_text())['rows'] if r['unit'] == name)
        assert audited['accepted'], 'constituent failed audit'
        receipt = json.loads(path.read_text()); launch_path = path.with_suffix('.launch.json')
        launch = json.loads(launch_path.read_text()); inputs[str(launch_path)] = digest(launch_path)
        assert digest(path) == audited['receipt_sha256'] == launch['receipt_sha256']
        assert launch['freeze_sha256'] == digest(directory/'sources.json')
        assert launch['returncode'] == 0 and launch['within_budget'] and not launch['timed_out']
        assert receipt['binding'] == single and receipt['best']['converged']
        assert receipt['best'] == min(receipt['fits'], key=lambda f:f['objectives'][-1])
        if directory != baseline_path.parent:
            assert receipt['continuation']['source_receipt_sha256'] == digest(baseline_path)
            inputs[str(baseline_path)] = digest(baseline_path)
        verify_sources(receipt['source_sha256']); verify_sources(receipt['inputs'])
        frozen = json.loads((directory/'sources.json').read_text())
        verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
        inputs.update(frozen['inputs']); sources.update(frozen['source_sha256'])
        records.append((receipt,launch))
    return binding, records, inputs, sources


def worker(unit, directory, seconds):
    frozen = json.loads((directory/'sources.json').read_text())
    verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
    binding, records, _, _ = constituents(unit)
    actual, scans, columns, precision, ports = prepare_window(unit)
    assert actual == binding
    for (scan,_,_), (receipt,_) in zip(scans,records,strict=True):
        assert receipt['binding']['scans'] == [scan.unit_id]
        assert receipt['inputs'] == scan.inputs
    local = [np.asarray(r['best']['mean']) for r,_ in records]
    starts = constituent_window_starts(local,columns,np.array([s[:2] for s in local]),len(precision))
    fits = []; deadline = START+seconds-5
    for index, state in enumerate(starts):
        if time.monotonic() >= deadline: break
        begun = time.monotonic()
        fit = fit_localization_fast(state,ports,precision,lambda x:np.linalg.norm(x[:2])<=250,
            max_iterations=64,deadline=deadline,degrees_of_freedom=4.)
        fits.append(dict(seed_index=index,mean=fit.mean.tolist(),objectives=list(fit.objectives),
            converged=fit.converged,reason=fit.reason,iterations=fit.iterations,
            associations=list(fit.associations),seconds=time.monotonic()-begun))
    scored = [f for f in fits if f['objectives']]
    best = min(scored,key=lambda f:f['objectives'][-1]) if scored else None
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result = dict(unit=unit, binding=binding, model='shared_position_constituent_starts',fits=fits,best=best,
        status='converged_local_mode' if best and best['converged'] else 'unresolved',
        columns=[c.tolist() for c in columns],precision=precision.tolist(),
        inputs={k:v for scan,_,_ in scans for k,v in scan.inputs.items()},height=scans[0][1].input_bindings,
        observations=[list(p.observation_ids) for p in ports],
        initial_states=starts.tolist(),source_sha256=frozen['source_sha256'],
        config=dict(max_iterations=64,extra_limit_s=seconds,total_limit_s=180,prior_radius_km=250,height_m_msl=30.48),
        wall_seconds=sum(l['elapsed_seconds'] for _,l in records)+time.monotonic()-START,
        cpu_seconds=sum(r['cpu_seconds'] for r,_ in records)+usage.ru_utime+usage.ru_stime,
        qualification='Warm constituent replay with all historical constituent launch times charged; no pair acquisition and no quad data. Not a fresh cold-pipeline timing.')
    verify_sources(frozen['source_sha256']); verify_sources(frozen['inputs'])
    save(directory/(unit+'.json'),result)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('unit',choices=PILOT)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--seconds',type=float)
    args=parser.parse_args();directory=HERE/'constituent-pair-v1'/args.unit
    if args.worker:
        worker(args.unit,directory,args.seconds);return
    with (GOAL/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        binding,records,inputs,sources=constituents(args.unit)
        cost=sum(l['elapsed_seconds'] for _,l in records);seconds=180-cost
        sources.update({str(Path(m.__file__).resolve()):digest(m.__file__)
            for m in tuple(sys.modules.values()) if getattr(m,'__file__',None)
            and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)})
        for p in [HERE/'CONSTITUENT_START_PLAN.md',ROOT/'tests/analysis/test_localization_window_starts.py']:
            sources[str(p)]=digest(p)
        directory.mkdir(parents=True,exist_ok=False)
        save(directory/'sources.json',dict(source_sha256=sources,inputs=inputs,units=[binding],constituent_cost_s=cost))
        if seconds < 10:
            save(directory/'policy-failure.json',dict(reason='insufficient_budget',remaining_s=seconds))
            return
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(ROOT/'src'))
        launch=execute([sys.executable,str(Path(__file__).resolve()),args.unit,'--worker','--seconds',str(seconds)],
            directory,args.unit,timeout_s=seconds,env=env)
        output=directory/(args.unit+'.json')
        launch.update(joint_launch_seconds=launch['elapsed_seconds'],constituent_cost_s=cost,
            elapsed_seconds=cost+launch['elapsed_seconds'],
            within_budget=launch['within_budget'] and cost+launch['elapsed_seconds']<=180,
            freeze_sha256=digest(directory/'sources.json'),receipt_sha256=digest(output) if output.exists() else None)
        save(output.with_suffix('.launch.json'),launch)
        evaluate(directory)


if __name__ == '__main__': main()
