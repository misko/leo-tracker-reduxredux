"""Source-balanced calibration and validation, with fixed proper regularizers.

Each training source has total weight one; repeated windows do not manufacture
independent sample size. Intercept and slope prior SDs are5 and10 respectively.
"""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from scipy.optimize import minimize
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'acquisition_calibration'))
from fit_family import projected_gradient
from model import design,likelihood,source_weights


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dataset(doc,donor,permuted=False):
    rows=doc['rows'];los=np.array([r['los_enu'] for r in rows])
    if permuted:
        rng=np.random.default_rng(20260930);mapping={}
        for rf in doc['frequencies']:
            lanes=[l for l in donor['lanes'] if l['rf_hz']==rf]
            for original,other in zip(lanes,rng.permutation(len(lanes))):mapping[original['norad'],rf]=lanes[int(other)]
        for i,row in enumerate(rows):
            lane=mapping[row['norad'],row['rf_hz']]
            j=int(np.searchsorted(lane['times_s'],row['time_s']))
            assert lane['times_s'][j]==row['time_s']
            los[i]=lane['los_enu'][j]
    return dict(los=los,rf=np.array([doc['frequencies'].index(r['rf_hz']) for r in rows]),anchor=np.array([r['anchor_rx'] for r in rows]),hit=np.array([r['hit'] for r in rows]),train=np.array([r['training'] for r in rows],bool),source=np.array([r['source'] for r in rows]))


def evaluate(parameters,data,arm,mask):
    weights=source_weights(data['source'],mask)
    scores,_=likelihood(parameters,design(data['los'],data['rf'],data['anchor'],arm),data['hit'],weights)
    return dict(score=float(weights@scores),events=int(mask.sum()),per_source={str(s):float(np.mean(scores[mask & (data['source']==s)])) for s in np.unique(data['source'][mask])})


def main():
    paths=[Path(__file__),HERE/'model.py',HERE/'PROTOCOL.md',HERE.parent/'acquisition_calibration/fit_family.py']
    sources={str(p):digest(p) for p in paths};docs=[];donors=[]
    for index in (16,17):
        p=HERE/f'input-{index:02d}.json';doc=json.loads(p.read_text())
        for q,h in doc['sources'].items():assert digest(q)==h,q
        sources[str(p)]=digest(p);docs.append(doc)
        p=HERE.parent/f'acquisition_calibration/donor-{index:02d}.json';donors.append(json.loads(p.read_text()));sources[str(p)]=digest(p)
    datasets=[dataset(d,g) for d,g in zip(docs,donors)]
    arms={};training=datasets[0]
    for arm in ('receiver','elevation','signed'):
        x=design(training['los'],training['rf'],training['anchor'],arm);n=x.shape[1]
        weights=source_weights(training['source'],training['train'])
        scales=np.r_[np.full(8,5.),10.] if n==9 else np.full(8,5.)
        bounds=[(-20.,20.)]*8+([(0.,40.)] if n==9 else [])
        def objective(p):
            scores,gradient=likelihood(p,x,training['hit'],weights)
            return -weights@scores+.5*np.sum((p/scales)**2),-gradient+p/scales**2
        fits=[]
        for start in [np.zeros(n)]+([np.r_[np.zeros(8),5.]] if n==9 else []):
            fit=minimize(objective,start,method='L-BFGS-B',jac=True,bounds=bounds,options=dict(maxiter=500,ftol=1e-13,gtol=1e-8))
            numerical=np.array([(objective(fit.x+np.eye(n)[i]*1e-5)[0]-objective(fit.x-np.eye(n)[i]*1e-5)[0])/2e-5 for i in range(n)])
            error=float(np.max(abs(numerical-fit.jac)));pg=projected_gradient(fit.x,fit.jac,bounds)
            fits.append(dict(parameters=fit.x.tolist(),objective=float(fit.fun),qualified=bool(fit.success and pg<.01 and error<.0001),success=bool(fit.success),message=str(fit.message),projected_gradient=pg,derivative_discrepancy=error))
        selected=min(fits,key=lambda f:f['objective']);p=np.array(selected['parameters'])
        arms[arm]=dict(fits=fits,selected=selected,validation=evaluate(p,datasets[1],arm,~datasets[1]['train']))
    p=np.array(arms['signed']['selected']['parameters']);validation=datasets[1]
    controls={'swapped':evaluate(p,validation,'swapped',~validation['train'])}
    permuted=dataset(docs[1],donors[1],True)
    controls['permuted']=evaluate(p,permuted,'signed',~permuted['train'])
    signed=arms['signed']['validation'];baseline=arms['receiver']['validation']
    wins=sum(v>baseline['per_source'][s] for s,v in signed['per_source'].items())
    passed=all(a['selected']['qualified'] for a in arms.values()) and wins>len(signed['per_source'])/2 and all(signed['score']>v for v in [arms['receiver']['validation']['score'],arms['elevation']['validation']['score'],*[c['score'] for c in controls.values()]])
    result=dict(family=2,arms=arms,controls=controls,screen=dict(passed=bool(passed),wins=wins,sources=len(signed['per_source'])),sources=sources,position_improvement_established=False)
    with (HERE/'fit.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(screen=result['screen'],validation={k:v['validation']['score'] for k,v in arms.items()},controls={k:v['score'] for k,v in controls.items()},signed_parameters=arms['signed']['selected']['parameters']),indent=2))


if __name__=='__main__':main()
