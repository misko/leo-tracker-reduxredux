"""Shared-baseline sensitivity, full pairs, no coordinate-reference fitting."""
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
spec=importlib.util.spec_from_file_location('association',ROOT/'2026_09_27_ds6_likelihood_association/run.py');previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous);pair=previous.pair


def baselines():
    rows=[]
    for length in [.04,.08,.12]:
        for az in range(0,360,30):
            r=np.radians(az);rows.append(dict(length_m=length,azimuth_deg=az,elevation_deg=0,enu_m=[length*np.sin(r),length*np.cos(r),0.]))
        for elevation in [-90,90]:rows.append(dict(length_m=length,azimuth_deg=0,elevation_deg=elevation,enu_m=[0.,0.,length*np.sign(elevation)]))
    return rows


def shared_score(scans,indices):
    train=np.array([s['train'] for s in scans])[:,indices];joint=np.array([s['joint'] for s in scans])[:,indices]
    lt=logsumexp(train,axis=-1)-np.log(train.shape[-1]);lj=logsumexp(joint,axis=-1)-np.log(joint.shape[-1]);total=lt.sum(axis=0);z=logsumexp(total)
    return dict(baseline_posterior=np.exp(total-z).tolist(),held_by_scan=[float(logsumexp(total-lt[i]+lj[i])-z) for i in range(len(scans))],
                joint_held=float(logsumexp(lj.sum(axis=0))-z))


def main():
    start=time.monotonic();ip=ROOT/'2026_09_27_ds6_likelihood_association/inputs.json';inputs=json.loads(ip.read_text());sourcepath=ROOT/'2026_09_27_ds6_differential_cfo/results.json';source=json.loads(sourcepath.read_text());base=json.loads((ROOT/'2026_09_27_ds6_likelihood_association/protocol.json').read_text());lat,lon=base['observer_from_cfo'];taus=np.array(base['timing_s']);hyp=baselines();vectors=np.array([b['enu_m'] for b in hyp])
    protocol=dict(inputs_sha256=hashlib.sha256(ip.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(sourcepath.read_bytes()).hexdigest(),observer_from_cfo=[lat,lon],timing_s=taus.tolist(),baselines=hyp,
        prior='Uniform over 42 discrete sensitivity hypotheses; shared physical baseline across scans; independent scan timing',
        contamination=.1,scope='Sensitivity screen, not calibrated baseline inference or position search; horizontal directions and vertical endpoints, not continuous 3D coverage')
    pp=HERE/'protocol.json';pp.write_text(json.dumps(protocol,indent=2)+'\n');receiver=geodetic_to_ecef_km(lat,lon,0);la,lo=np.radians([lat,lon]);east=np.array([-np.sin(lo),np.cos(lo),0]);north=np.array([-np.sin(la)*np.cos(lo),-np.sin(la)*np.sin(lo),np.cos(la)]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]);rotation=np.stack([east,north,up],axis=-1);rows=[]
    for scan,prep in zip(source['scans'],inputs['scans']):
        sid=scan['session_id'];assert sid==prep['session_id'];path=ROOT/'2026_09_27_ds6_common_rate_validation'/(sid+'-plan.json');plan=json.loads(path.read_text());cat=pair.u.load_catalogue(plan);tracks={t['track_id']:t for t in plan['tracks']};indices=np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')]);prior=-2*np.log(len(indices));groups=[]
        for group,pg in zip(scan['groups'],prep['groups']):
            assert group['group']==pg['group'];paired=pair.dd.paired_observations(*[tracks[t] for t in group['track_ids']]);mask=paired['mask'];n=len(mask);measured=paired['measured'][1]-paired['measured'][0];pt=np.array([o['time_s'] for o in pg['observations']]);states=[]
            for mode in [0,1]:
                preds=[];change=[];visible=[]
                for first in range(0,len(indices),256):
                    p,v,valid=propagate_candidate_states(cat,indices[first:first+256],plan['start_utc_ns'],np.r_[paired['source_times'][mode],pt],taus);d=p-receiver;d/=np.linalg.norm(d,axis=-1,keepdims=True)
                    preds.append(-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(d[:,:,:n]*v[:,:,:n],axis=-1));change.append((d[:,:,n+1]-d[:,:,n])@rotation);visible.append(np.any((d[:,:,:n]@up)[...,mask]>=0,axis=-1))
                states.append(dict(pred=np.concatenate(preds),change=np.concatenate(change),visible=np.concatenate(visible)))
            a,b=states;scale=2*np.pi*tracks[group['track_ids'][0]]['rf_hz']/299792458.;train=np.full((len(hyp),len(taus)),-np.inf);joint=np.full_like(train,-np.inf);counts=[]
            for ti,tau in enumerate(taus):
                ia=np.flatnonzero(a['visible'][:,ti]);ib=np.flatnonzero(b['visible'][:,ti]);counts.append(len(ia)*len(ib))
                for first in range(0,len(ia),16):
                    aa=ia[first:first+16];res=(measured-(b['pred'][ib,ti][None,:,:]-a['pred'][aa,ti][:,None,:])).reshape(-1,n);ct,cj=pair.u.robust_scores(res,mask,sigma=group['differential_scale_hz']);ct+=prior;cj+=prior
                    delta=(b['change'][ib,ti][None,:,:]-a['change'][aa,ti][:,None,:]).reshape(-1,3);shift=scale*(delta@vectors.T);ph=previous.factor(pg['offset_correlation'],shift,.1)
                    train[:,ti]=np.logaddexp(train[:,ti],logsumexp(ct[:,None]+ph,axis=0));joint[:,ti]=np.logaddexp(joint[:,ti],logsumexp(cj[:,None]+ph,axis=0))
            groups.append(dict(group=group['group'],pair_counts=counts,train=train.tolist(),joint=joint.tolist()));print(sid,len(groups),'elapsed',round(time.monotonic()-start,1),flush=True)
        rows.append(dict(session_id=sid,groups=groups,train=sum(np.array(g['train']) for g in groups).tolist(),joint=sum(np.array(g['joint']) for g in groups).tolist()))
        nominal=[i for i,b in enumerate(hyp) if b['length_m']==.08 and b['elevation_deg']==0 and b['azimuth_deg'] in [90,270]]
        scores={name:shared_score(rows,ids) for name,ids in [('nominal_east_west',nominal),('baseline_mixture',list(range(len(hyp))))]}
        (HERE/'results.json').write_text(json.dumps(dict(complete=len(rows)==2,protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),elapsed_s=time.monotonic()-start,scans=rows,scores=scores),indent=2)+'\n')
    print(json.dumps(scores,indent=2))


if __name__=='__main__':main()
