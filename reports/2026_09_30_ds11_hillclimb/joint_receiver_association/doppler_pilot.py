"""Fixed-position integration of soft RX matching, identity and ownership.

No detector calibration or geographic optimization is claimed by this pilot.
"""
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.special import logsumexp
from matching import evidence
HERE=Path(__file__).resolve().parent;HILL=HERE.parent
sys.path.insert(0,str(HERE.parents[2]/'tools'))
import ds7_fast_baseline_adapter as fast
def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def candidate_factor(left,left_ids,right=None,right_ids=None,catalogue_size=None):
    """One physical satellite identity, with the original catalogue prior."""
    if right is None:return float(logsumexp(left)-np.log(catalogue_size))
    l={n:i for i,n in enumerate(left_ids)};r={n:i for i,n in enumerate(right_ids)}
    common=sorted(l.keys()&r.keys())
    if not common:return -np.inf
    return float(logsumexp([left[l[n]]+right[r[n]] for n in common])-np.log(catalogue_size))

def evaluate(doc,config,bound,x):
    geometry=fast.Stationary(doc,config);track_by_id={t['track_id']:t for t in doc['tracks']}
    meta={t['track_id']:t for t in bound['tracks']};base={};profiles={}
    for tid,t in track_by_id.items():
        prediction,visible=geometry.prediction(t,x);base[tid]=(t['y'][None,:]-prediction,visible)
    lanes=[]
    for lane in bound['lanes']:
        ls,rs=lane['left'],lane['right'];allowed={(e['left'],e['right']) for e in lane['edges']}
        prior=np.array([[0. if (a,b) in allowed else -np.inf for b in rs] for a in ls]).reshape(len(ls),len(rs))
        branches=[]
        for branch in lane['ownership_alternatives']:
            scores={};held={}
            for tid in ls+rs:
                t=track_by_id[tid];m=meta[tid]
                keep=np.array([branch['assignment'].get(cid,tid)==tid for cid in m['candidate_ids']])
                key=(tid,tuple(np.flatnonzero(~keep)))
                if key not in profiles:
                    residual,visible=base[tid];mask=t['mask'][keep]
                    if mask.sum()<2:raise ValueError('ownership leaves insufficient training support')
                    train,joint,audits,_=fast.profile(residual[:,keep],mask)
                    assert all(a['converged'] for a in audits)
                    profiles[key]=(np.where(visible,train,-np.inf),np.where(visible,joint,-np.inf))
                scores[tid],held[tid]=profiles[key]
            outputs={}
            for name,table in (('train',scores),('joint',held)):
                single={tid:candidate_factor(table[tid],meta[tid]['candidate_norad'],catalogue_size=track_by_id[tid]['catalogue_size']) for tid in ls+rs}
                pair=np.full((len(ls),len(rs)),-np.inf)
                for i,a in enumerate(ls):
                    for j,b in enumerate(rs):
                        if (a,b) in allowed:
                            assert track_by_id[a]['catalogue_size']==track_by_id[b]['catalogue_size']
                            pair[i,j]=candidate_factor(table[a],meta[a]['candidate_norad'],table[b],meta[b]['candidate_norad'],track_by_id[a]['catalogue_size'])
                outputs[name]=evidence([single[t] for t in ls],[single[t] for t in rs],pair,prior)
            branches.append(dict(log_prior=branch['log_prior'],train=outputs['train'],joint=outputs['joint']))
        train=logsumexp([b['log_prior']+b['train']['log_evidence'] for b in branches])
        joint=logsumexp([b['log_prior']+b['joint']['log_evidence'] for b in branches])
        weights=np.exp([b['log_prior']+b['train']['log_evidence']-train for b in branches])
        posterior=sum(w*b['train']['pair_posterior'] for w,b in zip(weights,branches))
        lanes.append(dict(rf_hz=lane['rf_hz'],train=float(train),held=float(joint-train),
                          expected_pairs=float(posterior.sum()),pair_posterior=posterior.tolist(),
                          ownership_posterior=weights.tolist(),left=ls,right=rs))
    return dict(training_score=sum(l['train'] for l in lanes),held_score=sum(l['held'] for l in lanes),lanes=lanes)

def main():
    started=time.monotonic();inventory=read(HERE/'inputs.json');sources=dict(inventory['sources'])
    for p,h in sources.items():assert digest(p)==h
    base=HILL.parent/'2026_09_30_ds11_single10';plan=read(base/'plan.json');rows=[]
    for row in inventory['scans']:
        assert digest(row['path'])==row['sha256'];sources[row['path']]=row['sha256']
        index=row['index'];bound=read(row['path']);doc=fast.load_documents(dict(config=plan['config'],inputs=[plan['inputs'][index]]))[0]
        original_path=base/f'runs/{index:02d}_iid.json';original=read(original_path)['selected'];sources[str(original_path)]=digest(original_path)
        begin=time.monotonic();result=evaluate(doc,plan['config'],bound,np.array(original['x']))
        rows.append(dict(index=index,elapsed_s=time.monotonic()-begin,**result))
    for p in (HERE/'inputs.json',Path(__file__),HERE/'matching.py',HERE/'test_matching.py',HERE/'test_doppler_pilot.py',HERE.parents[2]/'tools/ds7_fast_baseline_adapter.py',HERE.parents[2]/'tools/ds7_baseline_adapter.py'):sources[str(p)]=digest(p)
    output=dict(rows=rows,sources=sources,elapsed_s=time.monotonic()-started,position_fits=0,receiver_geometry_used=False,
                prior='uniform over allowed partial matching configurations; diagnostic, not calibrated',
                shortlist_scope='original candidate banks; no explicit catalogue-other emission yet')
    with (HERE/'doppler-pilot.json').open('x') as f:json.dump(output,f,indent=2,allow_nan=False)
    print(json.dumps(dict(elapsed_s=output['elapsed_s'],scans=[dict(index=r['index'],training_score=r['training_score'],held_score=r['held_score'],expected_pairs=sum(l['expected_pairs'] for l in r['lanes'])) for r in rows]),indent=2))
if __name__=='__main__':main()
