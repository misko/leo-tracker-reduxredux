"""Launch each native comparison once its fresh reference is terminal."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
import time
from run import OUT,variants


def wait_then_run(case,deadline):
    receipt=OUT/case/'baseline_execution.json'
    while not receipt.exists() and time.monotonic()<deadline:time.sleep(1)
    if not receipt.exists():return dict(case=case,status='reference_wait_deadline')
    baseline=json.loads(receipt.read_text())
    if baseline['status']!='complete':return dict(case=case,status='reference_unavailable',reference=baseline)
    return variants(case)


if __name__=='__main__':
    cases=[r['dataset_label'] for r in json.loads((OUT/'sample.json').read_text())['selected']]
    deadline=time.monotonic()+1800;rows=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(wait_then_run,c,deadline) for c in cases]):
            row=f.result();rows.append(row);print(json.dumps(row),flush=True)
            (OUT/'variants_execution.json').write_text(json.dumps(dict(receipts=rows,total=len(cases),completed=len(rows),all_terminal=len(rows)==len(cases)),indent=2)+'\n')
