"""Matched continuous-location CFO arms with frozen receiver-drift priors."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / '2026_09_27_ds6_cfo_transfer'))
from run import (LIGHT_KM_S, REFERENCE_RF_HZ, TleArchiveReader,
    exclude_labelled_starlink_debris, parse_element_sets, propagate_candidate_states,
    robust_scores, site)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze():
    old = REPORTS/'2026_09_27_ds6_cfo_transfer'
    prior = json.loads((old/'protocol.json').read_text())
    protocol = dict(inputs=prior['inputs'], center=prior['center'],
        transfer_sha256={name.replace('-plan',''):digest(old/name.replace('-plan',''))
                         for name in prior['inputs']},
        source_sha256=digest(Path(__file__)),
        robust_sha256=digest(REPORTS/'2026_09_27_ds6_exact_timing/robust.py'),
        model='Student-t4 100 Hz; training-only per-track offset; catalogue mixture',
        arms=['no_drift','receiver_drift'], drift_prior_std_hz_s=5., drift_bounds_hz_s=[-20.,20.],
        position_bounds_km=[-12.,12.], timing_bounds_s=[-5.,5.],
        starts='previous training winner and same location at tau=-2,+2; zero initial drift',
        propagation='quarter-second timing interpolation; exact propagation audit at winner',
        selection='penalized training likelihood only; held observations never optimize',
        scope='Local conditional transfer; inherited approximate catalogue shortlists; no roof coordinate loaded',
        limitation='Profile timing replaces earlier timing integration equally in both matched arms')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


class Objective:
    def __init__(self, tracks, banks, center, catalogue_size, receivers, drift_std=5.):
        self.tracks, self.banks, self.center = tracks, banks, center
        self.catalogue_size, self.receivers, self.drift_std = catalogue_size, receivers, drift_std
        self.calls = 0

    def coordinates(self, x):
        lat = self.center[0]+x[1]/111.195
        lon = self.center[1]+x[0]/(111.195*np.cos(np.radians(self.center[0])))
        return float(lat),float(lon)

    def evaluate(self,x,drift,exact_banks=None):
        self.calls += 1
        rec,up=site(*self.coordinates(x));tau=float(x[2]);q=(tau+5.)*4
        index=min(39,max(0,int(np.floor(q))));weight=q-index
        rates=dict(zip(self.receivers,x[3:],strict=True)) if drift else {rx:0. for rx in self.receivers}
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
            visible=np.any((unit@up)[:,t['mask']]>=0,axis=-1)
            res=t['y'][None,:]-pred-rates[t['receiver_id']]*t['centered_t'][None,:]
            a,b=robust_scores(res,t['mask']);a=np.where(visible,a,-np.inf);b=np.where(visible,b,-np.inf)
            train+=float(logsumexp(a)-np.log(self.catalogue_size))
            joint+=float(logsumexp(b)-np.log(self.catalogue_size))
            predictions.append(pred)
        penalty=sum(b*b for b in rates.values())/(2*self.drift_std**2)
        return dict(train=train, penalized_train=train-penalty,held=joint-train,
                    rates=rates,predictions=predictions)


def run(session):
    started=time.monotonic();protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(Path(__file__))==protocol['source_sha256']
    assert digest(REPORTS/'2026_09_27_ds6_exact_timing/robust.py')==protocol['robust_sha256']
    source=REPORTS/'2026_09_27_ds6_common_rate_validation'/f'{session}-plan.json'
    assert digest(source)==protocol['inputs'][source.name]
    old=REPORTS/'2026_09_27_ds6_cfo_transfer'/f'{session}.json'
    assert digest(old)==protocol['transfer_sha256'][old.name]
    previous=json.loads(old.read_text());data=json.loads(source.read_text())
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    chosen={}
    for stage in previous['stages']:
        for key,values in stage['shortlists'].items():chosen.setdefault(key,set()).update(values)
    tracks=[]
    for t in data['tracks']:
        if t['track_id'] not in chosen:continue
        row=dict(t,t=np.array(t['times_s']),y=np.array(t['measured_hz']),mask=np.array(t['training_mask'],dtype=bool))
        row['centered_t']=row['t']-row['t'][row['mask']].mean();tracks.append(row)
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));snap=archive.select_latest_before(data['start_utc_ns']-505_000_000_000)
    assert snap.digest==data['snapshot_digest']
    payload,_=exclude_labelled_starlink_debris(archive.read(snap));cat=parse_element_sets(payload)
    taus=np.arange(-5.,5.001,.25)
    banks={t['track_id']:propagate_candidate_states(cat,np.array(sorted(chosen[t['track_id']])),
        data['start_utc_ns'],t['t'],taus) for t in tracks}
    receivers=sorted({t['receiver_id'] for t in tracks});center=protocol['center']
    objective=Objective(tracks,banks,center,len(cat.satellite_numbers),receivers,protocol['drift_prior_std_hz_s'])
    prior=previous['stages'][-1]['best']
    east=(prior['longitude']-center[1])*111.195*np.cos(np.radians(center[0]));north=(prior['latitude']-center[0])*111.195
    results={}
    for arm in protocol['arms']:
        drift=arm=='receiver_drift';runs=[]
        bounds=[tuple(protocol['position_bounds_km'])]*2+[tuple(protocol['timing_bounds_s'])]
        if drift:bounds += [tuple(protocol['drift_bounds_hz_s'])]*len(receivers)
        for tau in [prior['map_time_s'],-2.,2.]:
            initial=np.array([east,north,tau]+([0.]*len(receivers) if drift else []))
            result=minimize(lambda x:-objective.evaluate(x,drift)['penalized_train'],initial,
                method='L-BFGS-B',bounds=bounds,
                options=dict(maxiter=70,maxfun=650,ftol=1e-10,gtol=1e-5,eps=1e-4))
            scores=objective.evaluate(result.x,drift);lat,lon=objective.coordinates(result.x)
            row=dict(initial_tau=tau,x=result.x.tolist(),latitude=lat,longitude=lon,
                     train=scores['train'],penalized_train=scores['penalized_train'],held=scores['held'],
                     rates=scores['rates'],success=bool(result.success),message=str(result.message),
                     nfev=int(result.nfev),iterations=int(result.nit),
                     bound_hit=any(abs(x-a)<1e-3 or abs(x-b)<1e-3 for x,(a,b) in zip(result.x,bounds)))
            runs.append(row);print(json.dumps(dict(session=session,arm=arm,**row)),flush=True)
        best=max(runs,key=lambda r:r['penalized_train'])
        exact={t['track_id']:propagate_candidate_states(cat,np.array(sorted(chosen[t['track_id']])),
            data['start_utc_ns'],t['t'],np.array([best['x'][2]])) for t in tracks}
        approximate=objective.evaluate(np.array(best['x']),drift)
        verified=objective.evaluate(np.array(best['x']),drift,exact)
        deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(approximate['predictions'],verified['predictions'],strict=True))
        results[arm]=dict(runs=runs,best=best,exact_train=verified['train'],exact_held=verified['held'],
                         maximum_interpolation_error_hz=deviation)
        output.write_text(json.dumps(dict(session_id=session,complete=len(results)==2,
            protocol_sha256=digest(HERE/'protocol.json'),input_sha256=digest(source),arms=results,
            elapsed_s=time.monotonic()-started),indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--session')
    args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.session)
