"""Public saved-contract audit; no localization, RF fit, raw IQ or GPS read."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from ds23_delivery_clock_bounds import delivery_interval
from run_algo01_ds23_sample import ROOT,read,write,sha

SOURCE=ROOT/'reports/2026_10_19_algo02_ds23_full'
OUT=ROOT/'reports/2026_10_20_ds23_delivery_clock_bounds'


def run(case):
    path=SOURCE/case/'tracking.json';receipt=SOURCE/case/'receipt.json'
    interval=delivery_interval(read(path),read(receipt)['origin_utc_ns'])
    return dict(case=case,interval=interval,tracking_sha256=sha(path),receipt_sha256=sha(receipt))


def main():
    OUT.mkdir(exist_ok=True)
    manifest=read(ROOT/'reports/2026_10_18_ds23_post_ds22/manifest.json')
    cases=[r['dataset_label'] for r in manifest['members']
           if (SOURCE/r['dataset_label']/'tracking.json').exists() and (SOURCE/r['dataset_label']/'receipt.json').exists()]
    rows=[];errors=[]
    with ProcessPoolExecutor(max_workers=12) as pool:
        futures={pool.submit(run,c):c for c in cases}
        for f in as_completed(futures):
            try:rows.append(f.result())
            except Exception as exc:errors.append(dict(case=futures[f],error=repr(exc)))
    reductions=[r['interval']['original_interval']['width_s']-r['interval']['width_s']
                for r in rows if r['interval']['delivery_bound_used']]
    write(OUT/'audit.json',dict(rows=rows,errors=errors,population=len(manifest['members']),
        available_contracts=len(cases),all_terminal=True,
        tighter_bounds=len(reductions),median_interval_reduction_s=float(np.median(reductions)) if reductions else 0.,
        nominal_midpoint_excluded=sum(not r['interval']['lower_s']<=0<=r['interval']['upper_s'] for r in rows),
        no_GPS_RF_fit_TLE_or_IQ_read=True,conditional_on_declared_sample_rate=True,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'tools/ds23_delivery_clock_bounds.py')}))
    print('Contracts',len(cases),'errors',len(errors),'tightened',len(reductions),'median reduction',np.median(reductions),flush=True)


if __name__=='__main__':main()
