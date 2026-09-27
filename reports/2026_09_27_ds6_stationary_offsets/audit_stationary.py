"""Audit each scan's numerically most affected track and every failed track."""
import json
import sys
import hashlib
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from solver import scores

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_fresh_joint43'))
from run_joint43 import load_model
from run_baseline import robust_scores,site


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    source=REPORTS/'2026_09_27_ds6_offset_convergence'
    old=json.loads((source/'protocol.json').read_text());selected={};inputs={}
    for session in old['sessions']:
        path=source/f'{session}.json';result=json.loads(path.read_text());inputs[str(path.relative_to(REPORTS))]=digest(path)
        selected[session]=sorted({max(result['tracks'],key=lambda t:abs(t['train_gain']))['track_id']}|
            {t['track_id'] for t in result['tracks'] if t['unconverged_visible']})
    protocol=dict(source_sha256=digest(Path(__file__)),solver_sha256=digest(HERE/'solver.py'),
        input_protocol_sha256=digest(source/'protocol.json'),input_sha256=inputs,selected=selected,
        policy='Largest absolute fixed-position training-score change per scan plus every previously unconverged track; selection contains no ground truth',
        model='Nine quantile initializations plus median,100 IRLS iterations, bracketed positive-curvature stationary roots; exact weak offset penalty included',
        scope='Numerical diagnostic on selected tracks, no position refit; finite brackets do not prove global optimality')
    protocol_path=HERE/'protocol.json'
    if protocol_path.exists():assert json.loads(protocol_path.read_text())==protocol
    else:protocol_path.write_text(json.dumps(protocol,indent=2)+'\n')
    for name,value in old['files'].items():assert digest(REPORTS/name)==value
    for session,track_ids in selected.items():
        output=HERE/f'{session}.json'
        if output.exists():continue
        model,x,_=load_model(session,old['center']);pred=model.evaluate(x,False)['predictions']
        rec,up=site(*model.coordinates(x));q=(x[2]+5)*4;lo=min(39,max(0,int(np.floor(q))));weight=q-lo;rows=[]
        for t,prediction in zip(model.tracks,pred,strict=True):
            if t['track_id'] not in track_ids:continue
            p,_,_=model.banks[t['track_id']];pos=p[:,lo]*(1-weight)+p[:,lo+1]*weight
            visible=np.any(((pos-rec)@up)[:,t['mask']]>=0,axis=-1)
            residual=t['y'][None,:]-prediction;a,b=robust_scores(residual,t['mask']);c,d,audits=scores(residual,t['mask'])
            a,b,c,d=[np.where(visible,s,-np.inf) for s in [a,b,c,d]]
            rows.append(dict(track_id=t['track_id'],candidates=len(audits),visible_candidates=int(visible.sum()),
                train_gain=float(logsumexp(c)-logsumexp(a)),held_gain=float(logsumexp(d)-logsumexp(c)-logsumexp(b)+logsumexp(a)),
                all_converged=all(v['converged'] for v in audits),max_abs_gradient=max(abs(v['gradient']) for v in audits),
                min_curvature=min(v['curvature'] for v in audits),max_roots=max(v['roots'] for v in audits),
                old_map=int(np.argmax(a)),new_map=int(np.argmax(c))))
        result=dict(session_id=session,complete=True,protocol_sha256=digest(protocol_path),tracks=rows)
        output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
