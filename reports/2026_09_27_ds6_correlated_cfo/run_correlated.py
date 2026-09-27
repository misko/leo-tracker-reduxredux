"""Matched track-level t4 controls with cross-subset slope-scale learning."""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from density import TrackDensity

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_full_stationary'))
from run_full import Stationary,load_model,digest


class Correlated:
    def __init__(self,base,slope_scale):
        self.base=base;self.geometry=Stationary(base)
        self.densities={t['track_id']:TrackDensity(t['t'],t['mask'],slope_scale) for t in base.tracks}

    def evaluate(self,x,exact=None):
        train=held=0.;predictions=[]
        for t in self.base.tracks:
            pred,visible=self.geometry.prediction(t,x,exact)
            a,b=self.densities[t['track_id']].scores(t['y'][None,:]-pred)
            a=np.where(visible,a,-np.inf);b=np.where(visible,b,-np.inf);normal=logsumexp(a)
            train+=float(normal-np.log(self.base.catalogue_size));held+=float(logsumexp(b)-normal)
            predictions.append(pred)
        return dict(train=train,held=held,predictions=predictions)

    def value_gradient(self,x):
        value=self.evaluate(x)['train'];g=[]
        for j in range(3):
            plus=x.copy();minus=x.copy();plus[j]+=1e-4;minus[j]-=1e-4
            if j==2:plus[j]=min(5.,plus[j]);minus[j]=max(-5.,minus[j])
            g.append((self.evaluate(plus)['train']-self.evaluate(minus)['train'])/(plus[j]-minus[j]))
        return -value,-np.array(g)


def freeze():
    full=REPORTS/'2026_09_27_ds6_full_stationary';p=json.loads((full/'protocol.json').read_text())
    joint=REPORTS/'2026_09_27_ds6_stationary_joint43/protocol.json';splits=json.loads(joint.read_text())['splits']
    transfer=REPORTS/'2026_09_27_ds6_satellite_slope_transfer'
    donors={n:json.loads((transfer/f'{n}.json').read_text()) for n in ['A','B']}
    scales={n:float(np.median(np.abs([r['training_slope_hz_s'] for r in d['tracks']]))/.6744897501960817) for n,d in donors.items()}
    calibration={}
    for s in p['development_sessions']:
        target='A' if s in splits['A'] else 'B';donor='B' if target=='A' else 'A'
        assert all(r['session_id'] not in splits[target] for r in donors[donor]['tracks'])
        calibration[s]=dict(target_subset=target,donor_subset=donor,slope_scale_hz_s=scales[donor])
    files=[full/'protocol.json',full/'run_full.py',HERE/'density.py',joint,transfer/'protocol.json']
    files += [REPORTS/f for f in p['files']]
    files += [transfer/f'{n}.json' for n in ['A','B']]
    files += [full/f'{s}.json' for s in p['development_sessions']]
    protocol=dict(source_sha256=digest(HERE/'run_correlated.py'),files={str(f.relative_to(REPORTS)):digest(f) for f in files},
        sessions=p['development_sessions'],center=p['center'],calibration=calibration,
        model='Multivariate Student-t4 per track, scale covariance 100^2 I + 1e12 ones + slope_scale^2 t t^T; t centered on training mean; exact offset/slope random-effects marginal density',
        arms=['zero_slope','cross_subset_slope'],scale_rule='Opposite-subset training residual median absolute OLS slope / normal median-absolute constant; zero mean; no geographic reference',
        optimizer='Three corrected-baseline horizontal starts at baseline tau,-2,+2; +/-12km,+/-5sec; training winner; central full-objective derivatives',
        limits='Changes pointwise t4 to joint track-level t4 and integrates offset; zero-slope arm isolates slope addition within the new model; inherited shortlist not revalidated for this likelihood; plug-in scale uncertainty; local development experiment')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(session):
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    p=json.loads((HERE/'protocol.json').read_text());assert session in p['sessions']
    assert digest(HERE/'run_correlated.py')==p['source_sha256']
    for path,value in p['files'].items():assert digest(REPORTS/path)==value
    base,_,banks=load_model(session,p['center'])
    old=json.loads((REPORTS/'2026_09_27_ds6_full_stationary'/f'{session}.json').read_text());arms={}
    for name in p['arms']:
        scale=0. if name=='zero_slope' else p['calibration'][session]['slope_scale_hz_s']
        model=Correlated(base,scale);runs=[]
        for tau in [old['best']['x'][2],-2.,2.]:
            fit=minimize(model.value_gradient,np.r_[old['best']['x'][:2],tau],jac=True,method='L-BFGS-B',
                bounds=[(-12,12),(-12,12),(-5,5)],options=dict(maxiter=100,maxfun=200,ftol=1e-10,gtol=1e-5,maxls=30))
            result=model.evaluate(fit.x);lat,lon=base.coordinates(fit.x)
            row=dict(x=fit.x.tolist(),latitude=lat,longitude=lon,train=result['train'],held=result['held'],
                success=bool(fit.success),message=str(fit.message),nfev=int(fit.nfev),bound_hit=bool(any(abs(v)>=b-1e-3 for v,b in zip(fit.x,[12,12,5]))))
            runs.append(row);print(json.dumps(dict(arm=name,**row)),flush=True)
        best=max(runs,key=lambda r:r['train']);x=np.array(best['x']);approx=model.evaluate(x);exact=model.evaluate(x,banks(np.array([x[2]])))
        deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(approx['predictions'],exact['predictions'],strict=True))
        arms[name]=dict(runs=runs,best=best,slope_scale_hz_s=scale,exact_train=exact['train'],exact_held=exact['held'],maximum_interpolation_error_hz=deviation)
    with output.open('x') as f:json.dump(dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'protocol.json'),arms=arms),f,indent=2)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');p.add_argument('--session');a=p.parse_args()
    if a.freeze:freeze()
    else:run(a.session)
