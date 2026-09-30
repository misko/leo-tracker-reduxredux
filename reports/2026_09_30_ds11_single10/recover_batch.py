"""Wait for original export batch, then stage-recover failed units with three workers."""
import concurrent.futures,json,subprocess,time
from pathlib import Path
from export_batch import HERE,PY

def run(row):
    unit=row['unit'];start=time.monotonic()
    with (HERE/'receipts'/f'{unit}.recovery.log').open('x') as f:
        p=subprocess.run(['sudo','-n','env','OPENBLAS_NUM_THREADS=1','timeout','--kill-after=10','180',PY,str(HERE/'recover_export.py'),unit],stdout=f,stderr=subprocess.STDOUT)
    r=dict(unit=unit,exit_code=p.returncode,wall_s=time.monotonic()-start,state='validated' if p.returncode==0 and (HERE/'exports'/unit/'validated.json').exists() else 'failed')
    (HERE/'receipts'/f'{unit}.recovery.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True);return r

if __name__=='__main__':
    while not (HERE/'export-batch.json').exists():time.sleep(2)
    rows=[r for r in json.loads((HERE/'export-batch.json').read_text()) if r['state']=='failed']
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,rows))
    (HERE/'recovery-batch.json').write_text(json.dumps(results,indent=2))
