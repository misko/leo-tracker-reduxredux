"""Full pair association on the fixed expanded cohort, including transfer prior."""
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
spec=importlib.util.spec_from_file_location('baseline',ROOT/'2026_09_27_ds6_baseline_sensitivity/run.py');baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline);pair=baseline.pair


def predict(train,joint,prior):
    p=np.array(prior);take=p>0;lp=np.log(p[take])[:,None]-np.log(train.shape[1]);z=logsumexp(train[take]+lp)
    return dict(held_cfo_log_predictive=float(logsumexp(joint[take]+lp)-z),baseline_posterior=np.exp(logsumexp(train[take]+lp,axis=1)-z).tolist())


def main():
    start=time.monotonic();ip=HERE/'inputs.json';inputs=json.loads(ip.read_text());donorpath=ROOT/'2026_09_27_ds6_baseline_sensitivity/results.json';donor=json.loads(donorpath.read_text());oldp=json.loads((ROOT/'2026_09_27_ds6_baseline_sensitivity/protocol.json').read_text());assert donor['complete'];lat,lon=oldp['observer_from_cfo'];taus=np.array(oldp['timing_s']);hyp=oldp['baselines'];vectors=np.array([b['enu_m'] for b in hyp]);uniform=np.ones(len(hyp))/len(hyp);nominal=np.array([b['length_m']==.08 and b['elevation_deg']==0 and b['azimuth_deg'] in [90,270] for b in hyp],float);nominal/=nominal.sum();priors=dict(nominal=nominal.tolist(),uniform_baseline=uniform.tolist(),transferred_baseline=donor['scores']['baseline_mixture']['baseline_posterior'])
    protocol=dict(inputs_sha256=hashlib.sha256(ip.read_bytes()).hexdigest(),donor_sha256=hashlib.sha256(donorpath.read_bytes()).hexdigest(),observer_from_cfo=[lat,lon],timing_s=taus.tolist(),baselines=hyp,priors=priors,
        cfo_scale_hz=100.,cfo_scale_scope='Fixed differential Student-t4 scale, matched within this cohort; not the learned per-pair scales of the donor experiment',
        contamination=.1,scope='Three evaluable expansion scans plus one retained unavailable; fixed observer, all training-visible pairs; original whole-visit partitions; no held phase or reference coordinate enters')
    pp=HERE/'protocol.json';pp.write_text(json.dumps(protocol,indent=2)+'\n');receiver=geodetic_to_ecef_km(lat,lon,0);la,lo=np.radians([lat,lon]);east=np.array([-np.sin(lo),np.cos(lo),0]);north=np.array([-np.sin(la)*np.cos(lo),-np.sin(la)*np.sin(lo),np.cos(la)]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]);rotation=np.stack([east,north,up],axis=-1);rows=[]
    for scan in inputs['scans']:
        sid=scan['session_id'];path=ROOT/scan['plan_path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==scan['plan_sha256'];plan=json.loads(path.read_text())
        if not scan['groups']:rows.append(dict(session_id=sid,evaluable=False,reason=scan['unavailable_reason']));continue
        cat=pair.u.load_catalogue(plan);tracks={t['track_id']:t for t in plan['tracks']};indices=np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')]);prior=-2*np.log(len(indices));groups=[]
        for group in scan['groups']:
            paired=pair.dd.paired_observations(*[tracks[t] for t in group['track_ids']]);mask=paired['mask'];n=len(mask);assert mask.sum()>=2 and (~mask).sum()>=2;measured=paired['measured'][1]-paired['measured'][0];pt=np.array([o['time_s'] for o in group['observations']]);states=[]
            for mode in [0,1]:
                preds=[];changes=[];visible=[]
                for first in range(0,len(indices),256):
                    p,v,valid=propagate_candidate_states(cat,indices[first:first+256],plan['start_utc_ns'],np.r_[paired['source_times'][mode],pt],taus);d=p-receiver;d/=np.linalg.norm(d,axis=-1,keepdims=True);preds.append(-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(d[:,:,:n]*v[:,:,:n],axis=-1));changes.append((d[:,:,n+1]-d[:,:,n])@rotation);visible.append(np.any((d[:,:,:n]@up)[...,mask]>=0,axis=-1))
                states.append(dict(pred=np.concatenate(preds),change=np.concatenate(changes),visible=np.concatenate(visible)))
            a,b=states;scale=2*np.pi*tracks[group['track_ids'][0]]['rf_hz']/299792458.;train=np.full((len(hyp),len(taus)),-np.inf);joint=np.full_like(train,-np.inf);ctotal=np.full(len(taus),-np.inf);cjtotal=ctotal.copy();counts=[]
            for ti,tau in enumerate(taus):
                ia=np.flatnonzero(a['visible'][:,ti]);ib=np.flatnonzero(b['visible'][:,ti]);counts.append(len(ia)*len(ib))
                for first in range(0,len(ia),16):
                    aa=ia[first:first+16];res=(measured-(b['pred'][ib,ti][None,:,:]-a['pred'][aa,ti][:,None,:])).reshape(-1,n);ct,cj=pair.u.robust_scores(res,mask,sigma=100.);ct+=prior;cj+=prior;ctotal[ti]=np.logaddexp(ctotal[ti],logsumexp(ct));cjtotal[ti]=np.logaddexp(cjtotal[ti],logsumexp(cj))
                    delta=(b['change'][ib,ti][None,:,:]-a['change'][aa,ti][:,None,:]).reshape(-1,3);ph=baseline.previous.factor(group['correlation'],scale*(delta@vectors.T),.1)
                    train[:,ti]=np.logaddexp(train[:,ti],logsumexp(ct[:,None]+ph,axis=0));joint[:,ti]=np.logaddexp(joint[:,ti],logsumexp(cj[:,None]+ph,axis=0))
            groups.append(dict(group=group['group'],paired_visits=n,training_visits=int(mask.sum()),held_visits=int((~mask).sum()),pair_counts=counts,train=train.tolist(),joint=joint.tolist(),cfo_train=ctotal.tolist(),cfo_joint=cjtotal.tolist()));print(sid,len(groups),'elapsed',round(time.monotonic()-start,1),flush=True)
        train=sum(np.array(g['train']) for g in groups);joint=sum(np.array(g['joint']) for g in groups);ct=sum(np.array(g['cfo_train']) for g in groups);cj=sum(np.array(g['cfo_joint']) for g in groups);scores={name:predict(train,joint,p) for name,p in priors.items()};scores['cfo_only']=dict(held_cfo_log_predictive=float(logsumexp(cj)-logsumexp(ct)))
        rows.append(dict(session_id=sid,evaluable=True,groups=groups,scores=scores));(HERE/'results.json').write_text(json.dumps(dict(complete=len(rows)==len(inputs['scans']),protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),elapsed_s=time.monotonic()-start,scans=rows),indent=2)+'\n')
    print(json.dumps([{k:v for k,v in r.items() if k!='groups'} for r in rows],indent=2))


if __name__=='__main__':main()
