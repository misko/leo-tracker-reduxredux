"""Verify equivalent catalogue screening before a separately sealed speed trial."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import signal
import time

import numpy as np

from ds23_recovery_screen_geometry import install_for_screening
from investigate_ds23_adaptive_failures import phase_widths
import run_ds23_combined_recovery_full as inference
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_recovery_screen_speed'
PILOT=ROOT/'reports/2026_10_20_ds23_combined_recovery_frequency_only'


def digest(value):
    def encode(x):
        if isinstance(x,np.ndarray):return x.tolist()
        if isinstance(x,np.generic):return x.item()
        raise TypeError(type(x).__name__)
    return hashlib.sha256(json.dumps(value,default=encode,sort_keys=True,allow_nan=False).encode()).hexdigest()


def benchmark(case):
    path=OUT/(case+'.json');OUT.mkdir(parents=True,exist_ok=True)
    if path.exists():return read(path)
    inference.prepare()
    record=read(inference.OUT/case/'result.json')
    p,x,_=inference.reconstruct(case,record,'c0')
    powers=np.asarray(record['policy_model']['powers']);model=record['policy_model']['hyper']
    phase_widths(p.scan,list(range(len(p.scan.norads))));p.calculate(x);p.state(x)
    import ds23_combined_recovery_search as screen
    original=(screen.prepare_phase_geometry,screen.phase_linear_frequency)
    receipts=[]
    def timeout(*_):raise TimeoutError('600 second bounded screen benchmark exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(600)
    try:
        for name in ('original','frequency_only','frequency_only','original'):
            if name=='frequency_only':install_for_screening(screen)
            else:screen.prepare_phase_geometry,screen.phase_linear_frequency=original
            begin=time.perf_counter();result=screen.screen_blocks(p,x,powers,model,max_blocks=2)
            receipts.append(dict(method=name,seconds=time.perf_counter()-begin,complete_screen_sha256=digest(result)))
            write(OUT/(case+'_partial.json'),dict(case=case,receipts=receipts))
            print(case,receipts[-1],flush=True)
    finally:
        signal.alarm(0);screen.prepare_phase_geometry,screen.phase_linear_frequency=original
    equivalent=len({r['complete_screen_sha256'] for r in receipts})==1
    times={k:float(np.median([r['seconds'] for r in receipts if r['method']==k])) for k in ('original','frequency_only')}
    result=dict(case=case,receipts=receipts,complete_proposal_output_bitwise_equal=equivalent,
        median_seconds=times,measured_screen_speedup=times['original']/times['frequency_only'],
        order='original,optimized,optimized,original; phase-prior and posterior warmup excluded equally',
        catalogue_candidates=len(p.scan.norads),GPS_used=False,future_TLE_used=False,
        observed_result_sha256=sha(inference.OUT/case/'result.json'),
        source_sha256={q.name:sha(q) for q in (Path(__file__),ROOT/'tools/ds23_recovery_screen_geometry.py',ROOT/'tools/ds23_combined_recovery_search.py')},
        fitted_geometry_likelihood_priors_and_gates_unchanged=True)
    write(path,result)
    if not equivalent:raise ValueError('complete catalogue proposal output changed; no speed pilot permitted')
    return result


def pilot(case):
    proof=read(OUT/(case+'.json'))
    if not proof['complete_proposal_output_bitwise_equal']:raise ValueError('missing exact screening proof')
    base=inference.prepare();PILOT.mkdir(parents=True,exist_ok=True)
    protocol=copy.deepcopy(base)
    for path in (Path(__file__),ROOT/'tools/ds23_recovery_screen_geometry.py'):
        protocol['source_sha256'][path.name]=sha(path)
    protocol.update(experiment='frequency_only_equivalent_screening',
        execution_override='Only catalogue-screen geometry omits derivatives that are never consumed; position fitting unchanged',
        benchmark_sha256=sha(OUT/(case+'.json')),engineering_pilot_case=case,
        same_catalogue_phases_aliases_masks_RF_gates_priors_and_900_second_budget=True,
        pilot_is_previously_inspected_not_generalization_validation=True)
    target=PILOT/'protocol.json'
    if target.exists():
        if read(target)!=protocol:raise ValueError('speed trial protocol changed')
    else:write(target,protocol)
    inference.OUT=PILOT
    import ds23_combined_recovery_search as screen
    install_for_screening(screen)
    result=inference.run_case(case)
    write(PILOT/'pilot_execution.json',dict(result=result,protocol_sha256=sha(target)))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',default='DS23-0268')
    parser.add_argument('--stage',choices=('benchmark','pilot'),default='benchmark')
    args=parser.parse_args();print(benchmark(args.case) if args.stage=='benchmark' else pilot(args.case),flush=True)
