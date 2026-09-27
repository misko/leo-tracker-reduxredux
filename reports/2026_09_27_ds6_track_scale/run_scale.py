"""Training-calibrated track noise; no evaluation coordinate is loaded."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'2026_09_27_ds6_joint_drift'))
from run_joint import (Objective, LIGHT_KM_S, REFERENCE_RF_HZ, site,
                       TleArchiveReader, exclude_labelled_starlink_debris,
                       parse_element_sets, propagate_candidate_states, robust_scores)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def training_scale(residual, mask):
    values = residual[mask]
    # t4 has median absolute deviation 0.740697 scale units.
    return float(np.clip(np.median(np.abs(values-np.median(values)))/0.7406970841, 20., 1000.))


class ScaledObjective(Objective):
    def evaluate(self, x, drift=False, exact_banks=None):
        assert not drift
        rec, up = site(*self.coordinates(x))
        q = (float(x[2])+5.)*4
        index = min(39,max(0,int(np.floor(q))))
        weight = q-index
        train = joint = 0.
        predictions = []
        for t in self.tracks:
            p,v,_ = (self.banks if exact_banks is None else exact_banks)[t['track_id']]
            if exact_banks is None:
                pos = p[:,index]*(1-weight)+p[:,index+1]*weight
                vel = v[:,index]*(1-weight)+v[:,index+1]*weight
            else:
                pos,vel = p[:,0],v[:,0]
            unit = pos-rec
            unit /= np.linalg.norm(unit,axis=-1)[...,None]
            pred = -REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel,axis=-1)
            visible = np.any((unit@up)[:,t['mask']]>=0,axis=-1)
            a,b = robust_scores(t['y'][None,:]-pred,t['mask'],t['sigma'])
            train += float(logsumexp(np.where(visible,a,-np.inf))-np.log(self.catalogue_size))
            joint += float(logsumexp(np.where(visible,b,-np.inf))-np.log(self.catalogue_size))
            predictions.append(pred)
        return dict(train=train,held=joint-train,predictions=predictions)


def freeze():
    parent = HERE.parent/'2026_09_27_ds6_joint_drift'
    old = json.loads((parent/'protocol.json').read_text())
    protocol = dict(inputs=old['inputs'],center=old['center'],source_sha256=digest(Path(__file__)),
        baseline_sha256={name.replace('-plan',''):digest(parent/name.replace('-plan','')) for name in old['inputs']},
        dependencies={str(p.relative_to(HERE.parent)):digest(p) for p in [parent/'run_joint.py',
            HERE.parent/'2026_09_27_ds6_cfo_transfer/run.py',HERE.parent/'2026_09_27_ds6_exact_timing/robust.py']},
        calibration='At frozen no-drift training winner, select candidate by training score; training MAD / t4 MAD; clamp 20..1000 Hz; freeze before refit',
        arms=['fixed_100','training_scale'],selection='Training likelihood only; shared continuous scan timing; no receiver drift',
        starts='Previous no-drift winner at previous tau and -2,+2 seconds',
        limits='Local +/-12 km, timing +/-5 seconds; inherited approximate catalogue shortlists',
        scope='All four frozen development scans, never selected by geographic error')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(session):
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(Path(__file__))==protocol['source_sha256']
    for name,value in protocol['dependencies'].items():assert digest(HERE.parent/name)==value
    source=HERE.parent/'2026_09_27_ds6_common_rate_validation'/f'{session}-plan.json'
    assert digest(source)==protocol['inputs'][source.name]
    previous=HERE.parent/'2026_09_27_ds6_joint_drift'/f'{session}.json'
    assert digest(previous)==protocol['baseline_sha256'][previous.name]
    prior=json.loads(previous.read_text())['arms']['no_drift']['best']
    data=json.loads(source.read_text())
    transfer=json.loads((HERE.parent/'2026_09_27_ds6_cfo_transfer'/f'{session}.json').read_text())
    chosen={}
    for stage in transfer['stages']:
        for key,values in stage['shortlists'].items():chosen.setdefault(key,set()).update(values)
    tracks=[]
    for t in data['tracks']:
        if t['track_id'] not in chosen:continue
        t=dict(t,t=np.array(t['times_s']),y=np.array(t['measured_hz']),mask=np.array(t['training_mask'],dtype=bool),sigma=100.)
        t['centered_t']=t['t']-t['t'][t['mask']].mean()
        tracks.append(t)
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    snap=archive.select_latest_before(data['start_utc_ns']-505_000_000_000)
    assert snap.digest==data['snapshot_digest']
    payload,_=exclude_labelled_starlink_debris(archive.read(snap));cat=parse_element_sets(payload)
    def banks(taus):
        return {t['track_id']:propagate_candidate_states(cat,np.array(sorted(chosen[t['track_id']])),data['start_utc_ns'],t['t'],taus) for t in tracks}
    bank=banks(np.arange(-5.,5.001,.25))
    model=ScaledObjective(tracks,bank,protocol['center'],len(cat.satellite_numbers),[])
    x0=np.array(prior['x'])
    calibration=[]
    initial=model.evaluate(x0)
    rec,up=site(*model.coordinates(x0))
    # The selected training candidate must satisfy the same visibility gate.
    exact=banks(np.array([x0[2]]))
    for t,pred in zip(tracks,model.evaluate(x0,exact_banks=exact)['predictions'],strict=True):
        res=t['y'][None,:]-pred
        score,_=robust_scores(res,t['mask'])
        pos=exact[t['track_id']][0][:,0]-rec
        visible=np.any((pos@up)[:,t['mask']]>=0,axis=-1)
        idx=int(np.argmax(np.where(visible,score,-np.inf)))
        sigma=training_scale(res[idx],t['mask'])
        centered=res[idx,t['mask']]-np.median(res[idx,t['mask']])
        calibration.append(dict(track_id=t['track_id'],receiver_id=t['receiver_id'],channel=t['channel'],
            candidate_index=int(exact[t['track_id']][2][idx]),sigma=sigma,
            training_count=int(t['mask'].sum()),span_s=float(np.ptp(t['t'])),
            training_residual_rms_hz=float(np.sqrt(np.mean(centered**2)))))
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    results={}
    for arm in protocol['arms']:
        for t,c in zip(tracks,calibration,strict=True):t['sigma']=100. if arm=='fixed_100' else c['sigma']
        runs=[]
        for tau in [x0[2],-2.,2.]:
            start=x0.copy();start[2]=tau
            fit=minimize(lambda x:-model.evaluate(x)['train'],start,method='L-BFGS-B',
                bounds=[(-12.,12.),(-12.,12.),(-5.,5.)],
                options=dict(maxiter=70,maxfun=650,ftol=1e-10,gtol=1e-5,eps=1e-4))
            score=model.evaluate(fit.x);lat,lon=model.coordinates(fit.x)
            runs.append(dict(x=fit.x.tolist(),latitude=lat,longitude=lon,train=score['train'],held=score['held'],
                success=bool(fit.success),message=str(fit.message),nfev=int(fit.nfev),
                bound_hit=bool(any(abs(v)>=b-1e-3 for v,b in zip(fit.x,[12.,12.,5.])))))
        best=max(runs,key=lambda r:r['train'])
        approximate=model.evaluate(np.array(best['x']))
        verified=model.evaluate(np.array(best['x']),exact_banks=banks(np.array([best['x'][2]])))
        deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(approximate['predictions'],verified['predictions'],strict=True))
        results[arm]=dict(best=best,runs=runs,exact_train=verified['train'],exact_held=verified['held'],maximum_interpolation_error_hz=deviation)
        output.write_text(json.dumps(dict(session_id=session,protocol_sha256=digest(HERE/'protocol.json'),complete=len(results)==2,
            calibration=calibration,arms=results),indent=2)+'\n')
        print(json.dumps(dict(session=session,arm=arm,**best)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--session')
    args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.session)
