"""GLRT-weighted greedy satellite selection over frozen N01--N16 mode pools.

Keep the 600 Hz gate, lane coherence (10 windows, 5 s span, <=5 s gaps),
exclusive windows, one timing mode per NORAD and satellite penalty 10.
This bounded prototype covers the greedy stage, not replacement repairs.
"""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
from marks import lane_marks


def compile_modes(records, receiver, channel):
    modes = []
    for record in records:
        rows=np.asarray(record['eligible_rows'],int)
        errors=np.asarray(record['residual_hz'],float)
        lanes=[]
        for rx,ch in sorted(set(zip(receiver[rows].tolist(),channel[rows].tolist()))):
            ids=np.flatnonzero((receiver[rows]==rx)&(channel[rows]==ch))
            ids=ids[np.argsort(abs(errors[ids]),kind='stable')]
            lanes.append((rows[ids],errors[ids]))
        modes.append(dict(number=record['catalog_number'],offset=record['offset_s'],
                          rows=rows,lanes=lanes))
    return modes


def coherent_support(mode, used, times, weights):
    selected=[]; residuals=[]
    for rows,errors in mode['lanes']:
        ids=np.flatnonzero((abs(errors)<=600)&~used[rows])
        ids=ids[np.argsort(times[rows[ids]],kind='stable')]
        for part in np.split(ids,np.flatnonzero(np.diff(times[rows[ids]])>5)+1):
            if len(part)>=10 and times[rows[part[-1]]]-times[rows[part[0]]]>=5:
                selected.extend(rows[part].tolist());residuals.extend(errors[part].tolist())
    rows=np.asarray(selected,int)
    tie=-.5*np.sum(np.asarray(residuals)**2)/200**2-.5*mode['offset']**2
    return dict(rows=rows,residuals=residuals,reward=float(weights[rows].sum()),tie=float(tie))


def greedy(records, receiver, channel, times, weights):
    times,weights=np.asarray(times),np.asarray(weights,float)
    if len(times)!=len(weights) or np.any(weights<=0) or np.any(~np.isfinite(weights)):
        raise ValueError('Positive finite per-window weights required')
    modes=compile_modes(records,np.asarray(receiver),np.asarray(channel))
    used=np.zeros(len(times),bool);chosen=set();assignments=[];selected=[]
    row_modes=[set() for _ in times]
    for i,m in enumerate(modes):
        for row in m['rows']:row_modes[row].add(i)
    cache=[coherent_support(m,used,times,weights) for m in modes]
    while True:
        available=[i for i,m in enumerate(modes) if m['number'] not in chosen and cache[i]['reward']>10]
        if not available:break
        i=max(available,key=lambda j:(cache[j]['reward'],cache[j]['tie'],-modes[j]['number'],-j))
        m,s=modes[i],cache[i]
        assert not used[s['rows']].any()
        used[s['rows']]=True;chosen.add(m['number'])
        selected.append(dict(catalog_number=m['number'],mode_index=i,offset_s=m['offset'],
                             windows=len(s['rows']),reward=s['reward']))
        assignments.extend(dict(row_index=int(r),catalog_number=m['number'],residual_hz=e)
                           for r,e in zip(s['rows'],s['residuals']))
        affected=set().union(*(row_modes[r] for r in s['rows']))
        for j in affected:
            if modes[j]['number'] not in chosen:cache[j]=coherent_support(modes[j],used,times,weights)
    return dict(assigned=len(assignments),satellites=len(chosen),assignments=assignments,
                selected=selected,objective=sum(v['reward'] for v in selected)-10*len(chosen))


def run_scan(task):
    scan,output=task
    from experiment import sweep, digest, HERE, serial
    _,saved,source,_,_=sweep.inputs(scan)
    meta=saved['input_metadata'];prior=Path(meta['association_source'])
    pool_path=prior.with_name('candidate-pool.json');pool=json.loads(pool_path.read_text())
    raw=meta['raw_sources']
    observation_path=next(Path(p) for p in raw if p.endswith('/observations.json'))
    refinement_path=next(Path(p) for p in raw if p.endswith('/refinement/refined.json'))
    for path in (observation_path,refinement_path):
        assert digest(path)==raw[str(path)]
    observations={r['row_index']:r for r in json.loads(observation_path.read_text())['records']}
    refined={r['row_index']:r for r in json.loads(refinement_path.read_text())['records']}
    original=pool['original_rows']
    rows=[observations[i] for i in original]
    times=np.asarray([r['time_s'] for r in rows]);rx=np.asarray([r['receiver'] for r in rows]);ch=np.asarray([r['channel'] for r in rows])
    assert len({r['group_id'] for r in rows})==len(rows)
    margin=np.asarray([refined[i]['refinement'].get('margin',refined[i]['original_margin']) for i in original])
    marks=lane_marks(margin,rx,ch);shuffle=lane_marks(margin,rx,ch,shuffle=True)
    results=[]
    for arm in ('fitted-c','zero-c'):
        archive=json.loads(prior.with_name(f'{arm}.json').read_text())
        baseline=None
        for mode,weights in [('control',np.ones(len(rows))),('weighted-support',1+.5*marks),('shuffled-support',1+.5*shuffle)]:
            result=greedy(pool['arms'][arm],rx,ch,times,weights)
            assigned={original[a['row_index']]:a['catalog_number'] for a in result['assignments']}
            if baseline is None:
                baseline=assigned
                expected={a['row_index']:a['catalog_number'] for a in archive['initial']['assignments']}
                assert assigned==expected,(scan,arm,'greedy control mismatch')
                assert result['objective']==archive['initial']['objective']
            result.update(scan=scan,arm=arm,mode=mode,denominator=len(rows),scope=__doc__,
                mean_weight=float(weights.mean()),gained_windows=len(set(assigned)-set(baseline)),
                lost_windows=len(set(baseline)-set(assigned)),
                relabeled_windows=sum(assigned[r]!=baseline[r] for r in set(assigned)&set(baseline)),
                added_satellites=sorted(set(assigned.values())-set(baseline.values())),
                removed_satellites=sorted(set(baseline.values())-set(assigned.values())),
                pool_source=str(pool_path),pool_sha256=digest(pool_path),
                original_rows=original,weights_sha256=__import__('hashlib').sha256(weights.tobytes()).hexdigest(),
                baseline_greedy_reproduced=mode=='control')
            for a in result['assignments']:a['row_index']=original[a['row_index']]
            results.append(result)
    target=Path(output)/f'{scan}.json';target.write_text(json.dumps(results,default=serial,indent=2,allow_nan=False))
    print(scan,'association prototypes complete',flush=True)
    return [{k:v for k,v in r.items() if k not in ('assignments','selected','original_rows')} for r in results]


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    results=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run_scan,(f'N{i:02d}',str(args.output))) for i in range(1,17)]):
            results.extend(future.result())
    (Path(__file__).parent/'association_summary.json').write_text(json.dumps(results,indent=2))
