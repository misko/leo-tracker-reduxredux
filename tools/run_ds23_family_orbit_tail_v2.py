"""Current-archive replay of the joint orbital-tail experiment.

The first pilot stopped at digest checks: its older transition cache belongs
to another causal-history export. Recompute transitions from the current sealed
histories; preserve the failed pilot and unchanged 20+20 cohort/algorithm.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

import probe_ds23_family_orbit_tail as engine
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_family_orbit_tail_v2'
OLD=engine.OUT
original_hashes=engine.hashes


def hashes():
    return dict(original_hashes(),**{str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))})


def bind():
    engine.OUT=OUT;engine.hashes=hashes
    protocol=engine.prepare()
    if 'causal_transition_cache_policy' not in protocol:
        original=read(OLD/'protocol.json')
        for key in ('development_cases','confirmation_cases'):
            if original[key]!=protocol[key]:raise ValueError('cohort changed during archive correction')
        protocol.update(causal_transition_cache_policy='recompute every transition from current sealed history; never reuse mismatched historical exports',
            failed_initial_pilot=str(OLD.relative_to(ROOT)),original_protocol_sha256=sha(OLD/'protocol.json'),
            first_pilot_made_no_new_RF_fit=True)
        write(OUT/'protocol.json',protocol)
    # The engine's cached path lookup now deliberately misses. Its current
    # history digest, cutoff and transition-target checks remain mandatory.
    engine.OLD=OUT/'no_external_transition_cache'
    return protocol


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('development','confirmation'),required=True)
    args=parser.parse_args();protocol=bind();receipts=[];cases=protocol[args.stage+'_cases']
    with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
        futures={pool.submit(engine.run,c):c for c in cases}
        for f in as_completed(futures):
            try:receipts.append(f.result())
            except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
            write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts,completed=len(receipts),total=len(cases)))
    write(OUT/(args.stage+'_execution.json'),dict(all_terminal=True,receipts=receipts))
    print('Terminal',len(receipts),'errors',sum('error' in r for r in receipts),flush=True)
