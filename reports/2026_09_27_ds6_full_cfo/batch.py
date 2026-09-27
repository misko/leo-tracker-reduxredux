"""Run a bounded batch of already-exported DS6 scans in inventory order."""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor

from run_baseline import HERE,REPORTS,run


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=6);parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.limit<=12 or not 1<=args.workers<=3:parser.error('Bound batches to 1..12 scans and 1..3 workers')
    protocol=json.loads((HERE/'protocol.json').read_text())
    selected=[s for s in protocol['sessions'] if not (HERE/f'{s}.json').exists()
        and (REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{s}-plan.json').exists()][:args.limit]
    print(json.dumps(dict(batch=selected)),flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for _ in pool.map(run,selected):pass
