"""Full-panel extension of the unchanged, budget-accounted constituent pair policy."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
from run_constituent_pair import constituents, worker, save, digest, execute, evaluate

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
GOAL=HERE.parent/'2026_10_01_localization_goal'


def policy_failure(directory,binding,reason,cost=None):
    save(directory/'policy-failure.json',dict(unit=binding['unit_id'],reason=reason,constituent_cost_s=cost))
    save(directory/'evaluation.json',dict(rows=[dict(unit=binding['unit_id'],block_id=binding['block_id'],
        size=binding['size'],scans=binding['scans'],accepted=False,failures=[reason],
        fit_status='policy_failure',runtime_s=cost,error_m=None)],
        qualification='No target-window fit: policy admission or remaining-budget failure. Retain in planned denominators. Unknown runtime stays null.'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('unit')
    parser.add_argument('--worker',action='store_true');parser.add_argument('--seconds',type=float)
    args=parser.parse_args();directory=HERE/'constituent-pair-v3'/args.unit
    if args.worker:
        worker(args.unit,directory,args.seconds);return
    with (GOAL/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        selection_path=HERE/'selection.json'
        assert digest(selection_path)==selection_path.with_suffix('.sha256').read_text().strip()
        binding=next(u for u in json.loads(selection_path.read_text())['evaluation_units'] if u['unit_id']==args.unit)
        assert binding['size'] == 2, 'this arm only fits pairs'
        directory.mkdir(parents=True,exist_ok=False)
        save(directory/'admission.json',dict(unit=binding,selection_sha256=digest(selection_path),runner_sha256=digest(__file__)))
        try:
            actual,records,inputs,sources=constituents(args.unit)
            assert actual==binding
        except (AssertionError,OSError,ValueError,KeyError) as error:
            policy_failure(directory,binding,type(error).__name__+': '+str(error));return
        cost=sum(l['elapsed_seconds'] for _,l in records);seconds=180-cost
        sources.update({str(Path(m.__file__).resolve()):digest(m.__file__)
            for m in tuple(sys.modules.values()) if getattr(m,'__file__',None)
            and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)})
        for p in [HERE/'CONSTITUENT_START_PLAN.md',HERE/'FULL_PAIR_PLAN.md',ROOT/'tests/analysis/test_localization_window_starts.py',HERE/'test_constituent_policy_failures.py']:
            sources[str(p)]=digest(p)
        save(directory/'sources.json',dict(source_sha256=sources,inputs=inputs,units=[binding],constituent_cost_s=cost))
        if seconds<10:
            policy_failure(directory,binding,'insufficient_budget',cost);return
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


if __name__=='__main__':main()
