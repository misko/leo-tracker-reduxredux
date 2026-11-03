import hashlib
import json
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from core import pack,conditional

HERE=Path(__file__).resolve().parent


def design(rows,variable):
    result=np.zeros((len(rows),4 if variable else 2))
    for i,r in enumerate(rows):
        result[i,r['rx']]=1.
        if variable:result[i,2+r['rx']]=math.log(r['feature']/100.)
    return result


def main():
    started=time.monotonic();path=HERE/'statistics.json';source=json.loads(path.read_text())
    for name,digest in source['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    donors=[r for r in source['rows'] if r['dataset']!='DS10'];targets=[r for r in source['rows'] if r['dataset']=='DS10']
    train,full=pack([r['training'] for r in donors]),pack([r['full'] for r in donors])
    target_train,target_full=pack([r['training'] for r in targets]),pack([r['full'] for r in targets])
    counts=defaultdict(int);scans=defaultdict(set)
    for r in donors:
        counts[r['dataset'],r['session_id']]+=r['held_observations'];scans[r['dataset']].add(r['session_id'])
    weights=np.array([1/(3*len(scans[r['dataset']])*counts[r['dataset'],r['session_id']]) for r in donors])
    assert abs(sum(w*r['held_observations'] for w,r in zip(weights,donors))-1)<1e-12
    fits={};target_scores={}
    for arm,variable in [('constant',False),('variable',True)]:
        matrix=design(donors,variable);target_matrix=design(targets,variable)
        bounds=[(-math.log(4),math.log(4))]*2+([(-2.,2.)]*2 if variable else [])
        def objective(p):
            values,g=conditional(train,full,math.log(100)+matrix@p)
            return -float(weights@values),-matrix.T@(weights*g)
        fit=minimize(objective,np.zeros(len(bounds)),jac=True,bounds=bounds,method='L-BFGS-B',options=dict(maxiter=200,ftol=1e-12,gtol=1e-7))
        audit=[]
        for i in range(len(bounds)):
            delta=np.zeros(len(bounds));delta[i]=1e-5
            fd=(objective(fit.x+delta)[0]-objective(fit.x-delta)[0])/2e-5
            audit.append(abs(fd-fit.jac[i]))
        boundary=any(min(v-lo,hi-v)<.001 for v,(lo,hi) in zip(fit.x,bounds))
        pg=float(max(abs(fit.jac)));ga=float(max(audit))
        fits[arm]=dict(params=fit.x.tolist(),success=bool(fit.success),message=str(fit.message),boundary=boundary,gradient=pg,gradient_audit=ga,
                       qualified=bool(fit.success and not boundary and pg<=1e-5 and ga<=1e-5))
        if fits[arm]['qualified']:
            target_scores[arm]=conditional(target_train,target_full,math.log(100)+target_matrix@fit.x)[0]
    summary=dict(fits=fits,donor_tracks=len(donors),target_tracks=len(targets),coverage=source['coverage'])
    if len(target_scores)==2:
        baseline=np.array([r['baseline_held'] for r in targets]);rows=[]
        for sid in dict.fromkeys(r['session_id'] for r in targets):
            keep=np.array([r['session_id']==sid for r in targets]);held=sum(r['held_observations'] for r in targets if r['session_id']==sid)
            rows.append(dict(session_id=sid,held=held,**{arm:float((values[keep]-baseline[keep]).sum()) for arm,values in target_scores.items()}))
        summary['scan_scores']=rows
        for arm in target_scores:
            summary[arm]=dict(total_log_score_gain=sum(r[arm] for r in rows),equal_scan_per_held_gain=float(np.mean([r[arm]/r['held'] for r in rows])),scans_improved=sum(r[arm]>0 for r in rows))
        delta=float(np.mean([(r['variable']-r['constant'])/r['held'] for r in rows]))
        summary['variable_vs_constant_equal_scan_gain']=delta
        summary['geographic_refit_warranted']=bool(delta>0 and summary['variable']['equal_scan_per_held_gain']>0)
    else:summary['geographic_refit_warranted']=False
    paths=[path,HERE/'run.py',HERE/'core.py',HERE/'PROTOCOL.md']
    with (HERE/'results.json').open('x') as out:json.dump(dict(summary=summary,elapsed_seconds=time.monotonic()-started,hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}),out,indent=2,allow_nan=False)
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['coverage','scan_scores']},indent=2))


if __name__=='__main__':main()
