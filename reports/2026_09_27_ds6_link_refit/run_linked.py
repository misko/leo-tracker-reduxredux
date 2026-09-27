"""Matched separate/shared fragment-offset location fits with frozen assignments."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_full_cfo'))
from run_baseline import (Objective,site,robust_scores,REFERENCE_RF_HZ,LIGHT_KM_S,TleArchiveReader,
    exclude_labelled_starlink_debris,parse_element_sets,propagate_candidate_states)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def group_scores(residuals,masks,shared):
    if shared:
        a,b=robust_scores(np.concatenate(residuals),np.concatenate(masks))
        return float(a),float(b-a)
    train=held=0.
    for residual,mask in zip(residuals,masks,strict=True):
        a,b=robust_scores(residual,mask);train+=float(a);held+=float(b-a)
    return train,held


class LinkedObjective:
    def __init__(self,tracks,banks,center,size,groups):
        self.tracks={t['track_id']:t for t in tracks};self.banks=banks;self.groups=groups
        linked={key for g in groups for key in g['track_ids']}
        self.other=Objective([t for t in tracks if t['track_id'] not in linked],banks,center,size,
            sorted({t['receiver_id'] for t in tracks}))
        self.size=size

    def coordinates(self,x):return self.other.coordinates(x)

    def evaluate(self,x,shared,exact_banks=None):
        old=self.other.evaluate(x,False,exact_banks=exact_banks)
        train,held=old['train'],old['held'];predictions=list(old['predictions'])
        rec,up=site(*self.coordinates(x));q=(float(x[2])+5.)*4
        index=min(39,max(0,int(np.floor(q))));weight=q-index
        for group in self.groups:
            residuals=[];masks=[];visible=True
            for key,alias in zip(group['track_ids'],group['aliases'],strict=True):
                t=self.tracks[key];p,v,_=(self.banks if exact_banks is None else exact_banks)[key]
                if exact_banks is None:
                    pos=p[0,index]*(1-weight)+p[0,index+1]*weight
                    vel=v[0,index]*(1-weight)+v[0,index+1]*weight
                else:pos,vel=p[0,0],v[0,0]
                unit=pos-rec;unit/=np.linalg.norm(unit,axis=-1)[:,None]
                pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel,axis=-1)
                visible=visible and bool(np.any((unit@up)[t['mask']]>=0))
                residuals.append(t['y']-alias*group['normalized_alias_hz']-pred);masks.append(t['mask'])
                predictions.append(pred)
            a,b=group_scores(residuals,masks,shared)
            train+=a-len(residuals)*np.log(self.size) if visible else -np.inf
            held+=b
        return dict(train=float(train),held=float(held),predictions=predictions)


def freeze():
    parent=REPORTS/'2026_09_27_ds6_fragment_links'
    old=json.loads((parent/'protocol.json').read_text())
    paths=[parent/'protocol.json',parent/'audit_links.py']+[REPORTS/name for name in old['files']]
    paths += [parent/f'{s}.json' for s in old['sessions']]
    baseline_protocol=REPORTS/'2026_09_27_ds6_full_cfo/protocol.json'
    paths += [REPORTS/name for name in json.loads(baseline_protocol.read_text())['files']]
    protocol=dict(sessions=old['sessions'],source_sha256=digest(Path(__file__)),
        files={str(p.relative_to(REPORTS)):digest(p) for p in paths},
        center=json.loads(baseline_protocol.read_text())['center'],arms=['separate','shared'],
        model='Fixed 100 Hz Student-t4; frozen MAP labels and integer aliases for linked groups in BOTH arms; original catalogue mixtures for all unlinked tracks',
        nuisance='Separate offsets vs one common offset per linked group, fitted on training visits only',
        search='Baseline winner location/timing, donor center with baseline timing, baseline location at tau -2,+2; +/-12 km and +/-5 s bounds',
        selection='Highest training score per arm; unchanged whole-visit held observations evaluate only',
        scope='Four pre-existing development scans including no-link scan; conditional identities, no geographic reference loaded')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(session):
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert session in protocol['sessions'] and digest(Path(__file__))==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    data=json.loads((REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json').read_text())
    baseline=json.loads((REPORTS/'2026_09_27_ds6_full_cfo'/f'{session}.json').read_text())
    groups=json.loads((REPORTS/'2026_09_27_ds6_fragment_links'/f'{session}.json').read_text())['groups']
    chosen=dict(baseline['shortlists'])
    for group in groups:
        for key in group['track_ids']:chosen[key]=[group['candidate_index']]
    tracks=[]
    for t in data['tracks']:
        if t['track_id'] not in chosen:continue
        t=dict(t,t=np.array(t['times_s']),y=np.array(t['measured_hz']),mask=np.array(t['training_mask'],dtype=bool))
        t['centered_t']=t['t']-t['t'][t['mask']].mean();tracks.append(t)
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    snap=archive.select_latest_before(data['start_utc_ns']-505_000_000_000);assert snap.digest==data['snapshot_digest']
    payload,_=exclude_labelled_starlink_debris(archive.read(snap));cat=parse_element_sets(payload)
    def banks(taus):
        return {t['track_id']:propagate_candidate_states(cat,np.array(chosen[t['track_id']]),data['start_utc_ns'],t['t'],taus) for t in tracks}
    bank=banks(np.arange(-5.,5.001,.25));model=LinkedObjective(tracks,bank,protocol['center'],len(cat.satellite_numbers),groups)
    x0=np.array(baseline['best']['x']);results={}
    for arm in protocol['arms']:
        shared=arm=='shared';runs=[]
        for start in [x0,np.array([0.,0.,x0[2]]),np.r_[x0[:2],-2.],np.r_[x0[:2],2.]]:
            fit=minimize(lambda x:-model.evaluate(x,shared)['train'],start,method='L-BFGS-B',
                bounds=[(-12.,12.),(-12.,12.),(-5.,5.)],options=dict(maxiter=100,maxfun=900,ftol=1e-10,gtol=1e-5,eps=1e-4))
            score=model.evaluate(fit.x,shared);lat,lon=model.coordinates(fit.x)
            runs.append(dict(x=fit.x.tolist(),latitude=lat,longitude=lon,train=score['train'],held=score['held'],
                success=bool(fit.success),message=str(fit.message),nfev=int(fit.nfev),
                bound_hit=bool(any(abs(v)>=b-1e-3 for v,b in zip(fit.x,[12.,12.,5.])))))
        best=max(runs,key=lambda r:r['train']);x=np.array(best['x'])
        exact=model.evaluate(x,shared,exact_banks=banks(np.array([x[2]])));approx=model.evaluate(x,shared)
        deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(exact['predictions'],approx['predictions'],strict=True))
        results[arm]=dict(best=best,runs=runs,exact_train=exact['train'],exact_held=exact['held'],maximum_interpolation_error_hz=deviation)
        output.write_text(json.dumps(dict(session_id=session,protocol_sha256=digest(HERE/'protocol.json'),complete=len(results)==2,
            groups=groups,tracks=len(tracks),arms=results),indent=2)+'\n')
        print(json.dumps(dict(session=session,arm=arm,**best)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--session');args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.session)
