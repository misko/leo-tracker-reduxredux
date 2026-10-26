"""Fixed-precision count and family/RX/time matched evidence controls."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import signal
import sys
import time
import traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import *

OUT=ROOT/'matched'


def masks(keep,m,seed):
    low=keep & (m['channel']<=4);high=keep & (m['channel']>4)
    result={'full':keep.copy(),'low':low,'high':high};counts=[]
    for rep in range(3):
        rng=np.random.default_rng(seed+rep)
        large,small,name=(low,high,'low') if low.sum()>=high.sum() else (high,low,'high')
        count=np.zeros(len(keep),bool)
        count[rng.choice(np.flatnonzero(large),size=int(small.sum()),replace=False)]=True
        result[f'count_{name}_{rep}']=count
        l=np.zeros(len(keep),bool);h_=l.copy()
        cells={}
        for i in np.flatnonzero(keep):
            key=(int(m['family'][i]),int(m['receiver'][i]),int(np.floor(m['time'][i]/20)))
            cells.setdefault(key,{'low':[],'high':[]})['low' if low[i] else 'high'].append(i)
        for key,pair in sorted(cells.items()):
            n=min(len(pair['low']),len(pair['high']))
            if n:
                l[rng.choice(pair['low'],n,replace=False)]=True
                h_[rng.choice(pair['high'],n,replace=False)]=True
            if rep==0:counts.append(dict(cell=key,low=len(pair['low']),high=len(pair['high']),matched_each=n))
        result[f'matched_low_{rep}']=l;result[f'matched_high_{rep}']=h_
    return result,counts


def freeze():
    cases={}
    for case in CASES:
        d=context(case);p=d['base'];meta=metadata(p)
        choices,cells=masks(d['keep'],meta,2026102602+int(case[-4:]));packets={}
        for arm in ARMS:
            saved=d['arms'][arm];p=build(d,'default',arm,saved['phase_reference'])
            c=p.calculate(saved['endpoint_east_north_km'])
            packets[arm]=dict(case=case,arm=arm,noise_precision=c['noise_precision'],
                coefficient_prior_precision=c['coefficient_prior_precision'],layout=frozen.layout(p))
        cases[case]=dict(choices={k:np.flatnonzero(v) for k,v in choices.items()},
            ids={k:meta['ids'][v] for k,v in choices.items()},counts={k:int(v.sum()) for k,v in choices.items()},
            cells=cells,packets=packets,total_curved_coordinates=len(d['keep']))
    sources=source_manifest();sources[str(Path(__file__))]=sha(__file__)
    write(OUT/'protocol.json',dict(cases=cases,sources=sources,GPS_used=False,
        precision='Original full-data same-arm noise and nuisance-prior precision frozen',predictive_entries_used=False,
        identities_and_support_fixed=True,regional_pipeline_rerun=False))


def solve(d,arm,packet):
    x=np.zeros(2);ref=np.zeros(len(d['means']));history=[]
    for epoch in range(5):
        p=frozen.build(d,arm,ref,packet);f=fit(p,x,iterations=48);x=np.asarray(f['parameters'])
        phase=p.state(x)['phases'][p.labels];change=float(np.max(abs(np.clip(phase,-15,15)-ref)))
        history.append(dict(epoch=epoch,fit=f,phase_change_s=change));ref=np.clip(phase,-15,15)
    c=p.calculate(x)
    assert np.array_equal(c['coefficient_prior_precision'],np.asarray(packet['coefficient_prior_precision']))
    assert np.array_equal(c['noise_precision'],np.asarray(packet['noise_precision']))
    return dict(endpoint_east_north_km=x,phase_reference=p.reference,history=history,
        maximum_unclipped_phase_s=float(np.max(abs(phase))),final_phase_change_s=change,
        frequency_RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),
        objective=c['negative_twice_elbo'],points=int(p.keep.sum()),
        phase_checks_pass=bool(change<=.01 and np.max(abs(phase))<=15.000001),
        production_adoption_test=False)


def one(case):
    started=time.monotonic();cap(600);protocol=load(OUT/'protocol.json');results=[]
    try:
        verify(protocol['sources']);d=context(case);dd=dict(d,entries=[])
        data=protocol['cases'][case]
        for name,indices in data['choices'].items():
            keep=np.zeros(len(d['keep']),bool);keep[indices]=True
            for arm in ARMS:
                row=dict(case=case,method=name,arm=arm,GPS_used=False)
                try:
                    if not keep.any():row.update(status='unavailable',reason='empty matched mask')
                    else:row.update(status='complete',**solve(dict(dd,keep=keep),arm,data['packets'][arm]))
                except Exception as e:row.update(status='failed',error=repr(e),traceback=traceback.format_exc())
                results.append(row)
                write(OUT/'results'/f'{case}_{name}_{arm}.json',row)
        verify(protocol['sources'])
    except Exception as e:
        results.append(dict(case=case,status='failed',error=repr(e),traceback=traceback.format_exc()))
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    write(OUT/'results'/f'{case}_summary.json',dict(rows=results,seconds=time.monotonic()-started,GPS_used=False))
    print(case,len(results),sum(r['status']=='complete' for r in results),'complete',round(time.monotonic()-started,2),flush=True)
    return results


def run():
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,CASES))
    write(OUT/'execution.json',dict(results=rows,GPS_used=False))
    write(OUT/'RF_seal.json',dict(files={str(p):sha(p) for p in OUT.rglob('*.json')},GPS_used=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run']);args=parser.parse_args()
    freeze() if args.action=='freeze' else run()
