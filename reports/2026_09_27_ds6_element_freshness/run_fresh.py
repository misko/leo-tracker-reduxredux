"""Matched full-catalogue CFO fits with freshest causal per-object elements."""
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
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_joint_drift'))
from run_joint import (Objective,site,robust_scores,LIGHT_KM_S,REFERENCE_RF_HZ,
    TleArchiveReader,exclude_labelled_starlink_debris,parse_element_sets,propagate_candidate_states)
from catalogue import catalogues


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze():
    base=REPORTS/'2026_09_27_ds6_full_cfo'
    old=json.loads((base/'protocol.json').read_text())
    files=[base/'protocol.json',base/'run_baseline.py',HERE/'catalogue.py',HERE/'audit.json']+[REPORTS/name for name in old['files']]
    files += [REPORTS/folder/f'{s}{suffix}.json' for s in old['sessions'] for folder,suffix in
        [('2026_09_27_ds6_full_cfo',''),('2026_09_27_ds6_cfo_dataset','-plan')]]
    protocol=dict(source_sha256=digest(Path(__file__)),files={str(p.relative_to(REPORTS)):digest(p) for p in files},
        sessions=old['sessions'],center=old['center'],
        elements='Latest snapshot strictly before start minus505s per provider; newest per-object epoch; retain baseline object roster and row order',
        unchanged='Reuse sealed baseline only when all element record texts are identical; record baseline hash and reuse explicitly',
        model='Student-t4 fixed 100 Hz; training-profiled track offset; catalogue mixture; no drift or fitted noise scale',
        candidate_selection='Full catalogue at donor center and four +/-12 km corners, tau -5..5 every .25s; union top8 per training score and timing',
        optimization='Continuous location and one timing; starts donor center at tau=0,-2,+2; +/-12 km and +/-5 s bounds',
        input_policy='Numerical plans must bind to frozen export protocol and approved capture manifest; hash exact input in output',
        partition='Exported seeded random whole-visit masks; discard only tracks with fewer than two training or one held observation; record counts',
        evaluation='Exact orbit audit at winner; ground reference loaded only by a later summarizer',
        scope='All 43 DS6 scans; local conditional baseline, not blind global localization; donor itself is a DS6 development scan')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def select_top(score,ids,k=8):
    count=min(k,len(ids));chosen=np.argsort(score,axis=0)[-count:]
    mass=np.exp(logsumexp(np.take_along_axis(score,chosen,axis=0),axis=0)-logsumexp(score,axis=0))
    return set(ids[chosen.ravel()].tolist()),float(np.min(mass))


def run(session):
    started=time.monotonic();output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert session in protocol['sessions']
    assert digest(Path(__file__))==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    dataset_path=REPORTS/'2026_09_27_ds6_cfo_dataset/protocol.json'
    dataset=json.loads(dataset_path.read_text())
    source=REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json'
    data=json.loads(source.read_text())
    assert data['protocol_sha256']==digest(dataset_path)
    record=next(c for c in dataset['captures'] if c['session_id']==session)
    assert data['input_manifest_sha256']==record['manifest_sha256']
    provenance=dict(session_id=session,protocol_sha256=digest(HERE/'protocol.json'),input_sha256=digest(source))
    if data['state']!='complete':
        output.write_text(json.dumps(dict(provenance,state='unavailable',reason=data.get('reason'),complete=True),indent=2));return
    tracks=[]
    for t in data['tracks']:
        mask=np.array(t['training_mask'],dtype=bool)
        if mask.sum()<2 or (~mask).sum()<1:continue
        row=dict(t,t=np.array(t['times_s']),y=np.array(t['measured_hz']),mask=mask)
        row['centered_t']=row['t']-row['t'][mask].mean();tracks.append(row)
    if not tracks:
        output.write_text(json.dumps(dict(provenance,state='unavailable',reason='No tracks with training and held support',complete=True),indent=2));return
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    _,cat,element_provenance=catalogues(archive,data['start_utc_ns'],data['snapshot_digest'])
    audited=next(r for r in json.loads((HERE/'audit.json').read_text())['results'] if r['session_id']==session)
    assert element_provenance['providers']==audited['providers']
    assert len(element_provenance['changed_rows'])==audited['changed_catalogue_rows']
    if not element_provenance['changed_rows']:
        previous=REPORTS/'2026_09_27_ds6_full_cfo'/f'{session}.json'
        result=json.loads(previous.read_text())
        result.update(provenance,inference_reused=True,reused_baseline_sha256=digest(previous),element_provenance=element_provenance)
        with output.open('x') as f:json.dump(result,f,indent=2)
        print(json.dumps(dict(session=session,inference_reused=True)),flush=True);return
    nodes=np.arange(np.floor(min(t['t'].min() for t in tracks))-6,np.ceil(max(t['t'].max() for t in tracks))+7)
    pos,vel,ids=propagate_candidate_states(cat,np.arange(len(cat.satellite_numbers)),data['start_utc_ns'],nodes,np.array([0.]))
    pos,vel=pos[:,0],vel[:,0];taus=np.arange(-5.,5.001,.25)
    center=protocol['center'];locator=Objective([],{},center,len(ids),[])
    selected={t['track_id']:set() for t in tracks};minimum_mass=1.
    for east,north in [(0.,0.),(-12.,-12.),(-12.,12.),(12.,-12.),(12.,12.)]:
        rec,up=site(*locator.coordinates(np.array([east,north,0.])))
        unit=pos-rec;unit/=np.linalg.norm(unit,axis=-1)[...,None]
        elevation=unit@up;active=np.flatnonzero(np.any(elevation>=0,axis=1))
        pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit[active]*vel[active],axis=-1)
        for t in tracks:
            q=t['t'][None,:]+taus[:,None]-nodes[0];lo=np.floor(q).astype(int);w=q-lo
            predicted=pred[:,lo]*(1-w)+pred[:,lo+1]*w
            visible=np.any((elevation[active][:,lo]*(1-w)+elevation[active][:,lo+1]*w)[:,:,t['mask']]>=0,axis=-1)
            score=np.where(visible,robust_scores(t['y'][None,None,:]-predicted,t['mask'])[0],-np.inf)
            chosen,mass=select_top(score,ids[active]);selected[t['track_id']].update(chosen)
            minimum_mass=min(minimum_mass,mass)
        print(json.dumps(dict(session=session,anchor=[east,north],elapsed_s=time.monotonic()-started)),flush=True)
    def banks(values):
        return {t['track_id']:propagate_candidate_states(cat,np.array(sorted(selected[t['track_id']])),data['start_utc_ns'],t['t'],values) for t in tracks}
    bank=banks(taus);model=Objective(tracks,bank,center,len(ids),sorted({t['receiver_id'] for t in tracks}));runs=[]
    for tau in [0.,-2.,2.]:
        fit=minimize(lambda x:-model.evaluate(x,False)['train'],np.array([0.,0.,tau]),method='L-BFGS-B',
            bounds=[(-12.,12.),(-12.,12.),(-5.,5.)],options=dict(maxiter=100,maxfun=900,ftol=1e-10,gtol=1e-5,eps=1e-4))
        score=model.evaluate(fit.x,False);lat,lon=model.coordinates(fit.x)
        runs.append(dict(x=fit.x.tolist(),latitude=lat,longitude=lon,train=score['train'],held=score['held'],success=bool(fit.success),
            message=str(fit.message),nfev=int(fit.nfev),bound_hit=bool(any(abs(v)>=b-1e-3 for v,b in zip(fit.x,[12.,12.,5.])))))
    best=max(runs,key=lambda r:r['train']);x=np.array(best['x'])
    exact=model.evaluate(x,False,exact_banks=banks(np.array([x[2]])));approx=model.evaluate(x,False)
    deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(exact['predictions'],approx['predictions'],strict=True))
    result=dict(provenance,state='complete',complete=True,best=best,runs=runs,tracks=len(tracks),
        inference_reused=False,element_provenance=element_provenance,
        excluded_tracks=len(data['tracks'])-len(tracks),rate_hz=data['rate_hz'],minimum_anchor_top8_mass=minimum_mass,
        shortlists={key:sorted(value) for key,value in selected.items()},exact_train=exact['train'],exact_held=exact['held'],
        maximum_interpolation_error_hz=deviation,elapsed_s=time.monotonic()-started)
    with output.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(session=session,best=best,elapsed_s=result['elapsed_s'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--session');args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.session)
