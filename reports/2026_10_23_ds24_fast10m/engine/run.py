"""Supervise fresh DS24 paired stages with explicit per-case timeouts."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import subprocess
import time
from run_baseline import OUT,ENV,PYTHON,REPO,one as baseline,run_command


def variants(case):
    folder=OUT/case;folder.mkdir(exist_ok=True)
    began=time.monotonic()
    try:
        with (folder/'variants.log').open('a') as log:
            returncode=run_command([str(PYTHON),str(OUT/'engine/variants.py'),'--case',case],log,1200)
        path=OUT/'results'/(case+'.json')
        status=json.loads(path.read_text())['status'] if path.exists() else 'no_result'
        return dict(case=case,status=status,returncode=returncode,seconds=time.monotonic()-began)
    except Exception as exc:return dict(case=case,status='execution_failed',error=repr(exc),seconds=time.monotonic()-began)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['baseline','variants'],required=True)
    p.add_argument('--cases',nargs='+');p.add_argument('--workers',type=int,default=2);p.add_argument('--limit',type=int)
    a=p.parse_args()
    if not 1<=a.workers<=30:p.error('workers must be 1..30')
    allowed={m['dataset_label'] for m in json.loads((OUT/'sample.json').read_text())['selected']}
    cases=a.cases or sorted(allowed)
    if not set(cases)<=allowed:p.error('case outside sealed DS24 cohort')
    if a.limit:cases=cases[:a.limit]
    receipts=[];began=time.monotonic()
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for f in as_completed([pool.submit(baseline if a.stage=='baseline' else variants,c) for c in cases]):
            row=f.result();receipts.append(row);print(json.dumps(row),flush=True)
            (OUT/(a.stage+'_execution.json')).write_text(json.dumps(dict(cases=cases,receipts=receipts,completed=len(receipts),total=len(cases),all_terminal=len(receipts)==len(cases),seconds=time.monotonic()-began),indent=2)+'\n')
