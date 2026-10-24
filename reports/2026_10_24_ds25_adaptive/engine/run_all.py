"""Process-isolated inference on the whole sealed comparison cohort."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import time
from run_baseline import OUT, one


if __name__=='__main__':
    members=json.loads((OUT/'sample.json').read_text())['selected']
    # Interleave formats and chronological ranks; no quality or GPS ordering.
    modes={mode:sorted([m for m in members if m['mode']==mode],key=lambda m:m['captured_utc_ns'])
           for mode in ('adaptive','fast')}
    cases=[]
    for i in range(max(map(len,modes.values()))):
        for mode in ('adaptive','fast'):
            if i<len(modes[mode]):cases.append(modes[mode][i]['dataset_label'])
    receipts=[];start=time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(one,c) for c in cases]):
            receipt=f.result();receipts.append(receipt)
            print(json.dumps(receipt),flush=True)
            output=dict(total=len(cases),completed=len(receipts),all_terminal=len(receipts)==len(cases),
                        seconds=time.monotonic()-start,receipts=receipts)
            p=OUT/'execution.json';tmp=p.with_suffix('.tmp')
            tmp.write_text(json.dumps(output,indent=2)+'\n');tmp.replace(p)
