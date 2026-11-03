"""Resume saved original inference in an isolated, bounded recovery directory.

Scan 64 completed all three ranked discovery branches before timing out in
unused zero-phase diagnostics. Scan 266 already has a complete discovery file.
Neither the original benchmark nor any RF recording is modified.
"""

from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import os
import shutil
import time

from run_algo02_ds23 import ROOT,DEFAULT_RUN,THREAD_ENV,read,write,digest,verify_freeze,bounded_command

OUT=ROOT/'reports/2026_10_20_ds23_initial_checkpoint_recovery'
CASES=('DS23-0064','DS23-0266')


def prepare():
    verify_freeze(DEFAULT_RUN);OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():return read(OUT/'protocol.json')
    bindings={}
    for case in CASES:
        source=DEFAULT_RUN/case;destination=OUT/case;destination.mkdir(exist_ok=True)
        if read(source/'execution_receipt.json')['code']!=124 or (source/'result.json').exists():
            raise ValueError('original checkpoint status changed')
        names=('bank.npz','tracks.json','radio_noise.json','observations.json','nominal_elements.json',
               'receipt.json','previous.tle','tracking.json','input_receipt.json','prepared.json')
        files=[source/name for name in names]
        files+=list((DEFAULT_RUN/'causal_prior'/case).iterdir())
        files += [DEFAULT_RUN/'causal_phase_history'/(case+suffix) for suffix in ('.json','_forecast.json')]
        discovery=source/'fit_radio_noise.json'
        files.append(discovery if discovery.exists() else source/'progress_radio_noise.json')
        bindings[case]={}
        for path in files:
            if not path.is_file():raise ValueError('local scientific source missing')
            relative=path.relative_to(DEFAULT_RUN);target=OUT/relative
            target.parent.mkdir(parents=True,exist_ok=True);before=digest(path)
            if not target.exists():shutil.copyfile(path,target)
            if digest(target)!=before or digest(path)!=before:raise ValueError('checkpoint copy changed')
            bindings[case][str(relative)]=before
        if not discovery.exists():
            checkpoint=read(source/'progress_radio_noise.json')
            if checkpoint['GPS_used'] or [r['hypothesis'] for r in checkpoint['choices']]!=[0,1,2]:
                raise ValueError('all three frozen discovery finalists must be complete')
            winner=min(checkpoint['choices'],key=lambda r:r['arms']['c0']['fit']['score'])
            write(destination/'fit_radio_noise.json',dict(checkpoint,
                status='all_three_inference_branches_checkpoint_complete',selected_hypothesis=winner['hypothesis'],
                checkpoint_source_sha256=digest(source/'progress_radio_noise.json'),
                diagnostic_zero_phase_controls_not_reconstructed=True,
                unique_proposed_hypothesis_count_unknown=True,
                branch_cap_verified_by_original_frozen_source=True))
    protocol=dict(cases=CASES,workers=2,per_case_total_timeout_s=300,
        stages=['initial','algo02'],input_sha256=bindings,source_sha256=digest(Path(__file__)),
        original_engine_unchanged=True,original_benchmark_and_timeout_receipts_preserved=True,
        no_GPS_future_TLE_raw_IQ_or_new_RF=True,discovery_68_incomplete_not_accepted_as_finished=True)
    write(OUT/'protocol.json',protocol);return protocol


def run(case):
    protocol=read(OUT/'protocol.json');directory=OUT/case;receipt=directory/'recovery_receipt.json'
    if receipt.exists():return read(receipt)
    for path,expected in protocol['input_sha256'][case].items():
        if digest(DEFAULT_RUN/path)!=expected or digest(OUT/path)!=expected:raise ValueError('checkpoint source changed')
    verify_freeze(DEFAULT_RUN);started=time.monotonic();stages=[]
    env=dict(os.environ,PYTHONPATH='src:tools',PYTHONHASHSEED='0',**THREAD_ENV)
    with (directory/'recovery.log').open('a') as stream:
        for stage in ('initial','algo02'):
            command=[str(ROOT/'.venv/bin/python'),str(ROOT/'tools/algo02_scan.py'),
                     '--run-dir',str(OUT),'--case',case,'--stage',stage]
            code=bounded_command(command,stream,max(1,300-(time.monotonic()-started)),env)
            stages.append(dict(stage=stage,exit_code=code))
            if code:break
    result=directory/'algo02_result.json'
    record=dict(case=case,stages=stages,seconds=time.monotonic()-started,
        result_sha256=digest(result) if result.exists() else None,
        status=read(result)['status'] if result.exists() else 'unavailable')
    write(receipt,record);print(record,flush=True);return record


if __name__=='__main__':
    prepare();receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(run,c):c for c in CASES}
        for future in as_completed(futures):
            try:receipts.append(future.result())
            except Exception as exc:receipts.append(dict(case=futures[future],error=repr(exc)))
            write(OUT/'progress.json',dict(receipts=receipts))
    write(OUT/'execution.json',dict(receipts=receipts,all_terminal=True))
