"""Audit 12-step offset profiling against tighter stationary iteration."""
import argparse
import json
import hashlib
import sys
from pathlib import Path
import numpy as np
from scipy.special import logsumexp,gammaln

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_fresh_joint43'))
from run_joint43 import load_model
from run_baseline import robust_scores,site


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def refine(residual,mask,limit=2000):
    train=residual[:,mask];center=np.median(train,axis=-1);y=train-center[:,None];offset=np.zeros(len(train))
    active=np.ones(len(train),dtype=bool);steps=np.zeros(len(train),dtype=int)
    for i in range(limit):
        z=(y-offset[:,None])/100.;w=5/(4+z*z)
        new=(w*y).sum(axis=-1)/w.sum(axis=-1)
        delta=np.abs(new-offset);offset=np.where(active,new,offset);steps[active]=i+1
        active &= delta>=1e-7
        if not active.any():break
    offset+=center
    z=(residual-offset[:,None])/100.
    density=gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(100.)-2.5*np.log1p(z*z/4)
    score=density[:,mask].sum(axis=-1)-.5*offset**2/1e12
    return score,score+density[:,~mask].sum(axis=-1),~active,steps


def freeze():
    p=REPORTS/'2026_09_27_ds6_fresh_joint43/protocol.json';old=json.loads(p.read_text())
    paths=[p,REPORTS/'2026_09_27_ds6_fresh_joint43/run_joint43.py']+[REPORTS/name for name in old['files']]
    protocol=dict(source_sha256=digest(Path(__file__)),files={str(p.relative_to(REPORTS)):digest(p) for p in paths},sessions=old['splits']['all'],center=old['center'],
        comparison='Same median initialization; existing12 iterations versus centered up-to2000 iterations to offset change<1e-7Hz',
        scope='Fixed baseline positions and timing; same visibility and mixtures; no truth; conditional numerical audit, not global offset optimization',
        limitation='Preserves existing tiny post-fit offset penalty; convergence checks unpenalized offset stationarity')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(limit):
    protocol=json.loads((HERE/'protocol.json').read_text());assert digest(Path(__file__))==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    count=0
    for session in protocol['sessions']:
        path=HERE/f'{session}.json'
        if path.exists():continue
        if count>=limit:break
        model,x,_=load_model(session,protocol['center']);predictions=model.evaluate(x,False)['predictions']
        rec,up=site(*model.coordinates(x));q=(x[2]+5)*4;lo=min(39,max(0,int(np.floor(q))));weight=q-lo;rows=[]
        for t,pred in zip(model.tracks,predictions,strict=True):
            p,_,_=model.banks[t['track_id']];pos=p[:,lo]*(1-weight)+p[:,lo+1]*weight
            visible=np.any(((pos-rec)@up)[:,t['mask']]>=0,axis=-1)
            r=t['y'][None,:]-pred;a,b=robust_scores(r,t['mask']);c,d,converged,steps=refine(r,t['mask'])
            a,b,c,d=[np.where(visible,s,-np.inf) for s in [a,b,c,d]]
            oldtrain=float(logsumexp(a));newtrain=float(logsumexp(c))
            rows.append(dict(track_id=t['track_id'],train_gain=newtrain-oldtrain,
                held_gain=float(logsumexp(d)-newtrain-logsumexp(b)+oldtrain),
                unconverged_visible=int(np.sum(visible&~converged)),maximum_iterations=int(steps.max()),
                map_changed=bool(np.argmax(a)!=np.argmax(c))))
        result=dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'protocol.json'),tracks=rows,
            total_train_gain=sum(r['train_gain'] for r in rows),total_held_gain=sum(r['held_gain'] for r in rows),
            unconverged_visible=sum(r['unconverged_visible'] for r in rows))
        with path.open('x') as f:json.dump(result,f,indent=2)
        print(json.dumps({k:v for k,v in result.items() if k not in ['tracks','protocol_sha256']}),flush=True);count+=1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--limit',type=int,default=12);args=parser.parse_args()
    if args.freeze:freeze()
    else:
        assert 1<=args.limit<=12
        run(args.limit)
