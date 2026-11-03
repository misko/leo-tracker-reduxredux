"""One frozen quad's seven cold evaluation units, at most two fits."""
import argparse
import fcntl
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from run_window import prepare_window
from regression_batch import digest, execute, verify_sources

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GOAL = HERE.parent/'2026_10_01_localization_goal'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('block',choices=['DS9-B01','DS10-B01','DS11-B01'])
    args = parser.parse_args()
    selection = json.loads((HERE/'selection.json').read_text())
    units = [u for u in selection['evaluation_units'] if u['block_id']==args.block]
    _,scans,_,_,_ = prepare_window(args.block+'-Q')
    sources = {str(Path(m.__file__).resolve()):digest(m.__file__)
        for m in tuple(sys.modules.values()) if getattr(m,'__file__',None)
        and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)}
    sources.update({str(p):digest(p) for p in [Path(__file__),HERE/'run_window.py',
        ROOT/'tests/analysis/test_localization_windows.py',HERE/'PROTOCOL.md',HERE/'selection.json']})
    inputs = {k:v for scan,height,_ in scans for k,v in {**scan.inputs,**height.input_bindings}.items()}
    directory = HERE/'independent-v1'/args.block
    with (GOAL/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        directory.mkdir(parents=True,exist_ok=False)
        freeze = directory/'sources.json'
        freeze.write_text(json.dumps(dict(source_sha256=sources,inputs=inputs,units=units),indent=2))
        freeze.with_suffix('.sha256').write_text(digest(freeze)+'\n')
        def run(unit):
            verify_sources(sources);verify_sources(inputs)
            name = unit['unit_id'];output=directory/(name+'.json')
            env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
            launch=execute([sys.executable,str(HERE/'run_window.py'),name,'--output',str(output)],
                directory,name,timeout_s=90.*unit['size'],env=env)
            verify_sources(sources);verify_sources(inputs)
            launch.update(freeze_sha256=digest(freeze),receipt_sha256=digest(output) if output.exists() else None)
            output.with_suffix('.launch.json').write_text(json.dumps(launch,indent=2))
            receipt=json.loads(output.read_text()) if output.exists() else {}
            print(json.dumps(dict(unit=name,status=receipt.get('status','missing'),
                exception=receipt.get('exception'),seconds=launch['elapsed_seconds'])),flush=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(run,units))


if __name__ == '__main__':
    main()
