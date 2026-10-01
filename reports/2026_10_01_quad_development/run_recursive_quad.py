"""Budget-accounted recursive quad experiment, separate from pair policy."""
import time
START=time.monotonic()
import argparse
import fcntl
import json
import os
from pathlib import Path
import resource
import sys
import numpy as np
from recursive_quad_inputs import admit,prepare
from recursive_quad_starts import remaining_quad_budget
from run_constituent_pair import save,digest,execute,verify_sources
from run_constituent_pair_v3 import policy_failure
from run_window import fit_localization_fast
from evaluate_variant import evaluate

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
GOAL=HERE.parent/'2026_10_01_localization_goal'


def worker(unit,directory,seconds):
    frozen=json.loads((directory/'sources.json').read_text())
    verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    binding,records,scans,columns,precision,ports,starts,cost,remaining,inputs,sources=prepare(unit)
    assert abs(remaining-seconds)<1e-9 and cost==frozen['constituent_cost_s']
    assert all(frozen['inputs'].get(k)==v for k,v in inputs.items())
    fits=[];deadline=START+seconds-5
    for index,state in enumerate(starts):
        if time.monotonic()>=deadline:break
        begun=time.monotonic()
        fit=fit_localization_fast(state,ports,precision,lambda x:np.linalg.norm(x[:2])<=250,
            max_iterations=64,deadline=deadline,degrees_of_freedom=4.)
        fits.append(dict(seed_index=index,mean=fit.mean.tolist(),objectives=list(fit.objectives),
            converged=fit.converged,reason=fit.reason,iterations=fit.iterations,
            associations=list(fit.associations),seconds=time.monotonic()-begun))
    scored=[f for f in fits if f['objectives']];best=min(scored,key=lambda f:f['objectives'][-1]) if scored else None
    usage=resource.getrusage(resource.RUSAGE_SELF)
    result=dict(unit=unit,binding=binding,model='recursive_pair_to_quad',fits=fits,best=best,
        status='converged_local_mode' if best and best['converged'] else 'unresolved',
        columns=[c.tolist() for c in columns],precision=precision.tolist(),
        inputs={k:v for scan,_,_ in scans for k,v in scan.inputs.items()},height=scans[0][1].input_bindings,
        observations=[list(p.observation_ids) for p in ports],initial_states=starts.tolist(),
        source_sha256=frozen['source_sha256'],
        config=dict(max_iterations=64,total_limit_s=360,extra_limit_s=seconds,prior_radius_km=250,height_m_msl=30.48),
        wall_seconds=cost+time.monotonic()-START,
        cpu_seconds=sum(r['cpu_seconds'] for r,_ in records)+usage.ru_utime+usage.ru_stime,
        qualification='Warm recursive replay; pair totals already include singles. Full worker preparation and fitting charged. No quad acquisition or extra continuation.')
    verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    save(directory/(unit+'.json'),result)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('unit');parser.add_argument('--worker',action='store_true')
    parser.add_argument('--seconds',type=float);args=parser.parse_args()
    directory=HERE/'recursive-quad-v1'/args.unit
    if args.worker:worker(args.unit,directory,args.seconds);return
    with (GOAL/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        selection=HERE/'selection.json';assert digest(selection)==selection.with_suffix('.sha256').read_text().strip()
        binding=next(u for u in json.loads(selection.read_text())['evaluation_units'] if u['unit_id']==args.unit)
        assert binding['size']==4
        directory.mkdir(parents=True,exist_ok=False)
        save(directory/'admission.json',dict(unit=binding,selection_sha256=digest(selection),runner_sha256=digest(__file__)))
        try:
            actual,records,inputs,sources=admit(args.unit);assert actual==binding
        except (AssertionError,OSError,ValueError,KeyError) as error:
            policy_failure(directory,binding,type(error).__name__+': '+str(error));return
        cost,seconds=remaining_quad_budget([launch['elapsed_seconds'] for _,launch in records])
        sources.update({str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
            if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)})
        for name in ['RECURSIVE_QUAD_PLAN.md','test_recursive_quad_starts.py','test_recursive_quad_policy.py']:
            sources[str(HERE/name)]=digest(HERE/name)
        save(directory/'sources.json',dict(source_sha256=sources,inputs=inputs,units=[binding],constituent_cost_s=cost))
        if seconds<10:policy_failure(directory,binding,'insufficient_budget',cost);return
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(ROOT/'src'))
        launch=execute([sys.executable,str(Path(__file__).resolve()),args.unit,'--worker','--seconds',str(seconds)],
            directory,args.unit,timeout_s=seconds,env=env)
        output=directory/(args.unit+'.json')
        launch.update(joint_launch_seconds=launch['elapsed_seconds'],constituent_cost_s=cost,
            elapsed_seconds=cost+launch['elapsed_seconds'],within_budget=launch['within_budget'] and cost+launch['elapsed_seconds']<=360,
            freeze_sha256=digest(directory/'sources.json'),receipt_sha256=digest(output) if output.exists() else None)
        save(output.with_suffix('.launch.json'),launch);evaluate(directory)


if __name__=='__main__':main()
