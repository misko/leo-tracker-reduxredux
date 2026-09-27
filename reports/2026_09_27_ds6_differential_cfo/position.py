"""Bounded two-scan differential-CFO/phase position search without pose truth."""
import importlib.util
import json
import hashlib
from pathlib import Path
import time

import numpy as np
from scipy.special import logsumexp
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states,REFERENCE_RF_HZ,LIGHT_KM_S
from leo.sky.frames import geodetic_to_ecef_km

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('differential',HERE/'run.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
u=module.uncertainty


def components(banks,kappa,weights):
    """Marginalize per-pair candidates, response and precision; retain sign/time."""
    pt=[];pa=[];pc=[]
    for b in banks:
        fit=np.stack([u.phase_score(b['y'][b['mask']],s*b['geometry'][...,b['mask']],kappa) for s in [-1,1]])
        all_=np.stack([u.phase_score(b['y'],s*b['geometry'],kappa) for s in [-1,1]])
        prior=np.log(weights)[None,:,None,None]
        pt.append(logsumexp(logsumexp(b['cfo_train'][None,None,...]+fit+prior,axis=-1),axis=1))
        pa.append(logsumexp(logsumexp(b['cfo_train'][None,None,...]+all_+prior,axis=-1),axis=1))
        pc.append(logsumexp(logsumexp(b['cfo_joint'][None,None,...]+fit+prior,axis=-1),axis=1))
    return dict(train=sum(pt),phase_all=sum(pa),cfo_all=sum(pc),
                cfo_train=sum(logsumexp(b['cfo_train'],axis=-1) for b in banks),
                cfo_joint=sum(logsumexp(b['cfo_joint'],axis=-1) for b in banks))


def combine(scans):
    # One baseline sign shared by the recording setup; each scan has its own
    # time offset. Candidate/response factors stay independent per disjoint pair.
    phase_train=sum(logsumexp(s['train'],axis=-1)-np.log(s['train'].shape[-1]) for s in scans)
    phase_all=sum(logsumexp(s['phase_all'],axis=-1)-np.log(s['train'].shape[-1]) for s in scans)
    cfo_all=sum(logsumexp(s['cfo_all'],axis=-1)-np.log(s['train'].shape[-1]) for s in scans)
    z=logsumexp(phase_train)-np.log(2)
    cfo=sum(logsumexp(s['cfo_train'])-np.log(len(s['cfo_train'])) for s in scans)
    held=sum(logsumexp(s['cfo_joint'])-logsumexp(s['cfo_train']) for s in scans)
    return dict(cfo_train=float(cfo),phase_train=float(z),cfo_only_held=float(held),
        phase_held_cfo=float(logsumexp(cfo_all)-np.log(2)-z),
        held_phase=float(logsumexp(phase_all)-np.log(2)-z),
        baseline_sign_posterior=np.exp(phase_train-logsumexp(phase_train)).tolist())


def main():
    started=time.monotonic();source_path=HERE/'results.json';source=json.loads(source_path.read_text());protocol=json.loads((HERE/'protocol-v2.json').read_text())
    lat0,lon0=protocol['observer_from_other_scan_cfo'];times=np.array(protocol['timing_s'])
    previous=json.loads((ROOT/'2026_09_27_ds6_uncertainty_audit/protocol.json').read_text());kappa=np.array(previous['kappa_grid']);weights=np.ones(len(kappa));weights[[0,-1]]=.5;weights/=weights.sum()
    frozen=dict(source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),center_from_other_scan_cfo=[lat0,lon0],
        stages='7x7 +/-12 km at 4 km spacing; for each interior arm winner, 9x9 +/-4 km at 1 km spacing, then 9x9 +/-1 km at 0.25 km spacing; share cached points',
        selection='Maximize training score independently for differential CFO only and differential CFO plus phase. Holdouts and pose coordinates never select points.',
        timing='Independent scan time offsets; one shared baseline sign across both scans',
        response='Independent integrated pair phase offsets and kappa; nominal east-west baseline magnitude 80 mm',
        candidate_scope='Frozen unions from preceding conditional differential-CFO experiment; no global catalogue/geographic claim',
        local_limit_km=12.,sigma='Frozen training-derived differential scales from reference observer')
    pp=HERE/'position-protocol.json'
    if pp.exists():assert json.loads(pp.read_text())==frozen
    else:pp.write_text(json.dumps(frozen,indent=2)+'\n')
    states=[]
    for scan in source['scans']:
        sid=scan['session_id'];plan=json.loads((ROOT/'2026_09_27_ds6_common_rate_validation'/(sid+'-plan.json')).read_text());tracks={t['track_id']:t for t in plan['tracks']}
        cat=u.load_catalogue(plan);lookup={str(n):i for i,n in enumerate(cat.satellite_numbers)};groups=[]
        for g in scan['groups']:
            paired=module.paired_observations(*[tracks[i] for i in g['track_ids']]);phase_times=np.array([o['time_s'] for o in g['phase_observations']]);bodies=[]
            for mode in [0,1]:
                chosen=[lookup[str(s)] for s in g['candidates'][mode]]
                p,v,valid=propagate_candidate_states(cat,chosen,plan['start_utc_ns'],np.r_[paired['source_times'][mode],phase_times],times)
                assert np.array_equal(chosen,valid);bodies.append((p,v))
            groups.append(dict(source=g,paired=paired,bodies=bodies,rf=tracks[g['track_ids'][0]]['rf_hz']))
        states.append(groups)
    cache={};best={};receipts=[]
    def evaluate(east_km,north_km):
        key=(round(east_km,6),round(north_km,6))
        if key in cache:return cache[key]
        lat=lat0+np.degrees(north_km/6371.0088);lon=lon0+np.degrees(east_km/(6371.0088*np.cos(np.radians(lat0))))
        la,lo=np.radians([lat,lon]);receiver=geodetic_to_ecef_km(lat,lon,0)
        east=np.array([-np.sin(lo),np.cos(lo),0.]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)])
        scan_components=[]
        for groups in states:
            banks=[]
            for g in groups:
                paired=g['paired'];mask=paired['mask'];n=len(paired['times']);pred=[];projection=[];vis=[]
                for p,v in g['bodies']:
                    direction=p-receiver;direction/=np.linalg.norm(direction,axis=-1)[...,None]
                    pred.append(-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(direction[:,:,:n]*v[:,:,:n],axis=-1))
                    projection.append(direction[:,:,n:]@east);vis.append(np.any((direction[:,:,:n]@up)[...,mask]>=0,axis=-1))
                residual=module.difference_residual(paired['measured'],*pred)
                a,b=u.robust_scores(residual,mask,sigma=g['source']['differential_scale_hz'])
                visible=(vis[0][:,None,:]&vis[1][None,:,:]).transpose(2,0,1).reshape(len(times),-1)
                count=a.shape[-1];a=np.where(visible,a,-np.inf)-np.log(count);b=np.where(visible,b,-np.inf)-np.log(count)
                geometry=(2*np.pi*.08*g['rf']/299792458.*(projection[1][None,...]-projection[0][:,None,...])).transpose(2,0,1,3).reshape(len(times),count,-1)
                obs=g['source']['phase_observations']
                banks.append(dict(y=np.array([o['phase'] for o in obs]),mask=np.array([o['train'] for o in obs]),geometry=geometry,cfo_train=a,cfo_joint=b))
            scan_components.append(components(banks,kappa,weights))
        result=dict(east_km=key[0],north_km=key[1],latitude=lat,longitude=lon,**combine(scan_components));cache[key]=result
        if len(cache)%10==0:print('points',len(cache),'elapsed',round(time.monotonic()-started,1),flush=True)
        return result
    def grid(center,halfwidth,spacing):
        offsets=np.arange(-halfwidth,halfwidth+spacing/2,spacing)
        return [evaluate(center[0]+e,center[1]+n) for e in offsets for n in offsets]
    coarse=grid((0.,0.),12.,4.)
    for arm in ['cfo','phase']:
        field=arm+'_train';chosen=max(coarse,key=lambda r:r[field]);stage=0
        boundary=abs(chosen['east_km'])>=12 or abs(chosen['north_km'])>=12
        for halfwidth,spacing in [(4.,1.),(1.,.25)]:
            if boundary:break
            center=(chosen['east_km'],chosen['north_km']);points=grid(center,halfwidth,spacing);chosen=max(points,key=lambda r:r[field]);stage+=1
            boundary=abs(chosen['east_km']-center[0])>=halfwidth or abs(chosen['north_km']-center[1])>=halfwidth
        best[arm]=dict(chosen,boundary=bool(boundary),refinements=stage)
        receipts.append(dict(arm=arm,points_so_far=len(cache),best=best[arm]))
        (HERE/'position-results.json').write_text(json.dumps(dict(protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),best=best,points=list(cache.values()),receipts=receipts,complete=False),indent=2)+'\n')
    (HERE/'position-results.json').write_text(json.dumps(dict(protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),best=best,points=list(cache.values()),receipts=receipts,complete=True,elapsed_s=time.monotonic()-started),indent=2)+'\n')
    print(json.dumps(best,indent=2))


if __name__=='__main__':main()
