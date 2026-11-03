"""Fast feasible local-tracklet selection; one timing mode per satellite.

Greedy additions and coordinate mode swaps, not a global optimality claim.
"""
import argparse,json,time
import numpy as np
from benchmark import ROOT,ALIAS_HZ,digest


def compile_proposals(proposals,groups,pdet):
    result=[];penalty=.5*np.log(len(np.unique(groups)))
    for pi,p in enumerate(proposals):
        segments=[]
        for si,s in enumerate(p['segments']):
            r=np.array(s['eligible_rows'],int);e=np.array(s['eligible_residual_native_hz'])
            gain=np.log(pdet/(1-pdet))-np.log(200*np.sqrt(2*np.pi))-.5*(e/200)**2-np.log(2/ALIAS_HZ)
            segments.append((si,r,e,gain))
        result.append(dict(number=p['catalog_number'],proposal=pi,penalty=penalty+.5*p['offset_s']**2,segments=segments))
    return result


def evaluate_mode(mode,used,groups,times):
    records=[];value=-mode['penalty'];nextsegment=0
    for si,rr,residual,gain in mode['segments']:
        eligible=(gain>0)&~used[rr]
        order=np.flatnonzero(eligible);order=order[np.argsort(-gain[order],kind='stable')]
        _,first=np.unique(groups[rr[order]],return_index=True);order=order[first]
        order=order[np.argsort(times[rr[order]],kind='stable')]
        for part in np.split(order,np.flatnonzero(np.diff(times[rr[order]])>5)+1):
            if len(part)<10 or times[rr[part[-1]]]-times[rr[part[0]]]<5:continue
            score=float(gain[part].sum()-7.)
            if score<=0:continue
            value+=score
            records.extend(dict(row_index=int(rr[k]),catalog_number=mode['number'],proposal=mode['proposal'],
                                source_segment=si,segment=nextsegment,residual_native_hz=float(residual[k]),gain=float(gain[k])) for k in part)
            nextsegment+=1
    return dict(score=value,assignments=records,proposal=mode['proposal'],catalog_number=mode['number'])


def select(proposals,groups,times,pdet):
    modes=compile_proposals(proposals,groups,pdet);chosen={};used=np.zeros(len(groups),bool);trace=[]
    for sweep in range(3):
        changed=0
        if sweep:
            for number in sorted(list(chosen)):
                old=chosen.pop(number)
                used[[x['row_index'] for x in old['assignments']]]=False
                options=[evaluate_mode(m,used,groups,times) for m in modes if m['number']==number]
                best=max(options,key=lambda x:x['score'])
                if best['score']>old['score']+1e-8:chosen[number]=best;changed+=1
                else:chosen[number]=old
                used[[x['row_index'] for x in chosen[number]['assignments']]]=True
        while True:
            options=[evaluate_mode(m,used,groups,times) for m in modes if m['number'] not in chosen]
            if not options:break
            best=max(options,key=lambda x:x['score'])
            if best['score']<=0:break
            chosen[best['catalog_number']]=best;changed+=1
            used[[x['row_index'] for x in best['assignments']]]=True
        trace.append(dict(sweep=sweep,changes=changed,score=sum(v['score'] for v in chosen.values()),assigned=int(used.sum())))
        if not changed:break
    records=[r for v in chosen.values() for r in v['assignments']]
    assert len(records)==len({r['row_index'] for r in records})
    assert len(records)==len({(int(groups[r['row_index']]),r['catalog_number']) for r in records})
    for number in chosen:
        items=[r for r in records if r['catalog_number']==number]
        assert len({r['proposal'] for r in items})==1
        for segment in {r['segment'] for r in items}:
            rows=sorted([r['row_index'] for r in items if r['segment']==segment],key=lambda r:times[r])
            assert len(rows)>=10 and times[rows[-1]]-times[rows[0]]>=5
            assert np.max(np.diff(times[rows]))<=5
    return dict(assignments=records,score=sum(v['score'] for v in chosen.values()),trace=trace,
                selected_modes={n:v['proposal'] for n,v in chosen.items()})


def main():
    p=argparse.ArgumentParser();p.add_argument('--scan',choices=['A','B'],required=True);a=p.parse_args()
    source=ROOT/'development-expanded'/f'{a.scan}-proposals.json';data=json.loads(source.read_text())
    arrays=np.load(ROOT/'frozen'/f'{a.scan}-observations.npz');started=time.monotonic()
    result=select(data['proposals'],arrays['group'],arrays['times_s'],.8/(13 if a.scan=='A' else 15))
    result.update(scope=__doc__,source_sha256=digest(source),scan=a.scan,elapsed_s=time.monotonic()-started,
                  assigned_count=len(result['assignments']),coverage=len(result['assignments'])/len(arrays['canonical_rows']),
                  warning='Development-only raw assignments. Identity margins and validation gates outstanding.')
    out=ROOT/'development-tracklets';out.mkdir(exist_ok=True)
    (out/f'{a.scan}-feasible.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='assignments'}),flush=True)


if __name__=='__main__':main()
