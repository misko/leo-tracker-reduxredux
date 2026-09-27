"""All-track stationary offsets with envelope gradients and exact orbit audits."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from fast_solver import profile

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_fresh_joint43'))
from run_joint43 import load_model
from run_baseline import site,REFERENCE_RF_HZ,LIGHT_KM_S

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class Stationary:
    def __init__(self,base):self.base=base;self.calls=0
    def prediction(self,t,x,exact=None):
        rec,up=site(*self.base.coordinates(x))
        if exact is None:
            p,v,_=self.base.banks[t['track_id']];q=(x[2]+5)*4;lo=min(39,max(0,int(np.floor(q))));w=q-lo
            pos=p[:,lo]*(1-w)+p[:,lo+1]*w;vel=v[:,lo]*(1-w)+v[:,lo+1]*w
        else:
            p,v,_=exact[t['track_id']];pos=p[:,0];vel=v[:,0]
        unit=pos-rec;unit/=np.linalg.norm(unit,axis=-1)[...,None]
        return -REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel,axis=-1),np.any((unit@up)[:,t['mask']]>=0,axis=-1)

    def evaluate(self,x,gradient=False,exact=None):
        self.calls+=1;train=held=0.;g=np.zeros(3);maximum=0.;predictions=[]
        for t in self.base.tracks:
            pred,visible=self.prediction(t,x,exact);r=t['y'][None,:]-pred
            a,b,audits,offset=profile(r,t['mask'])
            if not all(v['converged'] for v in audits):raise RuntimeError('Offset stationarity check failed')
            maximum=max(maximum,max(abs(v['gradient']) for v in audits))
            a=np.where(visible,a,-np.inf);b=np.where(visible,b,-np.inf);normal=logsumexp(a)
            train+=float(normal-np.log(self.base.catalogue_size));held+=float(logsumexp(b)-normal)
            if gradient:
                residual=r[:,t['mask']]-offset[:,None];slope=5*residual/(40000+residual**2)
                responsibilities=np.exp(a-normal)
                for j in range(3):
                    # Geometry finite differences only; stationary offsets
                    # permit envelope derivatives without re-solving offsets.
                    step=1e-4 if j<2 else 1e-5
                    plus=x.copy();minus=x.copy();plus[j]+=step;minus[j]-=step
                    if j==2:plus[j]=min(5.,plus[j]);minus[j]=max(-5.,minus[j])
                    dp=(self.prediction(t,plus)[0]-self.prediction(t,minus)[0])/(plus[j]-minus[j])
                    g[j]+=float(responsibilities@np.sum(slope*dp[:,t['mask']],axis=1))
            predictions.append(pred)
        return dict(train=train,held=held,gradient=g,max_offset_gradient=maximum,predictions=predictions)

    def value_gradient(self,x):
        r=self.evaluate(x,True)
        return -r['train'],-r['gradient']


def freeze():
    oldpath=REPORTS/'2026_09_27_ds6_fresh_joint43/protocol.json';old=json.loads(oldpath.read_text())
    devpath=REPORTS/'2026_09_27_ds6_curvature_refit/protocol.json'
    files=[oldpath,devpath,REPORTS/'2026_09_27_ds6_fresh_joint43/run_joint43.py',HERE/'fast_solver.py',REPORTS/'2026_09_27_ds6_stationary_offsets/solver.py']+[REPORTS/name for name in old['files']]
    protocol=dict(source_sha256=digest(Path(__file__)),files={str(p.relative_to(REPORTS)):digest(p) for p in files},
        sessions=old['splits']['all'],development_sessions=json.loads(devpath.read_text())['development_sessions'],center=old['center'],
        model='Stationary penalized offsets on ALL tracks and inherited candidate rows; same t4 scale100; finite multistart scalar search',
        optimizer='Envelope likelihood gradient with central geometry derivatives; baseline position at tau baseline,-2,+2; +/-12km,+/-5s; training-only selection',
        audit='Exact propagation and full-objective finite difference gradient at selected winner',
        limits='Inherited approximate shortlist may omit modes under new profiler; local conditional estimate; no global scalar or geographic guarantee; no ground truth loaded')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(session):
    start=time.monotonic();p=json.loads((HERE/'protocol.json').read_text());assert session in p['sessions']
    assert digest(Path(__file__))==p['source_sha256']
    for name,value in p['files'].items():assert digest(REPORTS/name)==value
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    base,x0,banks=load_model(session,p['center']);model=Stationary(base);runs=[]
    for tau in [x0[2],-2.,2.]:
        fit=minimize(model.value_gradient,np.r_[x0[:2],tau],jac=True,method='L-BFGS-B',bounds=[(-12,12),(-12,12),(-5,5)],
            options=dict(maxiter=100,maxfun=200,ftol=1e-10,gtol=1e-5,maxls=30))
        r=model.evaluate(fit.x);lat,lon=base.coordinates(fit.x)
        runs.append(dict(x=fit.x.tolist(),latitude=lat,longitude=lon,train=r['train'],held=r['held'],max_offset_gradient=r['max_offset_gradient'],
            success=bool(fit.success),message=str(fit.message),nfev=int(fit.nfev),bound_hit=bool(any(abs(v)>=b-1e-3 for v,b in zip(fit.x,[12,12,5])))))
        print(json.dumps(dict(session=session,elapsed_s=time.monotonic()-start,**runs[-1])),flush=True)
    best=max(runs,key=lambda r:r['train']);x=np.array(best['x']);approx=model.evaluate(x,True);exact=model.evaluate(x,exact=banks(np.array([x[2]])))
    numeric=[]
    for j in range(3):
        step=1e-4;plus=x.copy();minus=x.copy();plus[j]+=step;minus[j]-=step
        if j==2:plus[j]=min(5.,plus[j]);minus[j]=max(-5.,minus[j])
        numeric.append((model.evaluate(plus)['train']-model.evaluate(minus)['train'])/(plus[j]-minus[j]))
    deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(exact['predictions'],approx['predictions'],strict=True))
    result=dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'protocol.json'),best=best,runs=runs,
        exact_train=exact['train'],exact_held=exact['held'],maximum_interpolation_error_hz=deviation,
        envelope_gradient=approx['gradient'].tolist(),numeric_gradient=numeric,
        maximum_gradient_difference=float(np.max(np.abs(approx['gradient']-numeric))),elapsed_s=time.monotonic()-start)
    output.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--session');a=parser.parse_args()
    if a.freeze:freeze()
    else:run(a.session)
