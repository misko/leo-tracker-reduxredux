"""Propagate CFO uncertainty while preserving the existing 40 Hz noise floor.

The unfloored pilot explicitly failed the existing finite-noise contract on six
recordings. Its files remain intact and are not evaluated as a complete cohort.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

import probe_ds23_fft_grid_uncertainty as adapter
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_fft_grid_uncertainty_floor'
original_hashes=adapter.hashes
original_prepare=adapter.prepare
original_correct=adapter.corrected_scan


def hashes():
    return dict(original_hashes(),**{str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))})


def prepare():
    p=original_prepare()
    if 'preserved_original_noise_floor_hz' not in p:
        p.update(preserved_original_noise_floor_hz=40.,
            inverse_noise_Jacobian='max(40 Hz, sigma_original * d inverse_CFO / d native_CFO)',
            reason_for_amendment='unfloored delta method violates original minimum-noise contract on six of forty recordings',
            failed_unfloored_run='reports/2026_10_20_ds23_fft_grid_uncertainty',
            floor_required_by_existing_contract_not_tuned_from_GPS=True)
        write(OUT/'protocol.json',p)
    return p


def corrected_scan(scan,case,protocol):
    changed,receipt=original_correct(scan,case,protocol)
    noise=changed.fixed_window_noise['per_observation_noise_sigma_hz']
    below=sum(value<40. for value in noise.values())
    for oid,value in noise.items():
        noise[oid]=max(40.,value)
    receipt.update(minimum_noise_floor_hz=40.,points_reaching_existing_floor=below)
    return changed,receipt


def bind():
    adapter.OUT=OUT;adapter.hashes=hashes;adapter.prepare=prepare
    adapter.corrected_scan=corrected_scan;adapter.bind()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('development','confirmation','evaluate'),required=True)
    args=parser.parse_args();bind();protocol=prepare()
    if args.stage=='evaluate':
        import evaluate_ds23_fft_grid_position as report
        report.OUT=OUT;report.prepare=prepare;report.main()
    else:
        cases=protocol[args.stage+'_cases'];receipts=[]
        with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
            futures={pool.submit(adapter.engine.run,c):c for c in cases}
            for f in as_completed(futures):
                try:
                    receipts.append(f.result())
                except Exception as exc:
                    receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts,completed=len(receipts),total=len(cases)))
        write(OUT/(args.stage+'_execution.json'),dict(all_terminal=True,receipts=receipts))
        print('Terminal',len(receipts),'errors',sum('error' in r for r in receipts),flush=True)
