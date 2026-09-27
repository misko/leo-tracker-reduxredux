"""Training-only receiver clock curvature audit on every frozen DS6 scan."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.special import gammaln

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_full_cfo'))
from run_baseline import (site,robust_scores,REFERENCE_RF_HZ,LIGHT_KM_S,TleArchiveReader,
    exclude_labelled_starlink_debris,parse_element_sets,propagate_candidate_states)
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_exact_timing'))
from robust import fit_offset


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def basis(times,mask,rf_hz,order):
    u=(np.asarray(times)-150.)/150.
    x=np.stack([u**degree for degree in range(1,order+1)],axis=-1)*REFERENCE_RF_HZ/rf_hz
    return x-x[mask].mean(axis=0)


def density(residual):
    return gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(100.)-2.5*np.log1p((residual/100.)**2/4)


def fit_clock(rows,order,iterations=80):
    """IRLS with weighted track offsets eliminated from each receiver solve."""
    if order==0:
        return {},[float(fit_offset(r['residual'][r['mask']])) for r in rows],True
    receivers=sorted({r['receiver_id'] for r in rows})
    coefficients={rx:np.zeros(order) for rx in receivers}
    centers=[float(np.median(r['residual'][r['mask']])) for r in rows]
    offsets=np.zeros(len(rows));design=[basis(r['time'],r['mask'],r['rf_hz'],order) for r in rows]
    converged=False
    for _ in range(iterations):
        before=np.concatenate([coefficients[rx] for rx in receivers])
        before_offsets=offsets.copy()
        for rx in receivers:
            h=np.eye(order)/750.**2;rhs=np.zeros(order);blocks=[]
            for i,(r,x) in enumerate(zip(rows,design,strict=True)):
                if r['receiver_id']!=rx:continue
                mask=r['mask'];a=x[mask];y=r['residual'][mask]-centers[i]
                z=(y-offsets[i]-a@coefficients[rx])/100.
                w=5/(4+z*z)/10000.
                sw=float(w.sum());sx=np.sum(w[:,None]*a,axis=0);sy=float(w@y)
                h+=a.T@(w[:,None]*a)-np.outer(sx,sx)/sw
                rhs+=a.T@(w*y)-sx*sy/sw
                blocks.append((i,sw,sx,sy))
            coefficients[rx]=np.linalg.solve(h,rhs)
            for i,sw,sx,sy in blocks:offsets[i]=(sy-sx@coefficients[rx])/sw
        delta=np.max(np.abs(np.concatenate([coefficients[rx] for rx in receivers])-before))
        delta=max(delta,float(np.max(np.abs(offsets-before_offsets))))
        if delta<1e-6:
            converged=True;break
    return coefficients,(offsets+np.array(centers)).tolist(),converged


def score(rows,order,coefficients,offsets):
    train=held=0.
    for r,offset in zip(rows,offsets,strict=True):
        residual=r['residual']-offset
        if order:residual=residual-basis(r['time'],r['mask'],r['rf_hz'],order)@coefficients[r['receiver_id']]
        d=density(residual);train+=float(d[r['mask']].sum());held+=float(d[~r['mask']].sum())
    penalty=sum(float(np.sum(v*v)) for v in coefficients.values())/(2*750.**2)
    return dict(train=train,penalized_train=train-penalty,held=held)


def freeze():
    base=REPORTS/'2026_09_27_ds6_full_cfo'
    old=json.loads((base/'protocol.json').read_text())
    paths=[base/'protocol.json',base/'run_baseline.py']+[REPORTS/name for name in old['files']]
    paths += [REPORTS/folder/f'{s}{suffix}.json' for s in old['sessions'] for folder,suffix in
        [('2026_09_27_ds6_full_cfo',''),('2026_09_27_ds6_cfo_dataset','-plan')]]
    protocol=dict(source_sha256=digest(Path(__file__)),sessions=old['sessions'],
        files={str(p.relative_to(REPORTS)):digest(p) for p in paths},
        orders=[0,1,2],clock_coefficient_prior_std_hz=750.,
        model='Student-t4 scale100Hz; track offsets; shared receiver polynomial in (t-150)/150; normalized by 11.2GHz/actual RF',
        assignment='Training MAP candidate at frozen individual-scan baseline position and timing; labels fixed for all orders',
        fit='Training-only IRLS with track-offset Schur elimination; held observations never fit or set basis centering',
        scope='All43 conditional diagnostic, not a location refit, hardware calibration, or known source identification')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(limit):
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(Path(__file__))==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    done=0
    for session in protocol['sessions']:
        output=HERE/f'{session}.json'
        if output.exists():
            assert json.loads(output.read_text())['protocol_sha256']==digest(HERE/'protocol.json');continue
        if done>=limit:break
        baseline=json.loads((REPORTS/'2026_09_27_ds6_full_cfo'/f'{session}.json').read_text())
        data=json.loads((REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json').read_text())
        best=baseline['best'];tau=best['x'][2];rec,up=site(best['latitude'],best['longitude'])
        archive=TleArchiveReader(Path('/var/lib/leo/tle'))
        snap=archive.select_latest_before(data['start_utc_ns']-505_000_000_000);assert snap.digest==data['snapshot_digest']
        payload,_=exclude_labelled_starlink_debris(archive.read(snap));cat=parse_element_sets(payload)
        rows=[]
        for t in data['tracks']:
            if t['track_id'] not in baseline['shortlists']:continue
            times=np.array(t['times_s']);mask=np.array(t['training_mask'],dtype=bool)
            pos,vel,ids=propagate_candidate_states(cat,np.array(baseline['shortlists'][t['track_id']]),data['start_utc_ns'],times,np.array([tau]))
            unit=pos[:,0]-rec;unit/=np.linalg.norm(unit,axis=-1)[...,None]
            pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel[:,0],axis=-1)
            residual=np.array(t['measured_hz'])[None,:]-pred
            scores=np.where(np.any((unit@up)[:,mask]>=0,axis=-1),robust_scores(residual,mask)[0],-np.inf)
            idx=int(np.argmax(scores))
            rows.append(dict(track_id=t['track_id'],receiver_id=t['receiver_id'],rf_hz=t['rf_hz'],time=times,mask=mask,
                residual=residual[idx],candidate_index=int(ids[idx])))
        arms={}
        for order in protocol['orders']:
            coefficients,offsets,converged=fit_clock(rows,order)
            arms[str(order)]=dict(**score(rows,order,coefficients,offsets),coefficients={str(k):v.tolist() for k,v in coefficients.items()},converged=converged)
        extra,offsets,converged=fit_clock(rows,2,iterations=160)
        audit=score(rows,2,extra,offsets)
        result=dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'protocol.json'),
            assignments=[dict(track_id=r['track_id'],candidate_index=r['candidate_index']) for r in rows],arms=arms,
            iteration_audit=dict(train_change=audit['train']-arms['2']['train'],held_change=audit['held']-arms['2']['held'],converged=converged),
            quadratic_vs_linear_held_gain=arms['2']['held']-arms['1']['held'])
        with output.open('x') as f:json.dump(result,f,indent=2)
        done+=1;print(json.dumps(dict(session=session,held_gain=result['quadratic_vs_linear_held_gain'],audit=result['iteration_audit'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--limit',type=int,default=12);args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.limit)
