"""Bounded continuation of three timed-out scans whose initial fits completed.

Original benchmark files remain immutable. Copy verified scientific inputs to
a separate run directory and execute only the unmodified ALGO02 final stage.
No raw recordings or new RF collection are used.
"""

from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import os
import shutil
import time

from run_algo02_ds23 import ROOT,DEFAULT_RUN,THREAD_ENV,read,write,digest,verify_freeze,bounded_command

OUT=ROOT/'reports/2026_10_20_ds23_unavailable_recovery'
CASES=('DS23-0004','DS23-0080','DS23-0118')


def prepare():
    verify_freeze(DEFAULT_RUN);OUT.mkdir(exist_ok=True)
    path=OUT/'protocol.json'
    if path.exists():return read(path)
    bindings={}
    for case in CASES:
        old=read(DEFAULT_RUN/case/'execution_receipt.json')
        if old['code']!=124 or (DEFAULT_RUN/case/'algo02_result.json').exists():
            raise ValueError('recovery membership no longer matches original unavailable scans')
        if read(DEFAULT_RUN/case/'result.json')['status']!='complete':
            raise ValueError('saved initial inference incomplete')
        files=[DEFAULT_RUN/case/name for name in ('bank.npz','tracks.json','radio_noise.json',
            'observations.json','nominal_elements.json','receipt.json','previous.tle','tracking.json',
            'result.json','input_receipt.json','prepared.json')]
        files+=list((DEFAULT_RUN/'causal_prior'/case).iterdir())
        files += [DEFAULT_RUN/'causal_phase_history'/(case+suffix) for suffix in ('.json','_forecast.json')]
        sources={}
        for source in files:
            if not source.is_file():raise ValueError('expected local scientific input missing')
            relative=source.relative_to(DEFAULT_RUN);destination=OUT/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            before=digest(source)
            if not destination.exists():shutil.copyfile(source,destination)
            if digest(destination)!=before or digest(source)!=before:raise ValueError('recovery input copy changed')
            sources[str(relative)]=before
        bindings[case]=sources
    protocol=dict(cases=CASES,source_run=str(DEFAULT_RUN.relative_to(ROOT)),workers=3,
        per_case_timeout_seconds=300,only_stage='algo02',original_engine_unchanged=True,
        original_frozen_timeout_and_result_receipts_preserved=True,input_sha256=bindings,
        source_sha256=digest(Path(__file__)),no_GPS_future_TLE_raw_IQ_or_new_RF=True,
        no_original_404_population_error_replaced_or_retroactively_redefined=True)
    write(path,protocol);return protocol


def run(case):
    protocol=read(OUT/'protocol.json');directory=OUT/case
    output=directory/'recovery_receipt.json'
    if output.exists():return read(output)
    for name,expected in protocol['input_sha256'][case].items():
        if digest(OUT/name)!=expected or digest(DEFAULT_RUN/name)!=expected:
            raise ValueError('original or copied scientific inputs changed')
    verify_freeze(DEFAULT_RUN)
    command=[str(ROOT/'.venv/bin/python'),str(ROOT/'tools/algo02_scan.py'),
             '--run-dir',str(OUT),'--case',case,'--stage','algo02']
    env=dict(os.environ,PYTHONPATH='src:tools',PYTHONHASHSEED='0',**THREAD_ENV)
    start=time.monotonic()
    with (directory/'final_stage.log').open('a') as stream:
        code=bounded_command(command,stream,300,env)
    result_path=directory/'algo02_result.json'
    record=dict(case=case,exit_code=code,seconds=time.monotonic()-start,
        result_sha256=digest(result_path) if result_path.exists() else None,
        scientific_status=read(result_path)['status'] if result_path.exists() else 'unavailable',
        original_receipt_preserved=True)
    write(output,record);print(record,flush=True);return record


if __name__=='__main__':
    protocol=prepare();receipts=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(run,c):c for c in CASES}
        for future in as_completed(futures):
            try:receipts.append(future.result())
            except Exception as exc:receipts.append(dict(case=futures[future],error=repr(exc)))
            write(OUT/'progress.json',dict(receipts=receipts))
    write(OUT/'execution.json',dict(receipts=receipts,all_terminal=True))
