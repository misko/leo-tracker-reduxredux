"""Profile training-only per-track drift under a frozen 10 Hz/s prior."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln,logsumexp

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_group_consistency'))
from run_groups import load,ScaledObjective
from run_scale import site,REFERENCE_RF_HZ,LIGHT_KM_S


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def profile(residual,time,mask,sigma,drift_std=10.,iterations=30):
    """Per-candidate robust ridge line fit; held residuals never enter the fit."""
    y=residual[...,mask];t=time[mask]
    offset=np.median(y,axis=-1);slope=np.zeros_like(offset)
    for _ in range(iterations):
        z=(y-offset[...,None]-slope[...,None]*t)/sigma
        w=5/(4+z*z)/sigma**2
        a=w.sum(axis=-1)+1e-12;b=(w*t).sum(axis=-1)
        c=(w*t*t).sum(axis=-1)+1/drift_std**2
        d=(w*y).sum(axis=-1);e=(w*y*t).sum(axis=-1)
        det=a*c-b*b
        offset=(d*c-b*e)/det;slope=(a*e-b*d)/det
    z=(residual-offset[...,None]-slope[...,None]*time)/sigma
    density=gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(sigma)-2.5*np.log1p(z*z/4)
    train=density[...,mask].sum(axis=-1)-.5*offset**2/1e12-.5*(slope/drift_std)**2
    joint=train+density[...,~mask].sum(axis=-1)
    return train,joint,offset,slope


class DriftObjective(ScaledObjective):
    def evaluate(self,x,drift=False,exact_banks=None,iterations=30):
        rec,up=site(*self.coordinates(x));q=(float(x[2])+5.)*4
        index=min(39,max(0,int(np.floor(q))));weight=q-index
        train=joint=0.;predictions=[];details=[]
        for t in self.tracks:
            p,v,ids=(self.banks if exact_banks is None else exact_banks)[t['track_id']]
            if exact_banks is None:
                pos=p[:,index]*(1-weight)+p[:,index+1]*weight
                vel=v[:,index]*(1-weight)+v[:,index+1]*weight
            else:pos,vel=p[:,0],v[:,0]
            unit=pos-rec;unit/=np.linalg.norm(unit,axis=-1)[...,None]
            pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel,axis=-1)
            visible=np.any((unit@up)[:,t['mask']]>=0,axis=-1)
            a,b,offset,slope=profile(t['y'][None,:]-pred,t['centered_t'],t['mask'],t['sigma'],iterations=iterations)
            a=np.where(visible,a,-np.inf);b=np.where(visible,b,-np.inf)
            train+=float(logsumexp(a)-np.log(self.catalogue_size))
            joint+=float(logsumexp(b)-np.log(self.catalogue_size))
            idx=int(np.argmax(a));details.append(dict(track_id=t['track_id'],candidate_index=int(ids[idx]),
                slope_hz_s=float(slope[idx]),offset_hz=float(offset[idx])))
            predictions.append(pred)
        return dict(train=train,held=joint-train,predictions=predictions,details=details)


def freeze():
    parent=REPORTS/'2026_09_27_ds6_group_consistency'
    old=json.loads((parent/'protocol.json').read_text())
    paths=[parent/'protocol.json',parent/'run_groups.py']+[REPORTS/name for name in {**old['dependencies'],**old['inputs']}]
    protocol=dict(sessions=old['sessions'],source_sha256=digest(Path(__file__)),
        files={str(p.relative_to(REPORTS)):digest(p) for p in paths},
        prior_std_hz_s=10.,iterations=30,iteration_audit=60,
        model='Training-profiled track offset plus track slope; Student-t4 and inherited frozen scales; Gaussian slope prior',
        starts='Previous training winner; donor center with previous timing; previous position at timing -2,+2',
        bounds='East/north +/-12 km, timing +/-5 s; no geographic reference loaded',
        selection='Highest training score; held visits never optimize',
        scope='Four frozen development scans; inherited approximate candidate shortlists; penalized profile scores, not integrated evidence')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(session):
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(Path(__file__))==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    p,tracks,bank,banks,size,x0=load(session)
    model=DriftObjective(tracks,bank,p['center'],size,[])
    baseline=ScaledObjective(tracks,bank,p['center'],size,[])
    base=baseline.evaluate(x0,exact_banks=banks(np.array([x0[2]])))
    starts=[x0,np.array([0.,0.,x0[2]]),np.r_[x0[:2],-2.],np.r_[x0[:2],2.]];runs=[]
    for initial in starts:
        fit=minimize(lambda x:-model.evaluate(x)['train'],initial,method='L-BFGS-B',bounds=[(-12.,12.),(-12.,12.),(-5.,5.)],
            options=dict(maxiter=100,maxfun=900,ftol=1e-10,gtol=1e-5,eps=1e-4))
        score=model.evaluate(fit.x);lat,lon=model.coordinates(fit.x)
        row=dict(x=fit.x.tolist(),latitude=lat,longitude=lon,train=score['train'],held=score['held'],success=bool(fit.success),
            message=str(fit.message),nfev=int(fit.nfev),bound_hit=bool(any(abs(v)>=b-1e-3 for v,b in zip(fit.x,[12.,12.,5.]))))
        runs.append(row);print(json.dumps(dict(session=session,**row)),flush=True)
    best=max(runs,key=lambda r:r['train']);x=np.array(best['x']);exact=banks(np.array([x[2]]))
    verified=model.evaluate(x,exact_banks=exact);audit=model.evaluate(x,exact_banks=exact,iterations=60)
    approx=model.evaluate(x)
    deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(approx['predictions'],verified['predictions'],strict=True))
    result=dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'protocol.json'),runs=runs,best=best,
        exact_train=verified['train'],exact_held=verified['held'],baseline_exact_held=base['held'],
        held_gain=verified['held']-base['held'],details=verified['details'],
        iteration_audit=dict(train_change=audit['train']-verified['train'],held_change=audit['held']-verified['held']),
        maximum_interpolation_error_hz=deviation)
    with output.open('x') as f:json.dump(result,f,indent=2)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--session');args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.session)
