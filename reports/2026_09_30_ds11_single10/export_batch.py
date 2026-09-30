"""Bounded export of frozen remaining inputs; no automatic retries."""
import concurrent.futures
import hashlib
import json
import subprocess
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PY='/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python'


def run(row):
    unit=row['unit_id'];folder=HERE/'exports'/unit;receipt=HERE/'receipts'/f'{unit}.json'
    valid=folder/'validated.json'
    if valid.exists():
        data=json.loads(valid.read_text())
        assert data['input']['session_id']==row['session_id']
        for artifact in data['input']['artifacts']:
            assert 'sha256:'+hashlib.sha256(Path(artifact['path']).read_bytes()).hexdigest()==artifact['sha256']
        return dict(unit=unit,state='reused_verified')
    if receipt.exists() or folder.exists():
        return dict(unit=unit,state='existing_unfinished_requires_review')
    start=time.monotonic()
    command=['sudo','-n','env','OPENBLAS_NUM_THREADS=1','timeout','--kill-after=10','180',PY,str(HERE/'export_one.py'),unit]
    with (HERE/'receipts'/f'{unit}.log').open('x') as log:
        process=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    result=dict(unit=unit,exit_code=process.returncode,elapsed_seconds=time.monotonic()-start,
                state='validated' if process.returncode==0 and valid.exists() else 'failed',command=command)
    with receipt.open('x') as out:json.dump(result,out,indent=2)
    print(unit,result['state'],round(result['elapsed_seconds'],1),flush=True)
    return result


if __name__=='__main__':
    (HERE/'receipts').mkdir(exist_ok=True)
    rows=json.loads((HERE/'export-plan.json').read_text())['captures']
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(run,rows))
    with (HERE/'export-batch.json').open('x') as out:json.dump(results,out,indent=2)
    print('Batch terminal',len(results),flush=True)
