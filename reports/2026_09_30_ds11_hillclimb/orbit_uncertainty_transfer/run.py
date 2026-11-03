"""Earlier-dataset symmetric prior calibration and DS9 held validation."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from model import track_scores,fit_prior,predictive,MAGNITUDES

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    started=time.monotonic();source=ROOT/'reports/2026_09_29_orbit_revision_transfer/directions.json'
    data=json.loads(source.read_text());sources={str(source):digest(source)}
    for name,h in data['hashes'].items():
        p=Path(name);p=p if p.is_absolute() else ROOT/p
        assert digest(p)==h;sources[str(p)]=h
    cases={};dates=defaultdict(list)
    for unit in sorted({r['unit_id'] for r in data['rows']}):
        p=ROOT/'reports/2026_09_29_donor_residual_transfer/runs'/unit/'result.json';assert str(p) in sources
        for c in json.loads(p.read_text())['cases']:
            key=(unit,c['session_id'],c['track_id']);assert key not in cases;cases[key]=c
            dates[unit[:3]].append(c['start_utc_ns'])
    assert max(dates['DS7']+dates['DS8'])<min(dates['DS9'])
    groups={}
    for r in data['rows']:
        c=cases[r['unit_id'],r['session_id'],r['track_id']]
        assert c['number']==r['number'] and c['mask']==r['mask']
        np.testing.assert_allclose(c['residual'],r['residual'],rtol=0,atol=1e-6)
        scores,rms=track_scores(c['times'],r['residual'],r['delta'],r['mask'])
        key=(r['unit_id'][:3],r['session_id'],r['number'])
        if key not in groups:groups[key]=dict(tracks=0,held_rows=0,changed=False,scores={name:{kind:np.zeros(11) for kind in ('train','joint')} for name in ('orbit','linear')})
        g=groups[key];g['tracks']+=1;g['held_rows']+=sum(not m for m in r['mask']);g['changed']|=rms>1e-6
        for name in scores:
            for kind in ('train','joint'):g['scores'][name][kind]+=scores[name][kind]
    donors=[g for k,g in groups.items() if k[0] in ('DS7','DS8')]
    priors={name:fit_prior(np.array([g['scores'][name]['train'] for g in donors])) for name in ('orbit','linear')}
    assert all(p['converged'] for p in priors.values())
    for p in (Path(__file__),HERE/'model.py',HERE/'test_model.py',HERE/'PROTOCOL.md'):sources[str(p)]=digest(p)
    # Seal fit before held predictive scoring. Held arrays were read/validated,
    # but are not arguments to the prior fitter.
    with (HERE/'priors.json').open('x') as f:json.dump(dict(priors=priors,magnitudes=MAGNITUDES.tolist(),donor_sources=len(donors),sources=sources),f,indent=2)
    rows=[]
    for (dataset,session,number),g in groups.items():
        if dataset!='DS9':continue
        assert g['held_rows']>0
        baseline=float(g['scores']['orbit']['joint'][0]-g['scores']['orbit']['train'][0])
        scored={name:predictive(s['train'],s['joint'],priors[name]['weights']) for name,s in g['scores'].items()}
        rows.append(dict(session_id=session,number=number,tracks=g['tracks'],held_rows=g['held_rows'],changed=g['changed'],
                         baseline=baseline,**scored,orbit_gain_per_row=(scored['orbit']-baseline)/g['held_rows'],
                         orbit_vs_linear_per_row=(scored['orbit']-scored['linear'])/g['held_rows']))
    changed=[r for r in rows if r['changed']];summary=dict(target_sources=len(rows),changed_sources=len(changed),donor_sources=len(donors))
    passes=[]
    for name,key,total_key in (('baseline','orbit_gain_per_row','baseline'),('linear','orbit_vs_linear_per_row','linear')):
        gains=[r[key] for r in changed];wins=sum(g>1e-10 for g in gains);total=sum(r['orbit']-r[total_key] for r in rows)
        summary[name]=dict(wins=wins,ties=sum(abs(g)<=1e-10 for g in gains),mean_gain_per_row=float(np.mean(gains)),median_gain_per_row=float(np.median(gains)),total_gain_nats=total)
        passes.append(wins>len(gains)/2 and np.mean(gains)>0 and np.median(gains)>0 and total>=0)
    summary['gate_pass']=all(passes)
    result=dict(summary=summary,rows=rows,priors_sha256=digest(HERE/'priors.json'),position_fits=0,reference_used=False,elapsed_s=time.monotonic()-started)
    with (HERE/'outcome.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(summary=summary,priors=priors,elapsed_s=result['elapsed_s']),indent=2))
if __name__=='__main__':main()
