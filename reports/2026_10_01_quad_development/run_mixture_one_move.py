"""One sealed coupled-label choice per window, then one bounded refit."""
import fcntl
import os
from pathlib import Path
import sys
import time
import numpy as np
from run_window import prepare_window
from check_receiver_curvature import save
from mixture_localization import MixtureObjective
from mixture_optimizer import fit,audit
from mixture_window_groups import group_keys
from one_move_policy import choose
from screen_seed_prefix import sealed,digest
from regression_batch import execute,verify_sources
from failure_composition_checks import process_ok

HERE=Path(__file__).resolve().parent


def worker(unit,directory):
    inputs={}
    def read(path):
        value=sealed(path);inputs[str(path)]=digest(path);return value
    choices=read(HERE/'mixture-one-move-v1/choices.json');verify_sources(choices['sources']);verify_sources(choices['inputs'])
    choice=next(r for r in choices['rows'] if r['unit']==unit)['move']
    diagnostic_dir=HERE/'mixture-label-check-v1'/unit
    diagnostic=read(diagnostic_dir/'result.json');assert choice==choose(diagnostic['moves'])
    frozen=read(diagnostic_dir/'sources.json');sources=dict(frozen['source_sha256']);inputs.update(frozen['inputs'])
    assert process_ok(read(diagnostic_dir/'launch.json'))
    single=unit.endswith('S1')
    old_dir=HERE/'mixture-localization-pilot-v1'/unit/'mixture' if single else HERE/'mixture-window-pilot-v1'/unit
    old=read(old_dir/('result.json' if single else 'mixture.json'));assert old['audit']['accepted']
    campaign='one-start-blas-cold-v1' if single else 'one-start-blas-window-cold-v1'
    parent=read(HERE/campaign/unit/'blas'/(unit+'.json'))
    verify_sources(sources);verify_sources(inputs)
    binding,scans,columns,precision,ports=prepare_window(unit)
    assert binding==parent['binding']==old['binding'] and parent['observations']==[list(p.observation_ids) for p in ports]
    labels=list(parent['best']['associations']);initial=np.asarray(old['fit']['mean'])
    catalogues=[s[0].bank.norad_ids for s in scans];counts=[len(s[2]) for s in scans]
    if choice:
        assert labels[choice['track']]==choice['old_index'];labels[choice['track']]=choice['new_index']
    keys=group_keys(binding['scans'],catalogues,counts,labels)
    model=MixtureObjective(ports,labels,keys,precision,initial)
    initial_value,gradient,metric,_=model.evaluate(initial)
    expected_gain=choice['mixture_gain'] if choice else 0.
    assert abs(old['fit']['objectives'][-1]-initial_value-expected_gain)<1e-6
    sources.update({str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    for name in ('MIXTURE_ONE_MOVE_PLAN.md','test_one_move_policy.py'):sources[str(HERE/name)]=digest(HERE/name)
    verify_sources(sources);verify_sources(inputs);save(directory/'sources.json',dict(source_sha256=sources,inputs=inputs))
    gradient_error=None
    if choice:
        numeric=[]
        for j in model.active:
            step=np.zeros(len(initial));step[j]=.0005
            numeric.append((model.evaluate(initial+step,False)[0]-model.evaluate(initial-step,False)[0])/.001)
        gradient_error=float(np.max(abs(gradient-numeric)));assert gradient_error<.005
        started=time.monotonic();result=fit(model,initial,started+60*binding['size']);fit_seconds=time.monotonic()-started
        numerical=audit(model,result)
        if numerical['accepted']:assert result['objectives'][-1]<=initial_value+1e-6
    else:
        result=old['fit'];numerical=old['audit'];fit_seconds=0.
    verify_sources(sources);verify_sources(inputs)
    value=dict(unit=unit,binding=binding,move=choice,changed=choice is not None,fit=result,audit=numerical,
        initial_objective=initial_value,initial_gain=expected_gain,initial_gradient_error=gradient_error,
        fit_seconds=fit_seconds,labels=labels,
        objective_improvement=old['fit']['objectives'][-1]-result['objectives'][-1] if numerical['accepted'] else None,
        qualification='One score-selected move then fixed-membership warm refit, or inherited unchanged accepted parent. No geographic selection.')
    save(directory/'result.json',value);print(unit,bool(choice),numerical,flush=True)


def main():
    if len(sys.argv)==3:worker(sys.argv[1],Path(sys.argv[2]));return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=HERE/'mixture-label-summary-v1.json';summary=sealed(path);verify_sources(summary['sources']);verify_sources(summary['inputs'])
        root=HERE/'mixture-one-move-v1';root.mkdir(exist_ok=False)
        rows=[dict(unit=r['unit'],move=choose(r['moves']),size=r['size']) for r in summary['rows']]
        assert sum(r['move'] is not None for r in rows)==5
        save(root/'choices.json',dict(rows=rows,inputs={str(path):digest(path)},sources={str(HERE/n):digest(HERE/n) for n in ('MIXTURE_ONE_MOVE_PLAN.md','one_move_policy.py','test_one_move_policy.py','run_mixture_one_move.py')}))
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(HERE.parents[1]/'src'))
        for row in rows:
            directory=root/row['unit'];directory.mkdir()
            launch=execute([sys.executable,str(Path(__file__).resolve()),row['unit'],str(directory)],directory,row['unit'],timeout_s=90*row['size'],env=env)
            save(directory/'launch.json',launch);print(row['unit'],launch['returncode'],launch['elapsed_seconds'],flush=True)


if __name__=='__main__':main()
