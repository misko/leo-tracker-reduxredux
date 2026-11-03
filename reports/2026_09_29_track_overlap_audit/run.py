import collections
import hashlib
import importlib.util
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent


def observation_key(receiver,rf,t,hz):
    return int(receiver),float(rf),int(round(float(t)*1e9)),int(round(float(hz)*1e6))


def compare(t1,y1,t2,y2):
    common,i,j=np.intersect1d(t1,t2,return_indices=True)
    if len(common)<8 or (common[-1]-common[0])/1e9<1:
        return None
    delta=y1[i]-y2[j]
    centered=delta-delta.mean()
    t=(common-common[0])/1e9;t-=t.mean()
    slope=float(t@centered/(t@t))
    return dict(overlap=len(common),span_s=float((common[-1]-common[0])/1e9),mean_difference_hz=float(delta.mean()),centered_rms_hz=float(np.sqrt(np.mean(centered**2))),difference_slope_hz_s=slope,detrended_rms_hz=float(np.sqrt(np.mean((centered-slope*t)**2))))


def main(ds):
    started=time.monotonic()
    frozen=json.loads((HERE/'manifest.json').read_text())
    for name,h in frozen['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h,name
    spec=importlib.util.spec_from_file_location('receiver',REPORTS/'2026_09_29_receiver_holdout/run.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    manifest=json.loads((REPORTS/'2026_09_29_scan_budget/manifest.json').read_text())
    pool=next(s for s in manifest['sets'] if s['dataset']==ds and s['count']==24)
    docs=helper.baseline.load_documents(dict(config=manifest['config'],inputs=[s['input'] for s in pool['scans']]))
    scans=[]
    for doc in docs:
        keys=collections.defaultdict(list)
        groups=collections.defaultdict(list)
        repeated_within=0
        for tr in doc['tracks']:
            times=np.rint(np.asarray(tr['times_s'])*1e9).astype(np.int64)
            y=np.asarray(tr['y'])
            repeated_within+=len(times)-len(set(times.tolist()))
            for t,hz,mask in zip(tr['times_s'],y,tr['mask'],strict=True):
                keys[observation_key(tr['receiver_id'],tr['rf_hz'],t,hz)].append((tr['track_id'],bool(mask)))
            groups[int(tr['receiver_id']),float(tr['rf_hz'])].append((tr['track_id'],times[tr['mask']],y[tr['mask']]))
        duplicates=[]
        for key,uses in keys.items():
            if len({u[0] for u in uses})>1:
                duplicates.append(dict(key=list(key),uses=uses,train_held_overlap=any(u[1] for u in uses) and any(not u[1] for u in uses)))
        pairs=[]
        for (rx,rf),tracks in groups.items():
            for a,b in itertools.combinations(tracks,2):
                result=compare(a[1],a[2],b[1],b[2])
                if result is not None:
                    pairs.append(dict(track_a=a[0],track_b=b[0],receiver=rx,rf_hz=rf,similar_history=result['centered_rms_hz']<=10,**result))
        scans.append(dict(session_id=doc['session_id'],tracks=len(doc['tracks']),observations=sum(len(t['y']) for t in doc['tracks']),repeated_within_track_timestamps=repeated_within,cross_track_reused_keys=len(duplicates),excess_cross_track_copies=sum(len({u[0] for u in d['uses']})-1 for d in duplicates),train_held_reused_keys=sum(d['train_held_overlap'] for d in duplicates),duplicates=duplicates,pairs=pairs))
    result=dict(dataset=ds,scans=scans,elapsed_seconds=time.monotonic()-started)
    with (HERE/f'{ds}.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    print(ds,dict(scans=len(scans),tracks=sum(s['tracks'] for s in scans),duplicate_keys=sum(s['cross_track_reused_keys'] for s in scans),train_held=sum(s['train_held_reused_keys'] for s in scans),eligible_pairs=sum(len(s['pairs']) for s in scans),similar_pairs=sum(p['similar_history'] for s in scans for p in s['pairs'])),flush=True)


if __name__=='__main__':
    main(sys.argv[1])
