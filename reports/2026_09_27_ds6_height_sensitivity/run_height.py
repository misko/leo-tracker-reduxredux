"""Matched fixed-height location profiles; antenna altitude is not known."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_fresh_joint43'))
from run_joint43 import load_model
from run_baseline import site,robust_scores,REFERENCE_RF_HZ,LIGHT_KM_S


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def elevated_site(lat,lon,height_m):
    rec,up=site(lat,lon)
    return rec+up*(height_m/1000.),up


class HeightObjective:
    def __init__(self,base,height_m):self.base=base;self.height_m=height_m
    def evaluate(self,x,exact_banks=None):
        rec,up=elevated_site(*self.base.coordinates(x),self.height_m)
        q=(float(x[2])+5.)*4;index=min(39,max(0,int(np.floor(q))));weight=q-index
        train=joint=0.;predictions=[]
        for t in self.base.tracks:
            if exact_banks is None:
                p,v,_=self.base.banks[t['track_id']]
                pos=p[:,index]*(1-weight)+p[:,index+1]*weight
                vel=v[:,index]*(1-weight)+v[:,index+1]*weight
            else:
                p,v,_=exact_banks[t['track_id']];pos=p[:,0];vel=v[:,0]
            unit=pos-rec;unit/=np.linalg.norm(unit,axis=-1)[...,None]
            pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel,axis=-1)
            visible=np.any((unit@up)[:,t['mask']]>=0,axis=-1)
            a,b=robust_scores(t['y'][None,:]-pred,t['mask'])
            a=np.where(visible,a,-np.inf);b=np.where(visible,b,-np.inf)
            train+=float(logsumexp(a)-np.log(self.base.catalogue_size))
            joint+=float(logsumexp(b)-np.log(self.base.catalogue_size));predictions.append(pred)
        return dict(train=train,held=joint-train,predictions=predictions)


def freeze():
    path=REPORTS/'2026_09_27_ds6_fresh_joint43/protocol.json';old=json.loads(path.read_text())
    devpath=REPORTS/'2026_09_27_ds6_curvature_refit/protocol.json'
    dev=json.loads(devpath.read_text())['development_sessions']
    files=[path,devpath,REPORTS/'2026_09_27_ds6_fresh_joint43/run_joint43.py']+[REPORTS/name for name in old['files']]
    protocol=dict(source_sha256=digest(Path(__file__)),files={str(p.relative_to(REPORTS)):digest(p) for p in files},
        frame_source_sha256=digest(REPORTS.parent/'src/leo/sky/frames.py'),height_datum='WGS84 ellipsoidal metres',
        sessions=dev,center=old['center'],heights_m=[0.,100.,250.,500.,1000.],
        model='Same corrected causal elements, candidate mixtures, Student-t4 fixed100Hz, training-profiled offsets; receiver ECEF shifted along geodetic normal',
        optimization='Each fixed height has three matched starts at baseline east/north and tau baseline,-2,+2; same +/-12km and +/-5s bounds',
        selection='Training likelihood selects each height winner and the discrete profile winner; held data and reference never select',
        scope='Four fixed development scans; sensitivity grid is not measured antenna altitude, terrain, survey prior, or complete uncertainty marginalization',
        limitation='Inherited candidate proposals and zero-degree local elevation cutoff; conditional local analysis, no new RF')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(session):
    protocol=json.loads((HERE/'protocol.json').read_text());assert session in protocol['sessions']
    assert digest(Path(__file__))==protocol['source_sha256']
    assert digest(REPORTS.parent/'src/leo/sky/frames.py')==protocol['frame_source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    base,x0,banks=load_model(session,protocol['center']);arms=[]
    for height in protocol['heights_m']:
        model=HeightObjective(base,height);runs=[]
        for tau in [x0[2],-2.,2.]:
            initial=np.array([x0[0],x0[1],tau])
            fit=minimize(lambda x:-model.evaluate(x)['train'],initial,method='L-BFGS-B',bounds=[(-12.,12.),(-12.,12.),(-5.,5.)],
                options=dict(maxiter=100,maxfun=900,ftol=1e-10,gtol=1e-5,eps=1e-4))
            scores=model.evaluate(fit.x);lat,lon=base.coordinates(fit.x)
            runs.append(dict(x=fit.x.tolist(),latitude=lat,longitude=lon,train=scores['train'],held=scores['held'],
                success=bool(fit.success),message=str(fit.message),nfev=int(fit.nfev),
                bound_hit=bool(any(abs(v)>=b-1e-3 for v,b in zip(fit.x,[12.,12.,5.])))))
        best=max(runs,key=lambda r:r['train']);x=np.array(best['x'])
        exact=model.evaluate(x,exact_banks=banks(np.array([x[2]])));approx=model.evaluate(x)
        deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(exact['predictions'],approx['predictions'],strict=True))
        arms.append(dict(height_m=height,best=best,runs=runs,exact_train=exact['train'],exact_held=exact['held'],maximum_interpolation_error_hz=deviation))
        print(json.dumps(dict(session=session,height_m=height,train=best['train'],success=best['success'])),flush=True)
    selected=max(arms,key=lambda a:a['best']['train'])
    result=dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'protocol.json'),arms=arms,
        selected_height_m=selected['height_m'],selected_height_at_grid_endpoint=selected['height_m'] in [min(protocol['heights_m']),max(protocol['heights_m'])])
    with output.open('x') as f:json.dump(result,f,indent=2)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--session');args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.session)
