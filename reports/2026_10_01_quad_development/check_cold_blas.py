"""Supervise and audit a cold numerical-equivalence gate on fixed first-block windows."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import numpy as np
from run_window import prepare_window
from acquire_blas import acquire_blas
from regression_batch import digest, execute, verify_sources
from evaluate_variant import evaluate

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
GOAL=HERE.parent/'2026_10_01_localization_goal'


def save(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2,allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('unit',choices=['DS9-B01-S1','DS9-B01-D1','DS9-B01-Q'])
    args=parser.parse_args()
    with (GOAL/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        binding,scans,_,_,_=prepare_window(args.unit)
        source=HERE/'independent-v2/DS9-B01'/(args.unit+'.json')
        assert digest(source)==source.with_suffix('.sha256').read_text().strip()
        baseline=json.loads(source.read_text());verify_sources(baseline['source_sha256']);verify_sources(baseline['inputs'])
        evaluation_path=source.parent/'evaluation.json'
        assert digest(evaluation_path)==evaluation_path.with_suffix('.sha256').read_text().strip()
        original=next(r for r in json.loads(evaluation_path.read_text())['rows'] if r['unit']==args.unit)
        assert original['accepted'] and original['receipt_sha256']==digest(source)
        inputs={k:v for scan,_,_ in scans for k,v in scan.inputs.items()}
        for _,height,_ in scans:inputs[height.input_bindings['grid_path']]=height.input_bindings['grid_sha256']
        inputs.update({str(p):digest(p) for p in [source,evaluation_path]})
        sources={str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
            if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)}
        sources[str(HERE/'run_blas_window.py')]=digest(HERE/'run_blas_window.py')
        directory=HERE/'cold-blas-v1'/args.unit;directory.mkdir(parents=True,exist_ok=False)
        freeze=directory/'sources.json';save(freeze,dict(source_sha256=sources,inputs=inputs,units=[binding]))
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(ROOT/'src'))
        output=directory/(args.unit+'.json')
        launch=execute([sys.executable,str(HERE/'run_blas_window.py'),args.unit,'--output',str(output)],
            directory,args.unit,timeout_s=90*binding['size'],env=env)
        verify_sources(sources);verify_sources(inputs)
        launch.update(freeze_sha256=digest(freeze),receipt_sha256=digest(output) if output.exists() else None)
        save(output.with_suffix('.launch.json'),launch)
        audited=evaluate(directory)['rows'][0]
        comparison=dict(unit=args.unit,accepted=audited['accepted'],equivalent=False,
            baseline_runtime_s=original['runtime_s'],optimized_runtime_s=launch['elapsed_seconds'],
            qualification='Cold numerical-equivalence gate; timing comparison is historical, not randomized host-load control. No model or acquisition-policy change.')
        if audited['accepted']:
            actual=json.loads(output.read_text())
            checks={key:actual['proposal'][key]==baseline['proposal'][key] for key in ['seeds','requested','unique_points','spacing']}
            checks['score_tolerance']=bool(np.allclose(actual['proposal']['scores'],baseline['proposal']['scores'],rtol=0,atol=1e-6))
            checks['fit_count']=len(actual['fits'])==len(baseline['fits'])
            checks['all_states']=checks['fit_count'] and all(np.allclose(a['mean'],b['mean'],rtol=0,atol=1e-5) for a,b in zip(actual['fits'],baseline['fits']))
            checks['all_labels']=checks['fit_count'] and all(a['associations']==b['associations'] for a,b in zip(actual['fits'],baseline['fits']))
            checks['best_objective']=abs(actual['best']['objectives'][-1]-baseline['best']['objectives'][-1])<1e-6
            checks['best_seed']=actual['best']['seed_index']==baseline['best']['seed_index']
            comparison.update(checks=checks,equivalent=all(checks.values()),
                maximum_best_state_difference=float(np.max(np.abs(np.asarray(actual['best']['mean'])-baseline['best']['mean']))))
        save(directory/'comparison.json',comparison);print(json.dumps(comparison,indent=2),flush=True)


if __name__=='__main__':main()
