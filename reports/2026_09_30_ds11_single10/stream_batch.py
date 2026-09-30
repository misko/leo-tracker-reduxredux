"""Schedule frozen single-scan jobs as their validated input exports finish."""
import concurrent.futures,hashlib,json,time
from pathlib import Path
from batch import scan,METHODS
HERE=Path(__file__).resolve().parent
plan=json.loads((HERE/'export-plan.json').read_text())
(HERE/'runs').mkdir(exist_ok=True);(HERE/'unit-plans').mkdir(exist_ok=True)
submitted=set();futures=[];failed=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    while len(submitted)<32:
        for i,row in enumerate(plan['captures']):
            if i in submitted:continue
            valid=HERE/'exports'/row['unit_id']/'validated.json'
            receipt=HERE/'receipts'/f"{row['unit_id']}.json"
            if valid.exists():
                result=json.loads(valid.read_text());entry=result['input']
                assert entry['session_id']==row['session_id'] and entry['manifest_sha256']==row['manifest_sha256']
                for a in entry['artifacts']:assert 'sha256:'+hashlib.sha256(Path(a['path']).read_bytes()).hexdigest()==a['sha256']
                inputs=[None]*32;inputs[i]=entry
                path=HERE/'unit-plans'/f'{i:02d}.json'
                with path.open('x') as f:json.dump(dict(config=plan['config'],inputs=inputs),f,indent=2)
                futures.append(pool.submit(scan,i,path));submitted.add(i)
                print('Queued single scan',i,row['unit_id'],flush=True)
            elif receipt.exists() and json.loads(receipt.read_text())['state']=='failed':
                for method in METHODS:
                    (HERE/'runs'/f'{i:02d}_{method}.receipt.json').write_text(json.dumps(dict(index=i,method=method,exit_code=66,wall_s=0.,reason='input_export_failed')))
                submitted.add(i);failed.append(i)
        if len(submitted)<32:time.sleep(2)
    results=[f.result() for f in futures]
(HERE/'batch.json').write_text(json.dumps(dict(results=results,input_failed_indices=failed),indent=2))
