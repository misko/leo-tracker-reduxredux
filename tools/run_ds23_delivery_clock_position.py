"""Same common-clock algorithm with independently tightened causal intervals."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

import probe_ds23_bracketed_clock as engine
from ds23_delivery_clock_bounds import delivery_interval
from run_ds23_bracketed_clock_v2 import OUT as PREVIOUS,clock_problem
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_delivery_clock_position'
METADATA=ROOT/'reports/2026_10_20_ds23_delivery_clock_bounds/audit.json'
original_hashes=engine.hashes


def hashes():
    return dict(original_hashes(),**{str(p.relative_to(ROOT)):sha(p) for p in
        (Path(__file__),ROOT/'tools/ds23_delivery_clock_bounds.py',ROOT/'tools/run_ds23_bracketed_clock_v2.py')})


def bind():
    engine.OUT=OUT;engine.hashes=hashes;engine.clock_interval=delivery_interval;engine.clock_problem=clock_problem
    p=engine.prepare()
    if 'delivery_bounds_sha256' not in p:
        p.update(delivery_bounds_sha256=sha(METADATA),
            prior='uniform over intersection of original START bracket and last-sample-before-delivery inequalities',
            sample_rate_assumption='conditional on original declared sample rate, as in existing device-counter timing',
            no_minimum_network_latency_assumed=True,no_GPS_RF_or_TLE_fit_in_bounds=True,
            no_clock_uncertainty_propagated_to_predictive_covariance=True,
            previous_clock_experiment=str(PREVIOUS.relative_to(ROOT)))
        write(OUT/'protocol.json',p)
    if sha(METADATA)!=p['delivery_bounds_sha256']:raise ValueError('causal delivery audit changed')
    return p


def run(case):
    old=read(PREVIOUS/(case+'.json'))
    tracking=engine.SOURCE/case/'tracking.json'
    interval=delivery_interval(read(tracking),old['interval']['origin_utc_ns'])
    if all(abs(interval[k]-old['interval'][k])<=1e-12 for k in ('lower_s','upper_s')):
        write(OUT/(case+'.json'),dict(old,interval=interval,reused_scientific_fit=dict(
            path=str((PREVIOUS/(case+'.json')).relative_to(ROOT)),sha256=sha(PREVIOUS/(case+'.json')),
            reason='same exact timing bounds, observations, priors, model and optimization')))
        return dict(case=case,reused=True,paired_valid=old['paired_valid'])
    return engine.run(case)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('development','confirmation','evaluate'),required=True)
    args=parser.parse_args();protocol=bind()
    if args.stage=='evaluate':
        import evaluate_ds23_bracketed_clock as report
        report.OUT=OUT;report.bind=bind;report.main()
    else:
        cases=protocol[args.stage+'_cases'];receipts=[]
        with ProcessPoolExecutor(max_workers=12) as pool:
            futures={pool.submit(run,c):c for c in cases}
            for f in as_completed(futures):
                try:receipts.append(f.result())
                except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts,completed=len(receipts),total=len(cases)))
        write(OUT/(args.stage+'_execution.json'),dict(all_terminal=True,receipts=receipts))
        print('Terminal',len(receipts),'errors',sum('error' in r for r in receipts),flush=True)
