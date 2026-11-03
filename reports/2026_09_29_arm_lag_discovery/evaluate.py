"""Timing-region coverage from current-IQ proposals, not detection recall."""
import hashlib
import json
from pathlib import Path
import sys
import time
import argparse
import numpy as np
from proposal import propose

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_28_arm_full_optimization'))
import arm_cohort as a

def peaks(scores,limit=32):
    scores=np.asarray(scores,dtype=float)
    assert scores.ndim==1 and np.isfinite(scores).all()
    left=np.roll(scores,1);right=np.roll(scores,-1)
    candidates=np.flatnonzero((scores>0)&(scores>=left)&(scores>=right)&((scores>left)|(scores>right)))
    selected=[];n=len(scores)
    for k in sorted(candidates,key=lambda k:(-scores[k],int(k))):
        if all(min(abs(int(k)-p),n-abs(int(k)-p))>=5 for p in selected):
            selected.append(int(k))
            if len(selected)==limit:break
    return selected

def covered(epoch,selected,radius):
    # The original matcher uses absolute coordinates, not circular distance.
    return any(abs(epoch-p)<=radius for p in selected)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--full',action='store_true')
    parser.add_argument('--output',default='ds7-32-v1');args=parser.parse_args()
    out=HERE/args.output;out.mkdir(exist_ok=False)
    manifest=json.loads((a.INPUTS/'inputs.json').read_text());assert manifest['complete']
    selection=[]
    for rate in (2500000,5000000,7500000,10000000):
        for edge in ('lower','upper'):
            group=[r for r in manifest['rows'] if r['rate_hz']==rate and r['target']['edge']==edge]
            selection.extend(group[round(i*(len(group)-1)/3)] for i in range(4))
    if args.full:selection=manifest['rows']
    assert len({r['ordinal'] for r in selection})==(704 if args.full else 32)
    baseline=a.baseline()
    oracle=json.loads((a.ORACLE/'oracle.json').read_text())
    templates={}
    for c in oracle['cases']:
        t=c['templates']['exact'];p=a.ORACLE/t['file'];assert a.sha(p)==t['sha256']
        templates[(c['context']['rate_hz'],c['context']['target']['edge'])]=np.fromfile(p,dtype=np.complex128)
    frozen={n:a.sha(HERE/n) for n in ('proposal.py','evaluate.py','PROTOCOL.md')}
    counts={};rows=[];frequency_counts={}
    for ctx in selection:
        source=a.INPUTS/ctx['file'];assert a.sha(source)==ctx['sha256']
        data=np.load(source,allow_pickle=False);rate=ctx['rate_hz'];probe=rate//50;stride=rate//100
        original=baseline[(ctx['session_id'],ctx['visit_index'])]
        for window in range(11):
            for rx in range(2):
                slab=data[window*stride:window*stride+probe,rx]
                iq=slab[:,0].astype(float)+1j*slab[:,1].astype(float)
                start=time.process_time();features=propose(iq,templates[(rate,ctx['target']['edge'])],rate)
                cpu=time.process_time()-start
                ranked={k:peaks(s) for k,s in features['scores'].items()}
                frequency_proposals={f'lag{lag}':[
                    float(np.angle(features['correlations'][f'lag{lag}'][epoch])*rate/(2*np.pi*lag))
                    for epoch in ranked['combined'][:4]] for lag in (1,3,5)}
                # Label lookup occurs only after current-IQ features/proposals.
                positive=[c for c in original[(rx,window)]['candidates'] if c['margin']>=.025]
                for method,freqs in frequency_proposals.items():
                    stat=frequency_counts.setdefault((rate,method),dict(original_hits=0,timing_covered=0,
                         direct_frequency_covered=0,alias_frequency_covered=0))
                    for c in positive:
                        valid=[f for e,f in zip(ranked['combined'][:4],freqs) if abs(e-c['epoch_sample'])<=2]
                        stat['original_hits']+=1;stat['timing_covered']+=bool(valid)
                        stat['direct_frequency_covered']+=any(abs(f-c['tracking_cfo_hz'])<=8000 for f in valid)
                        stat['alias_frequency_covered']+=any(abs(f+j/4.4e-6-c['tracking_cfo_hz'])<=8000
                              for f in valid for j in range(-8,9))
                for method,centers in ranked.items():
                    for budget in (2,4,8,16,32):
                        for radius in (2,8):
                            key=(rate,method,budget,radius)
                            stat=counts.setdefault(key,dict(windows=0,original_hits=0,covered_hits=0,
                                 original_positive_windows=0,covered_positive_windows=0))
                            matches=sum(covered(c['epoch_sample'],centers[:budget],radius) for c in positive)
                            stat['windows']+=1;stat['original_hits']+=len(positive);stat['covered_hits']+=matches
                            stat['original_positive_windows']+=bool(positive);stat['covered_positive_windows']+=matches>0
                rows.append({'context':ctx,'window':window,'rx':rx,'proposal_cpu_s':cpu,
                             'ranked_epochs':ranked,'frequency_proposals':frequency_proposals,
                             'original_positive_epochs':[c['epoch_sample'] for c in positive]})
        print('processed',ctx['ordinal'],flush=True)
    for n,digest in frozen.items():assert a.sha(HERE/n)==digest
    (out/'rows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    summary={'complete':True,'scope':'timing-region coverage only; no new GLRT calls or ARM timing',
       'source_sha256':frozen,'baseline_sha256':a.sha(a.BASELINE),'inputs_sha256':a.sha(a.INPUTS/'inputs.json'),
       'rows_sha256':a.sha(out/'rows.jsonl'),'selected':selection,'windows':len(rows),
       'frequency_results':[dict(rate_hz=k[0],method=k[1],**v) for k,v in sorted(frequency_counts.items())],
       'results':[dict(rate_hz=k[0],method=k[1],budget=k[2],radius=k[3],**v) for k,v in sorted(counts.items())]}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    for r in summary['results']:
        if r['rate_hz']==2500000 and r['radius']==2:
            print(r['method'],r['budget'],r['covered_hits'],r['original_hits'],flush=True)

if __name__=='__main__':main()
