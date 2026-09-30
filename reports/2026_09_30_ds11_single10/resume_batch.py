"""Resume after launcher failure, retaining originals and using installed Python directly."""
import concurrent.futures, hashlib, json, os, subprocess, time
from pathlib import Path
from batch import METHODS
HERE=Path(__file__).resolve().parent
PY='/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python'

def scan(i, path):
    for method in METHODS:
        name=f'{i:02d}_{method}';base=HERE/'runs'/name
        receipt=base.with_suffix('.receipt.json');result=base.with_suffix('.json')
        if result.exists():
            assert receipt.exists() and json.loads(receipt.read_text())['exit_code']==0
            continue
        retry=receipt.exists() or base.with_suffix('.log').exists()
        if retry:
            old=json.loads(receipt.read_text()) if receipt.exists() else {}
            assert old.get('exit_code') in (None,124,137,66),old
            log=base.with_suffix('.log')
            assert not log.exists() or not log.read_text().strip(),log
            if not receipt.exists():receipt.write_text(json.dumps(dict(index=i,method=method,exit_code=137,wall_s=None,reason='launcher_interrupted_before_python')))
        suffix='.retry' if retry else ''
        log=base.with_suffix(suffix+'.log');out=base.with_suffix(suffix+'.receipt.json')
        if out.exists():continue
        env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','PYTHONPATH':str(HERE.parents[1]),'SINGLE_BENCH_PLAN':str(path)}
        start=time.monotonic()
        with log.open('x') as f:
            p=subprocess.run(['sudo','-n','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1',f'SINGLE_BENCH_PLAN={path}',f'PYTHONPATH={HERE.parents[1]}','timeout','--kill-after=5s','90s','nice','-n','19',PY,str(HERE/'run.py'),str(i),method],env=env,stdout=f,stderr=subprocess.STDOUT)
        row=dict(index=i,method=method,exit_code=p.returncode,wall_s=time.monotonic()-start,python=PY)
        out.write_text(json.dumps(row,indent=2));print(json.dumps(row),flush=True)

def main():
    plan=json.loads((HERE/'export-plan.json').read_text());pending=set(range(32));futures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        while pending:
            for i in sorted(pending):
                row=plan['captures'][i];v=HERE/'exports'/row['unit_id']/'validated.json'
                if not v.exists():continue
                entry=json.loads(v.read_text())['input']
                assert entry['session_id']==row['session_id'] and entry['manifest_sha256']==row['manifest_sha256']
                for a in entry['artifacts']:assert 'sha256:'+hashlib.sha256(Path(a['path']).read_bytes()).hexdigest()==a['sha256']
                inputs=[None]*32;inputs[i]=entry;doc=dict(config=plan['config'],inputs=inputs)
                path=HERE/'unit-plans'/f'{i:02d}.json'
                if path.exists():assert json.loads(path.read_text())==doc
                else:path.write_text(json.dumps(doc,indent=2))
                futures.append(pool.submit(scan,i,path));pending.remove(i)
            if pending:time.sleep(2)
        for f in futures:f.result()
    (HERE/'resumed-batch.json').write_text(json.dumps(dict(state='terminal',scans=32)))

if __name__=='__main__':main()
