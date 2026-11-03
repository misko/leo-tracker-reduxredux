"""Reconstruct state likelihoods and verify expanded-state predictive mixtures."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.special import gammaln,logsumexp

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    prior=json.loads((HERE/'priors.json').read_text());result=json.loads((HERE/'outcome.json').read_text())
    assert result['priors_sha256']==digest(HERE/'priors.json')
    for p,h in prior['sources'].items():assert digest(p)==h
    source=ROOT/'reports/2026_09_29_orbit_revision_transfer/directions.json';data=json.loads(source.read_text())
    cases={};identities=set();dates=defaultdict(list)
    for unit in sorted({r['unit_id'] for r in data['rows']}):
        path=ROOT/'reports/2026_09_29_donor_residual_transfer/runs'/unit/'result.json'
        for c in json.loads(path.read_text())['cases']:
            cases[unit,c['session_id'],c['track_id']]=c;dates[unit[:3]].append(c['start_utc_ns'])
    assert max(dates['DS7']+dates['DS8'])<min(dates['DS9'])
    mags=prior['magnitudes'];beta=np.array([0.]+[v for m in mags[1:] for v in (-m,m)])
    logc=float(gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(100.))
    groups={}
    for row in data['rows']:
        identity=(row['unit_id'][:3],row['session_id'],row['track_id']);assert identity not in identities;identities.add(identity)
        c=cases[row['unit_id'],row['session_id'],row['track_id']];m=np.array(row['mask'],bool)
        t=np.array(c['times']);t-=t[m].mean();r=np.array(row['residual']);r-=r[m].mean();d=np.array(row['delta']);d-=d[m].mean()
        rms=np.sqrt(np.mean(d[m]**2));linear=np.zeros_like(d)
        if rms>1e-6:linear=t*rms/np.sqrt(np.mean(t[m]**2))*(-1 if np.dot(t[m],d[m])<0 else 1)
        key=(row['unit_id'][:3],row['session_id'],row['number'])
        if key not in groups:groups[key]={arm:np.zeros((2,11)) for arm in ('orbit','linear')}
        for arm,direction in (('orbit',d),('linear',linear)):
            for k,b in enumerate(beta):
                ll=logc-2.5*np.log1p(((r-b*direction)/100.)**2/4)
                groups[key][arm][0,k]+=ll[m].sum();groups[key][arm][1,k]+=ll.sum()
    largest=0.;fixed_point={}
    for arm in ('orbit','linear'):
        weights=np.array(prior['priors'][arm]['weights']);assert abs(weights.sum()-1)<1e-12 and np.all(weights>0)
        expanded=np.r_[weights[0],np.repeat(weights[1:]/2,2)]
        assert abs(expanded@beta)<1e-15
        donor=np.array([g[arm][0] for k,g in groups.items() if k[0] in ('DS7','DS8')])
        logits=donor+np.log(expanded);resp=np.exp(logits-logsumexp(logits,axis=1)[:,None])
        mass=np.r_[resp[:,0].mean(),resp[:,1:].reshape(len(resp),5,2).sum(axis=2).mean(axis=0)]
        fixed_point[arm]=float(np.max(abs(mass-weights)));assert fixed_point[arm]<1e-9
        for row in result['rows']:
            train,joint=groups['DS9',row['session_id'],row['number']][arm]
            predicted=float(logsumexp(joint+np.log(expanded))-logsumexp(train+np.log(expanded)))
            largest=max(largest,abs(predicted-row[arm]))
            assert abs(row['baseline']-(joint[0]-train[0]))<1e-8
    assert largest<1e-8
    changed=[r for r in result['rows'] if r['changed']]
    checks=[]
    for control,key in (('baseline','orbit_gain_per_row'),('linear','orbit_vs_linear_per_row')):
        gains=[(r['orbit']-r[control])/r['held_rows'] for r in changed]
        for r,g in zip(changed,gains):assert abs(r[key]-g)<1e-12
        summary=result['summary'][control];assert summary['wins']==sum(g>1e-10 for g in gains)
        assert abs(summary['median_gain_per_row']-np.median(gains))<1e-12
        total=sum(r['orbit']-r[control] for r in result['rows']);assert abs(summary['total_gain_nats']-total)<1e-8
        checks.append(sum(g>1e-10 for g in gains)>len(gains)/2 and np.mean(gains)>0 and np.median(gains)>0 and total>=0)
    assert result['summary']['gate_pass']==all(checks)
    verification=dict(verification_pass=True,unique_track_cases=len(identities),source_groups=len(groups),
                      maximum_predictive_discrepancy_nats=largest,em_fixed_point_error=fixed_point,
                      sources={str(p):digest(p) for p in (Path(__file__),HERE/'priors.json',HERE/'outcome.json')})
    with (HERE/'verification.json').open('x') as f:json.dump(verification,f,indent=2)
    print(json.dumps(verification,indent=2))
if __name__=='__main__':main()
