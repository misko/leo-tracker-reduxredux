"""Bounded two-satellite coordinate search under unchanged tracklet scoring.

Release two identities together, reconsider their timing modes and ownership,
then accept only a strict improvement of the existing penalized objective.
No likelihood gates, priors, coherence rules, or denominator changes.
"""
import argparse,json,time
from itertools import combinations
import numpy as np
from benchmark import ROOT,digest
from feasible_tracklets import compile_proposals,evaluate_mode


def best_pair(left,right,used,groups,times,top=3):
    best=[];score=0.
    for first,second in ((left,right),(right,left)):
        starts=sorted((evaluate_mode(m,used,groups,times) for m in first),key=lambda x:-x['score'])[:top]
        starts=[None]+[s for s in starts if s['score']>0]
        for start in starts:
            occupied=used.copy()
            if start:occupied[[r['row_index'] for r in start['assignments']]]=True
            others=[evaluate_mode(m,occupied,groups,times) for m in second]
            other=max(others,key=lambda x:x['score']) if others else None
            chosen=([start] if start else [])+([other] if other and other['score']>0 else [])
            value=sum(s['score'] for s in chosen)
            if value>score+1e-8:best,score=chosen,value
    return best,score


def validate(chosen,groups,times):
    records=[r for v in chosen.values() for r in v['assignments']]
    if len(records)!=len({r['row_index'] for r in records}):raise ValueError('Duplicate row ownership')
    if len(records)!=len({(int(groups[r['row_index']]),r['catalog_number']) for r in records}):raise ValueError('Duplicate satellite/probe')
    for n,v in chosen.items():
        if any(r['catalog_number']!=n or r['proposal']!=v['proposal'] for r in v['assignments']):raise ValueError('Mixed timing modes')
        for segment in {r['segment'] for r in v['assignments']}:
            rows=sorted([r['row_index'] for r in v['assignments'] if r['segment']==segment],key=lambda r:times[r])
            if len(rows)<10 or times[rows[-1]]-times[rows[0]]<5 or np.max(np.diff(times[rows]))>5:
                raise ValueError('Coherence failed')
    return records


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    parser.add_argument('--seconds',type=float,default=30);args=parser.parse_args()
    if not 0<args.seconds<=60:raise ValueError('Bounded experiment must take <=60 seconds')
    source=ROOT/'development-expanded'/f'{args.scan}-proposals.json';baseline_path=ROOT/'development-tracklets'/f'{args.scan}-feasible.json'
    baseline=json.loads(baseline_path.read_text());proposals=json.loads(source.read_text())['proposals']
    if baseline['source_sha256']!=digest(source):raise ValueError('Baseline source changed')
    output=ROOT/'pairwise-tracklets';output.mkdir(exist_ok=True);target=output/f'{args.scan}.json'
    if target.exists():raise FileExistsError(target)
    with np.load(ROOT/'frozen'/f'{args.scan}-observations.npz') as a:groups,times,denom=a['group'],a['times_s'],len(a['canonical_rows'])
    modes=compile_proposals(proposals,groups,.8/(13 if args.scan=='A' else 15));by_number={}
    for mode in modes:by_number.setdefault(mode['number'],[]).append(mode)
    chosen={}
    for n,pi in baseline['selected_modes'].items():
        rows=[r for r in baseline['assignments'] if r['catalog_number']==int(n)]
        score=sum(r['gain'] for r in rows)-7*len({r['segment'] for r in rows})-modes[pi]['penalty']
        chosen[int(n)]=dict(score=score,assignments=rows,proposal=pi,catalog_number=int(n))
    if not np.isclose(sum(v['score'] for v in chosen.values()),baseline['score']):raise ValueError('Score reconstruction mismatch')
    supports={n:{int(r) for m in items for _,rr,_,_ in m['segments'] for r in rr} for n,items in by_number.items()}
    pairs=[(len(supports[l]&supports[r]),l,r) for l,r in combinations(sorted(by_number),2) if supports[l]&supports[r]]
    pairs.sort(reverse=True);trace=[];tested=0;start=time.monotonic();deadline=start+args.seconds
    for sweep in range(3):
        changes=0
        for _,left,right in pairs:
            if time.monotonic()>=deadline:break
            if left not in chosen and right not in chosen:continue
            used=np.zeros(len(groups),bool)
            for n,v in chosen.items():
                if n not in (left,right):used[[r['row_index'] for r in v['assignments']]]=True
            old=sum(chosen[n]['score'] for n in (left,right) if n in chosen)
            candidate,score=best_pair(by_number[left],by_number[right],used,groups,times);tested+=1
            if score>old+1e-8:
                chosen.pop(left,None);chosen.pop(right,None)
                chosen.update({v['catalog_number']:v for v in candidate});changes+=1
                validate(chosen,groups,times)
                trace.append(dict(sweep=sweep,identities=[left,right],gain=score-old,
                    assigned=sum(len(v['assignments']) for v in chosen.values()),score=sum(v['score'] for v in chosen.values())))
        if not changes or time.monotonic()>=deadline:break
    records=validate(chosen,groups,times);score=sum(v['score'] for v in chosen.values())
    result=dict(scope=__doc__,scan=args.scan,assignments=records,selected_modes={n:v['proposal'] for n,v in chosen.items()},
        score=score,score_improvement=score-baseline['score'],assigned_count=len(records),
        assignment_change=len(records)-len(baseline['assignments']),coverage=len(records)/denom,
        pairs_tested=tested,trace=trace,elapsed_s=time.monotonic()-start,
        source_sha256={str(p):digest(p) for p in (source,baseline_path)},
        warning='Development-only calibration and assignments; no identity or validation certification. Bounded search, not optimality proof.')
    with target.open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('assignments','trace','selected_modes')}),flush=True)


if __name__=='__main__':main()
