"""Bounded process-isolated runner for one prequalified DS24 model."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time

from matched_controls import HERE,digest,load_protocol,one,write


def main(protocol_path,workers):
    if not 1<=workers<=4:raise ValueError('at most four workers')
    protocol,_=load_protocol(protocol_path);began=time.monotonic();rows=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(one,c,protocol_path):c for c in protocol['cases']}
        for future in as_completed(futures):
            result=future.result()
            rows.append({k:result[k] for k in ('case','status','policy_source','adopted','seconds')})
    assert len(rows)==len(protocol['cases'])
    report=dict(model_id=protocol['model_id'],protocol_path=str(protocol_path),protocol_sha256=digest(protocol_path),
        rows=sorted(rows,key=lambda r:r['case']),all_terminal=True,cases=len(rows),
        trial_policy_cases=sum(r['adopted'] for r in rows),baseline_policy_cases=sum(not r['adopted'] for r in rows),
        failed_trials=sum(r['status']=='failed' for r in rows),seconds=time.monotonic()-began,
        workers=workers,GPS_used=False)
    write(HERE/'models'/protocol['model_id']/'execution.json',report)
    print('complete',report,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--protocol',type=Path,required=True);p.add_argument('--workers',type=int,default=4)
    a=p.parse_args();main(a.protocol,a.workers)
