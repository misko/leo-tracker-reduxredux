"""Seal training-only scale fits, then evaluate disjoint historical objects."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
from model import fit,scores

HERE=Path(__file__).resolve().parent;PRIOR=HERE.parent/'historical_orbit_forecast'
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(indices,split,sources):
    rows=[]
    for i in indices:
        path=PRIOR/f'center-{i:02d}.json';doc=json.loads(path.read_text())
        for p,h in doc['sources'].items():assert digest(p)==h,p
        sources[str(path)]=digest(path)
        rows.extend(r for r in doc['rows'] if r['split']==split)
    return rows


def arrays(rows):
    return np.array([r['current_epoch_age_s']/86400 for r in rows]),np.array([r['next_revision'][:3] for r in rows])


def main():
    sources={str(p):digest(p) for p in (Path(__file__),HERE/'model.py',HERE/'PROTOCOL.md')}
    train=load(range(8),'training',sources);ages,v=arrays(train)
    counts=Counter(r['norad'] for r in train);weights=np.array([1/counts[r['norad']] for r in train])
    fits={arm:fit(ages,v,weights,flag) for arm,flag in [('constant',False),('age',True)]}
    calibration=dict(cases=len(train),physical_objects=len(counts),fits=fits,sources=sources.copy())
    path=HERE/'calibration.json'
    with path.open('x') as f:json.dump(calibration,f,indent=2,allow_nan=False)
    assert all(r['selected'] is not None for r in fits.values()),'Calibration unqualified'
    validation=load(range(8,12),'validation',sources);ages,v=arrays(validation)
    assert not set(counts)&{r['norad'] for r in validation}
    values={arm:scores(result['selected']['parameters'],ages,v,arm=='age')[0] for arm,result in fits.items()}
    groups=defaultdict(list)
    for row,gain in zip(validation,values['age']-values['constant']):groups[row['norad']].append(float(gain))
    gains=np.array([np.mean(g) for g in groups.values()]);wins=int(np.sum(gains>0))
    summary=dict(cases=len(validation),physical_objects=len(groups),source_wins=wins,
                 mean_source_gain=float(np.mean(gains)),median_source_gain=float(np.median(gains)),
                 passed=bool(np.mean(gains)>0 and np.median(gains)>0 and wins>.55*len(groups)))
    sources[str(path)]=digest(path)
    out=dict(validation=summary,source_gains={str(n):float(np.mean(g)) for n,g in groups.items()},
             sources=sources,exploratory_exposed_validation=True,independent_orbit_truth=False,
             causal_position_improvement_established=False)
    with (HERE/'summary.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(dict(fits=fits,validation=summary),indent=2))


if __name__=='__main__':main()
