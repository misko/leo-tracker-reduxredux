"""Matched local position refits with receiver linear/quadratic frequency drift."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_full_cfo'))
from run_baseline import (Objective as BaseObjective,site,robust_scores,REFERENCE_RF_HZ,
    LIGHT_KM_S,TleArchiveReader,exclude_labelled_starlink_debris,parse_element_sets,
    propagate_candidate_states)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class Objective(BaseObjective):
    """Drift coordinates are 100 Hz units; all priors are training-only."""
    def __init__(self,tracks,banks,center,catalogue_size,receivers,order):
        super().__init__(tracks,banks,center,catalogue_size,receivers)
        self.order=order
        self.design={}
        for t in tracks:
            u=(t['t']-150.)/150.
            design=np.stack([u**degree for degree in range(1,order+1)],axis=-1) if order else np.empty((len(u),0))
            self.design[t['track_id']]=(design-design[t['mask']].mean(axis=0))*REFERENCE_RF_HZ/t['rf_hz']*100.

    def evaluate(self,x,exact_banks=None):
        self.calls+=1
        rec,up=site(*self.coordinates(x));q=(float(x[2])+5.)*4
        index=min(39,max(0,int(np.floor(q))));weight=q-index
        coefficients={rx:x[3+i*self.order:3+(i+1)*self.order] for i,rx in enumerate(self.receivers)}
        train=joint=0.;predictions=[]
        for t in self.tracks:
            if exact_banks is None:
                p,v,_=self.banks[t['track_id']]
                pos=p[:,index]*(1-weight)+p[:,index+1]*weight
                vel=v[:,index]*(1-weight)+v[:,index+1]*weight
            else:
                p,v,_=exact_banks[t['track_id']];pos=p[:,0];vel=v[:,0]
            unit=pos-rec;unit/=np.linalg.norm(unit,axis=-1)[...,None]
            pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel,axis=-1)
            drift=self.design[t['track_id']]@coefficients[t['receiver_id']]
            visible=np.any((unit@up)[:,t['mask']]>=0,axis=-1)
            a,b=robust_scores(t['y'][None,:]-pred-drift[None,:],t['mask'])
            a=np.where(visible,a,-np.inf);b=np.where(visible,b,-np.inf)
            train+=float(logsumexp(a)-np.log(self.catalogue_size))
            joint+=float(logsumexp(b)-np.log(self.catalogue_size))
            predictions.append(pred)
        penalty=float(np.sum(np.asarray(x[3:])**2))/(2*7.5**2)
        return dict(train=train,penalized_train=train-penalty,held=joint-train,predictions=predictions)


def freeze():
    base=REPORTS/'2026_09_27_ds6_full_cfo'
    old=json.loads((base/'protocol.json').read_text())
    paths=[base/'protocol.json',base/'run_baseline.py']+[REPORTS/name for name in old['files']]
    paths += [REPORTS/folder/f'{s}{suffix}.json' for s in old['sessions'] for folder,suffix in
        [('2026_09_27_ds6_full_cfo',''),('2026_09_27_ds6_cfo_dataset','-plan')]]
    development=list(json.loads((REPORTS/'2026_09_27_ds6_joint_drift/protocol.json').read_text())['inputs'])
    protocol=dict(source_sha256=digest(Path(__file__)),sessions=old['sessions'],center=old['center'],
        development_sessions=[name.replace('-plan.json','') for name in development],
        files={str(p.relative_to(REPORTS)):digest(p) for p in paths},orders=[0,1,2],
        clock_coefficient_prior_std_hz=750.,clock_coefficient_bounds_hz=[-4000.,4000.],
        model='Student-t4 scale100Hz; training-profiled offsets; inherited candidate mixtures; per-RX polynomials in (t-150)/150 normalized by 11.2GHz/actual RF',
        optimization='Same baseline position at baseline tau,-2,+2 with zero drift in each arm; bounds +/-12 km and +/-5s; training penalized likelihood selection',
        validation='Inherited random whole-visit masks; exact propagation at winner; later external truth scoring only',
        scope='Conditional local location refit; shortlisted identities are not certain; inherited no-drift shortlists may omit mass under flexible drift',
        development='Same four previously frozen rate-representative scans first; no selection by new geographic outcomes')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(session):
    started=time.monotonic();output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert session in protocol['sessions']
    assert digest(Path(__file__))==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    baseline=json.loads((REPORTS/'2026_09_27_ds6_full_cfo'/f'{session}.json').read_text())
    source=REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json'
    data=json.loads(source.read_text());tracks=[]
    for t in data['tracks']:
        if t['track_id'] not in baseline['shortlists']:continue
        tracks.append(dict(t,t=np.array(t['times_s']),y=np.array(t['measured_hz']),mask=np.array(t['training_mask'],dtype=bool)))
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    snap=archive.select_latest_before(data['start_utc_ns']-505_000_000_000);assert snap.digest==data['snapshot_digest']
    payload,_=exclude_labelled_starlink_debris(archive.read(snap));cat=parse_element_sets(payload)
    def banks(taus):
        return {t['track_id']:propagate_candidate_states(cat,np.array(baseline['shortlists'][t['track_id']]),data['start_utc_ns'],t['t'],taus) for t in tracks}
    bank=banks(np.arange(-5.,5.001,.25));receivers=sorted({t['receiver_id'] for t in tracks})
    previous=baseline['best'];center=protocol['center'];initial_position=np.array(previous['x'][:2])
    arms={}
    for order in protocol['orders']:
        model=Objective(tracks,bank,center,len(cat.satellite_numbers),receivers,order)
        bounds=[(-12.,12.),(-12.,12.),(-5.,5.)]+[(-40.,40.)]*(len(receivers)*order)
        runs=[]
        for tau in [previous['x'][2],-2.,2.]:
            initial=np.r_[initial_position,tau,np.zeros(len(receivers)*order)]
            fit=minimize(lambda x:-model.evaluate(x)['penalized_train'],initial,method='L-BFGS-B',bounds=bounds,
                options=dict(maxiter=160,maxfun=2200,ftol=1e-11,gtol=1e-5,eps=1e-4))
            scores=model.evaluate(fit.x);lat,lon=model.coordinates(fit.x)
            result=dict(initial_tau=tau,x=fit.x.tolist(),latitude=lat,longitude=lon,
                **{k:v for k,v in scores.items() if k!='predictions'},success=bool(fit.success),message=str(fit.message),
                nfev=int(fit.nfev),iterations=int(fit.nit),
                bound_hit=bool(any(abs(x-a)<1e-3 or abs(x-b)<1e-3 for x,(a,b) in zip(fit.x,bounds))))
            runs.append(result);print(json.dumps(dict(session=session,order=order,**result)),flush=True)
        best=max(runs,key=lambda r:r['penalized_train']);x=np.array(best['x'])
        exact=model.evaluate(x,exact_banks=banks(np.array([x[2]])));approx=model.evaluate(x)
        deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(exact['predictions'],approx['predictions'],strict=True))
        arms[str(order)]=dict(runs=runs,best=best,exact_train=exact['train'],exact_held=exact['held'],maximum_interpolation_error_hz=deviation)
        output.write_text(json.dumps(dict(session_id=session,complete=len(arms)==3,protocol_sha256=digest(HERE/'protocol.json'),
            input_sha256=digest(source),receivers=receivers,rate_hz=data['rate_hz'],arms=arms,elapsed_s=time.monotonic()-started),indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--session');args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.session)
