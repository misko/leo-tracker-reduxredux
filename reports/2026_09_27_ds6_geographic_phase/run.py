"""Bounded matched geographic screen with exhaustive candidate pairs."""
import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states,REFERENCE_RF_HZ,LIGHT_KM_S
from leo.sky.frames import geodetic_to_ecef_km
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('expanded',ROOT/'2026_09_27_ds6_expanded_association/run.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old);baseline=old.baseline;pair=baseline.pair


def freeze():
    path=HERE/'protocol.json'
    if path.exists():raise FileExistsError('Already frozen')
    ip=ROOT/'2026_09_27_ds6_expanded_association/inputs.json';priorpath=ROOT/'2026_09_27_ds6_expanded_association/protocol.json';prior=json.loads(priorpath.read_text())
    protocol=dict(inputs_sha256=hashlib.sha256(ip.read_bytes()).hexdigest(),source_protocol_sha256=hashlib.sha256(priorpath.read_bytes()).hexdigest(),center_from_cfo=prior['observer_from_cfo'],timing_s=prior['timing_s'],baselines=prior['baselines'],
        points=[dict(index=i,east_km=e,north_km=n) for i,(e,n) in enumerate((e,n) for n in [-2.,0.,2.] for e in [-2.,0.,2.])],
        cfo_scale_hz=100.,phase_contamination=.1,
        selection='Training likelihood only; one stationary location and physical baseline shared across the three evaluable scans, independent scan timing; original unavailable member retained',
        scope='Nine-point local geographic screen; boundary winners unresolved; no automatic enlargement or claim of continuous optimum',
        reference='Operator coordinate excluded from fitting and selection; separate post-result scoring only')
    path.write_text(json.dumps(protocol,indent=2)+'\n')


def combine(scans):
    ctrain=sum(logsumexp(s['cfo_train'])-np.log(len(s['cfo_train'])) for s in scans)
    cjoint=sum(logsumexp(s['cfo_joint'])-np.log(len(s['cfo_joint'])) for s in scans)
    ptr=np.array([logsumexp(s['train'],axis=1)-np.log(len(s['cfo_train'])) for s in scans]);pjo=np.array([logsumexp(s['joint'],axis=1)-np.log(len(s['cfo_train'])) for s in scans]);total=ptr.sum(axis=0);z=logsumexp(total)-np.log(len(total))
    return dict(cfo_only=dict(train=float(ctrain),held=float(cjoint-ctrain)),phase=dict(train=float(z),held=float(logsumexp(pjo.sum(axis=0))-np.log(len(total))-z)),baseline_posterior=np.exp(total-logsumexp(total)).tolist())


def run(index):
    start=time.monotonic();pp=HERE/'protocol.json';protocol=json.loads(pp.read_text());point=protocol['points'][index];output=HERE/f'point-{index}.json'
    if output.exists():
        prior=json.loads(output.read_text());assert prior['complete'] and prior['protocol_sha256']==hashlib.sha256(pp.read_bytes()).hexdigest();print('Already complete',index);return
    ip=ROOT/'2026_09_27_ds6_expanded_association/inputs.json';assert hashlib.sha256(ip.read_bytes()).hexdigest()==protocol['inputs_sha256'];inputs=json.loads(ip.read_text());lat0,lon0=protocol['center_from_cfo'];lat=lat0+np.degrees(point['north_km']/6371.0088);lon=lon0+np.degrees(point['east_km']/6371.0088)/np.cos(np.radians(lat0));taus=np.array(protocol['timing_s']);vectors=np.array([b['enu_m'] for b in protocol['baselines']]);receiver=geodetic_to_ecef_km(lat,lon,0);la,lo=np.radians([lat,lon]);east=np.array([-np.sin(lo),np.cos(lo),0]);north=np.array([-np.sin(la)*np.cos(lo),-np.sin(la)*np.sin(lo),np.cos(la)]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]);rotation=np.stack([east,north,up],axis=-1);rows=[];unavailable=[]
    for scan in inputs['scans']:
        sid=scan['session_id']
        if not scan['groups']:unavailable.append(dict(session_id=sid,reason=scan['unavailable_reason']));continue
        path=ROOT/scan['plan_path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==scan['plan_sha256'];plan=json.loads(path.read_text());cat=pair.u.load_catalogue(plan);tracks={t['track_id']:t for t in plan['tracks']};indices=np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')]);prior=-2*np.log(len(indices));groups=[]
        for group in scan['groups']:
            paired=pair.dd.paired_observations(*[tracks[t] for t in group['track_ids']]);mask=paired['mask'];n=len(mask);measured=paired['measured'][1]-paired['measured'][0];pt=np.array([o['time_s'] for o in group['observations']]);states=[]
            for mode in [0,1]:
                preds=[];changes=[];visible=[]
                for first in range(0,len(indices),256):
                    p,v,valid=propagate_candidate_states(cat,indices[first:first+256],plan['start_utc_ns'],np.r_[paired['source_times'][mode],pt],taus);d=p-receiver;d/=np.linalg.norm(d,axis=-1,keepdims=True);preds.append(-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(d[:,:,:n]*v[:,:,:n],axis=-1));changes.append((d[:,:,n+1]-d[:,:,n])@rotation);visible.append(np.any((d[:,:,:n]@up)[...,mask]>=0,axis=-1))
                states.append(dict(pred=np.concatenate(preds),change=np.concatenate(changes),visible=np.concatenate(visible)))
            a,b=states;scale=2*np.pi*tracks[group['track_ids'][0]]['rf_hz']/299792458.;train=np.full((len(vectors),len(taus)),-np.inf);joint=np.full_like(train,-np.inf);ctotal=np.full(len(taus),-np.inf);cjtotal=ctotal.copy();counts=[]
            for ti,tau in enumerate(taus):
                ia=np.flatnonzero(a['visible'][:,ti]);ib=np.flatnonzero(b['visible'][:,ti]);counts.append(len(ia)*len(ib))
                for first in range(0,len(ia),16):
                    aa=ia[first:first+16];res=(measured-(b['pred'][ib,ti][None,:,:]-a['pred'][aa,ti][:,None,:])).reshape(-1,n);ct,cj=pair.u.robust_scores(res,mask,sigma=100.);ct+=prior;cj+=prior;ctotal[ti]=np.logaddexp(ctotal[ti],logsumexp(ct));cjtotal[ti]=np.logaddexp(cjtotal[ti],logsumexp(cj));delta=(b['change'][ib,ti][None,:,:]-a['change'][aa,ti][:,None,:]).reshape(-1,3);ph=baseline.previous.factor(group['correlation'],scale*(delta@vectors.T),.1);train[:,ti]=np.logaddexp(train[:,ti],logsumexp(ct[:,None]+ph,axis=0));joint[:,ti]=np.logaddexp(joint[:,ti],logsumexp(cj[:,None]+ph,axis=0))
            groups.append(dict(group=group['group'],pair_counts=counts,train=train.tolist(),joint=joint.tolist(),cfo_train=ctotal.tolist(),cfo_joint=cjtotal.tolist()))
        rows.append(dict(session_id=sid,groups=groups,train=sum(np.array(g['train']) for g in groups).tolist(),joint=sum(np.array(g['joint']) for g in groups).tolist(),cfo_train=sum(np.array(g['cfo_train']) for g in groups).tolist(),cfo_joint=sum(np.array(g['cfo_joint']) for g in groups).tolist()));print(index,sid,round(time.monotonic()-start,1),flush=True)
    output.write_text(json.dumps(dict(complete=True,protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),point=point,latitude_deg=lat,longitude_deg=lon,scans=rows,unavailable=unavailable,scores=combine(rows),elapsed_s=time.monotonic()-start),indent=2)+'\n')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--freeze',action='store_true');ap.add_argument('--point',type=int);args=ap.parse_args();freeze() if args.freeze else run(args.point)
