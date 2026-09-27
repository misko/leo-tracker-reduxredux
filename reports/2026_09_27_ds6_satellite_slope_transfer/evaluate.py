"""Opposite-subset satellite-slope transfer; no reference or location search."""
from collections import defaultdict
import json
import statistics
import numpy as np
from export import HERE,digest,profile


def corrections(rows):
    scans=defaultdict(list)
    for r in rows:scans[(r['norad'],r['session_id'])].append(r['training_slope_hz_s'])
    satellites=defaultdict(list)
    for (sat,_),slopes in scans.items():satellites[sat].append(statistics.median(slopes))
    return {sat:dict(slope=statistics.median(slopes),donor_scans=len(slopes)) for sat,slopes in satellites.items() if len(slopes)>=2}


def score(row,slope):
    residual=np.array(row['residual_hz'])-slope*np.array(row['centered_times_s'])
    mask=np.array(row['training_mask'],dtype=bool)
    train,joint,checks,_=profile(residual[None,:],mask)
    assert all(c['converged'] for c in checks)
    return float(train[0]),float(joint[0]-train[0])


def main():
    inputs={n:json.loads((HERE/f'{n}.json').read_text()) for n in ['A','B']}
    assert all(d['complete'] and d['protocol_sha256']==digest(HERE/'protocol.json') for d in inputs.values())
    rows=[]
    for target,donor in [('A','B'),('B','A')]:
        learned=corrections(inputs[donor]['tracks'])
        assert {r['session_id'] for r in inputs[target]['tracks']}.isdisjoint(r['session_id'] for r in inputs[donor]['tracks'])
        for r in inputs[target]['tracks']:
            if r['norad'] not in learned:continue
            correction=learned[r['norad']];baseline=score(r,0.);shifted=score(r,correction['slope'])
            rows.append(dict(target=target,session_id=r['session_id'],track_id=r['track_id'],norad=r['norad'],
                **correction,train_gain=shifted[0]-baseline[0],held_gain=shifted[1]-baseline[1]))
    summary=dict(complete=True,source_sha256={name:digest(HERE/name) for name in ['evaluate.py','export.py']},
        input_sha256={f'{n}.json':digest(HERE/f'{n}.json') for n in ['A','B']},tracks=rows,
        eligible_tracks={n:len(d['tracks']) for n,d in inputs.items()},
        transferred_tracks=len(rows),held_gain=sum(r['held_gain'] for r in rows),
        held_improved=sum(r['held_gain']>0 for r in rows))
    with (HERE/'summary.json').open('x') as f:json.dump(summary,f,indent=2)
    print(json.dumps({k:v for k,v in summary.items() if k!='tracks'},indent=2))


if __name__=='__main__':main()
