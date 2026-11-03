import hashlib
import json
import math
from pathlib import Path


def predict(rows, background, tau):
    if tau <= 0 or not math.isfinite(tau):
        raise ValueError('positive finite decay time required')
    if len(background)!=4 or any(x<=0 or not math.isfinite(x) for x in background):
        raise ValueError('four positive finite probabilities required')
    if not math.isclose(sum(background),1.,abs_tol=1e-10):
        raise ValueError('normalized background required')
    counts=[0.]*4; last=None; output=[]
    for row in rows:
        now=row['prediction_utc_ns']; y=row['category']
        if last is not None and now<=last: raise ValueError('strictly increasing times required')
        if not isinstance(y,int) or not 0<=y<4: raise ValueError('invalid category')
        decay=math.exp(-(now-last)/1e9/tau) if last is not None else 1.
        counts=[v*decay for v in counts]
        p=[(v+20*b)/(sum(counts)+20) for v,b in zip(counts,background)]
        output.append({'source_window_id':row['source_window_id'],'role':row['role'],
                       'probabilities':p,'log_score':math.log(p[y])})
        counts[y]+=1; last=now
    return output


def average(lanes, background, tau, role=None):
    scores=[r['log_score'] for lane in lanes for r in predict(lane['windows'],background,tau)
            if role is None or r['role']==role]
    return math.fsum(scores)/len(scores)


def main():
    here=Path(__file__).resolve().parent; source=here.parent/'2026_09_28_rx_paired_state_cv'
    paths=[source/f'fold-{i}.json' for i in range(6)]
    documents=[json.loads(p.read_text()) for p in paths]
    localpath=here.parent/'2026_09_30_rx_local_response/results.json'
    local={r['session']:r for r in json.loads(localpath.read_text())['records']}
    records=[]
    for i,doc in enumerate(documents):
        background=doc['background']; training=[]; train_ids=[]
        for j,donor in enumerate(documents):
            if j==i: continue
            lanes=[{**l,'windows':[r for r in l['windows'] if r['role']=='reception']}
                   for l in donor['evaluations']['P']['lanes']]
            training.append(lanes)
            train_ids.extend(r['source_window_id'] for l in lanes for r in l['windows'])
        assert sorted(train_ids)==doc['training_source_window_ids']
        grid=[{'tau_s':tau,'mean_training_score':math.fsum(average(ls,background,tau) for ls in training)/5}
              for tau in (1.,10.,30.,100.)]
        tau=max(grid,key=lambda r:(r['mean_training_score'],-r['tau_s']))['tau_s']
        lanes=doc['evaluations']['P']['lanes']
        predictions=[{'lane':l['lane'],'windows':predict(l['windows'],background,tau)} for l in lanes]
        held=[r for l in predictions for r in l['windows'] if r['role']=='held_frequency']
        score=math.fsum(r['log_score'] for r in held)/len(held)
        baselines={a:doc['evaluations'][a]['roles']['held_frequency']['full_log_score_per_window'] for a in ('P','U','O')}
        baselines['background']=doc['evaluations']['P']['roles']['held_frequency']['reference_log_score_per_window']
        baselines['frozen_local']=local[doc['held_session']]['local_score_per_window']
        assert len(held)==doc['evaluations']['P']['roles']['held_frequency']['windows']
        records.append({'session':doc['held_session'],'grid':grid,'tau_s':tau,'windows':len(held),
                        'later_score_per_window':score,'gains':{k:score-v for k,v in baselines.items()},
                        'predictions':predictions})
    summary={k:{'mean_gain':math.fsum(r['gains'][k] for r in records)/6,
                'positive_records':sum(r['gains'][k]>1e-6 for r in records)} for k in records[0]['gains']}
    sources=paths+[localpath,Path(__file__),here/'PROTOCOL.md']
    result={'records':records,'summary':summary,'source_sha256':{str(p.relative_to(Path.cwd())):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    with (here/'results.json').open('x') as f: json.dump(result,f,indent=2)
    print(json.dumps(summary,indent=2));print('selected times', [r['tau_s'] for r in records])


if __name__=='__main__': main()
