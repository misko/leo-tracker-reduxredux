"""Resume the original clock experiment with a checked floating-point clamp.

One initial job produced an interval violation at roundoff precision when its
curved optimum was passed to the fixed-clock stage. Scientific bounds, priors,
budgets and successful scientific outputs remain unchanged.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

import probe_ds23_bracketed_clock as engine
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_bracketed_clock_v2'
OLD=engine.OUT
original_hashes=engine.hashes
original_factory=engine.clock_problem


def bounded_shift(value,interval):
    bounded=float(np.clip(value,interval['lower_s'],interval['upper_s']))
    if abs(bounded-value)>1e-12:
        raise ValueError('physical common UTC correction lies outside recorded interval')
    return bounded


def clock_problem(*args,**kwargs):
    shift=kwargs.get('fixed_shift_s')
    if shift is not None:
        kwargs['fixed_shift_s']=bounded_shift(shift,args[8])
    return original_factory(*args,**kwargs)


def hashes():
    return dict(original_hashes(),**{str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))})


def bind():
    engine.OUT=OUT;engine.hashes=hashes;engine.clock_problem=clock_problem
    p=engine.prepare()
    if 'roundoff_tolerance_s' not in p:
        old=read(OLD/'protocol.json')
        if any(p[k]!=old[k] for k in ('development_cases','confirmation_cases')):
            raise ValueError('clock cohort changed')
        p.update(roundoff_tolerance_s=1e-12,previous_pilot=str(OLD.relative_to(ROOT)),
                 correction='clip only numerical interval excursions <=1e-12 s at curved-to-predictive handoff')
        write(OUT/'protocol.json',p)
    return p


def run(case):
    previous=OLD/(case+'.json')
    if previous.exists():
        record=read(previous)
        # Existing complete fits used the unchanged mathematical model. They
        # are bound by digest rather than silently rerun or outcome-filtered.
        if record['source_sha256']!=original_hashes():raise ValueError('initial clock fit code changed')
        write(OUT/(case+'.json'),dict(record,reused_scientific_fit=dict(path=str(previous.relative_to(ROOT)),sha256=sha(previous))))
        return dict(case=case,reused=True,paired_valid=record['paired_valid'])
    return engine.run(case)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('development','confirmation'),required=True)
    args=parser.parse_args()
    for stage in ('development','confirmation'):
        if not read(OLD/(stage+'_execution.json'))['all_terminal']:
            raise ValueError('initial jobs must be terminal before recovery')
    protocol=bind();cases=protocol[args.stage+'_cases'];receipts=[]
    with ProcessPoolExecutor(max_workers=12) as pool:
        futures={pool.submit(run,c):c for c in cases}
        for f in as_completed(futures):
            try:receipts.append(f.result())
            except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
            write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts,completed=len(receipts),total=len(cases)))
    write(OUT/(args.stage+'_execution.json'),dict(all_terminal=True,receipts=receipts))
    print('Terminal',len(receipts),'errors',sum('error' in r for r in receipts),flush=True)
