"""One additional three-iteration orbit-free GLRT pass on immutable saved IQ.

Inputs: measured candidate frequency, measured epoch and IQ only. No orbit,
satellite identity, receiver calibration, association, or location is loaded.
Keep the previously evaluated maximum if a restart cannot improve its margin.
"""
import argparse
import hashlib
import inspect
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE=Path(__file__).resolve().parent
BENCH=HERE.parent/'2026_10_04_ds13_18_scan_benchmark'
sys.path.insert(0,str(BENCH))
from refinement import refine, winners
from iq_visits import read_event

INPUTS=Path('/srv/bulk/leo/ds13-18scan-benchmark-20261004/inputs-v2')
STORES={}


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def improve(score,row,prior):
    old=prior['refinement']
    epoch=old.get('epoch',row['integer_epoch_sample']+row['fractional_epoch_offset_samples'])
    new=refine(score,prior['output_hz'],epoch,iterations=3)
    retain=(old['status']=='refined' and (new['status']!='refined' or new['margin']<=old['margin']))
    chosen=dict(old if retain else new)
    return chosen,dict(retained_previous=retain,attempt_status=new['status'],attempt_calls=new['calls'],
                      attempted_margin=new.get('margin'),starting_hz=prior['output_hz'],starting_epoch=epoch)


def worker(task):
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
    import numpy as np
    scan,signature,visit_index,rows,priors=task
    session=signature['session_id']
    if session not in STORES:
        store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True)
        published=store.inspect(session)
        assert published.manifest_sha256==signature['manifest_sha256']
        STORES[session]=(store,published)
    store,published=STORES[session]
    fs=int(published.manifest.receipt.plan.geometry.sample_rate_hz);assert fs==2_500_000
    visit,iq=read_event(store,published,visit_index)
    signals={};caches={};results=[];calls=0;parity=[]
    started=time.monotonic()
    for row,prior in zip(rows,priors):
        key=(row['receiver'],row['probe_start_ms'])
        if key not in signals:
            begin=row['probe_start_ms']*fs//1000
            block=iq[begin:begin+fs//50,row['receiver'],:];assert len(block)==fs//50
            signals[key]=(block[:,0].astype(float)+1j*block[:,1].astype(float))/32768.
            caches[key]={}
        def score(frequency,epoch):
            nonlocal calls
            cache=caches[key];identity=(float(frequency),float(epoch))
            if identity not in cache:
                integer=int(round(epoch))
                v=conditioned_glrt64_score(signals[key],fs,epoch_sample=integer,
                    fractional_epoch_offset_samples=epoch-integer,acquired_cfo_hz=float(frequency),
                    edge=visit.event.target.edge,glrt_size=4096)
                cache[identity]=dict(tracking_cfo_hz=v.tracking_cfo_hz,margin=v.margin,exact=v.exact_score,control=v.control_score)
                calls+=1
            return cache[identity]
        old=prior['refinement']
        if not parity and old['status']=='refined':
            reconstructed=score(old['center_hz'],old['epoch'])
            for field,value in reconstructed.items():
                np.testing.assert_allclose(value,old[field],atol=1e-8,rtol=1e-12,err_msg=field)
            parity.append(row['row_index'])
        chosen,audit=improve(score,row,prior)
        output=chosen['tracking_cfo_hz'] if chosen['status']=='refined' else prior['output_hz']
        results.append(dict(row_index=row['row_index'],candidate_id=row['candidate_id'],probe_key=row['probe_key'],
            original_hz=row['original_hz'],original_margin=row['original_margin'],output_hz=output,
            refinement=chosen,additional_pass=audit))
    return dict(scan=scan,visit_index=visit_index,signature=signature,records=results,
        scorer_calls=calls,parity_rows=parity,elapsed_s=time.monotonic()-started)


def main():
    from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
    p=argparse.ArgumentParser();p.add_argument('--scans',nargs='+',default=[f'N{i:02}' for i in range(1,17)])
    p.add_argument('--workers',type=int,default=6);p.add_argument('--maximum-visits',type=int)
    args=p.parse_args();tasks=[];sources={};completed={s:[] for s in args.scans}
    for scan in args.scans:
        obs_path=INPUTS/scan/'observations.json';prior_path=INPUTS/scan/'refinement/refined.json'
        obs=json.loads(obs_path.read_text());prior=json.loads(prior_path.read_text())
        scorer_path=Path(inspect.getfile(conditioned_glrt64_score));scorer_hash=digest(scorer_path)
        expected=[v.removeprefix('sha256:') for k,v in prior['summary']['signature']['sources'].items() if k.endswith('/pilot_methods.py')]
        assert expected==[scorer_hash], 'Use the same archived GLRT scorer, not the dirty workspace scorer'
        signature=dict(session_id=obs['summary']['session_id'],manifest_sha256=obs['signature']['manifest_sha256'],
            observations_sha256=digest(obs_path),parent_sha256=digest(prior_path),implementation_sha256=digest(__file__),
            scorer_sha256=scorer_hash,refinement_sha256=digest(BENCH/'refinement.py'))
        sources[scan]=(signature,len(obs['records']))
        byrow={r['row_index']:r for r in prior['records']};grouped=defaultdict(list)
        for row in obs['records']:grouped[row['probe_key'][0]].append(row)
        folder=HERE/'refinement'/scan;folder.mkdir(parents=True,exist_ok=True)
        added=0
        for visit,rows in sorted(grouped.items()):
            target=folder/f'visit-{visit:05d}.json'
            if target.exists():
                saved=json.loads(target.read_text());assert saved['signature']==signature
                completed[scan].append(saved)
            elif args.maximum_visits is None or added<args.maximum_visits:
                tasks.append((scan,signature,visit,rows,[byrow[r['row_index']] for r in rows]));added+=1
    begun=time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(worker,task):task for task in tasks}
        for i,future in enumerate(as_completed(futures),1):
            r=future.result();scan=r['scan']
            target=HERE/'refinement'/scan/f'visit-{r["visit_index"]:05d}.json'
            with target.open('x') as stream:json.dump(r,stream,allow_nan=False)
            completed[scan].append(r)
            if i%10==0 or len(tasks)<=10:
                print('EXTRA PASS',i,'/',len(tasks),scan,'candidates',len(r['records']),'elapsed',round(time.monotonic()-begun,1),flush=True)
    for scan,visits in completed.items():
        signature,total=sources[scan];records=sorted([r for v in visits for r in v['records']],key=lambda r:r['row_index'])
        assert len(records)==len({r['row_index'] for r in records})
        summary=dict(status='complete' if len(records)==total else 'partial',signature=signature,
            parent_sha256=signature['parent_sha256'],total_candidates=total,completed_candidates=len(records),
            visits=len(visits),scorer_calls=sum(v['scorer_calls'] for v in visits),
            compute_s=sum(v['elapsed_s'] for v in visits),retained_previous=sum(r['additional_pass']['retained_previous'] for r in records),
            parity_verified_visits=sum(bool(v['parity_rows']) for v in visits),orbit_information_used=False)
        result=dict(summary=summary,records=records,top_rows=winners(records))
        target=HERE/'refinement'/scan/('refined.json' if summary['status']=='complete' else 'progress.json')
        target.write_text(json.dumps(result,allow_nan=False))
        print(json.dumps(dict(scan=scan,**summary)),flush=True)


if __name__=='__main__':main()
