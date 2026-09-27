"""Distinguish RX information from generic posterior diversification, development only."""
import hashlib
import json
import math
from pathlib import Path
from conservative import SOURCE, score

HERE = Path(__file__).resolve().parent


def main():
    raw=SOURCE.read_bytes(); source=json.loads(raw)
    result={}
    for direction in ('A_to_B','B_to_A'):
        rows=[r for r in source['records'] if r['direction']==direction]
        arms={}
        for mode in ('uniform','training_prior'):
            values=[]
            for r in rows:
                v=r['normal']; p=v['baseline_conditioning_posterior']['log_weights']
                q=([-math.log(len(p))]*len(p) if mode=='uniform' else v['training_prior']['log_weights'])
                s=score(p,q,r['held_frequency_log_likelihood'],r['held_count'],.5)
                values.append({'session_id':r['session_id'],'track_id':r['track_id'],'weight':r['weight_seconds'],**s})
            def mean(rs): return math.fsum(r['weight']*r['gain'] for r in rs)/sum(r['weight'] for r in rs)
            per={sid:mean([r for r in values if r['session_id']==sid]) for sid in source['sessions']}
            arms[mode]={'weighted_gain':mean(values),'per_recording':per,'recordings_improving':sum(g>1e-10 for g in per.values()),'records':values}
        result[direction]=arms
    out={'scope':'Posthoc geometry-free diagnostic controls at fixed 0.5 blend. No tuning, no validation.',
         'source_sha256':hashlib.sha256(raw).hexdigest(),
         'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'core_sha256':hashlib.sha256((HERE/'conservative.py').read_bytes()).hexdigest(), 'results':result}
    with (HERE/'geometry-free-results.json').open('x') as stream:
        json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({d:{m:{k:v for k,v in a.items() if k!='records'} for m,a in arms.items()} for d,arms in result.items()},indent=2))


if __name__=='__main__': main()
