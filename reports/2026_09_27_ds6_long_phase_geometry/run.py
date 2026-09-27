"""Held-visit geometric versus response-only phase prediction."""
import importlib.util
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
prep=load('prep',ROOT/'2026_09_27_ds6_expanded_association/prepare.py')
envelope=load('envelope',ROOT/'2026_09_27_ds6_envelope_refit/run.py');geo=envelope.previous.phase.geo
SID='scan-fw-39ac2b14d1bb5f0f'


def evidence(probabilities,shifts,train,weights=None):
    """Integrate a common circular response and fixed model hypotheses."""
    delta=np.linspace(-np.pi,np.pi,len(probabilities[0]),endpoint=False);n=len(shifts)
    weights=np.ones(n)/n if weights is None else np.array(weights);ll=np.zeros((n,len(delta)));held=ll.copy()
    for i,p in enumerate(probabilities):
        density=.9*np.array(p)*len(delta)+.1
        term=np.log(np.interp(delta[None,:]+shifts[:,i,None],delta,density,period=2*np.pi))
        if train[i]:ll+=term
        else:held+=term
    lp=ll+np.log(weights)[:,None]-np.log(len(delta));z=logsumexp(lp)
    return dict(train=float(z),held=float(logsumexp(lp+held)-z),hypothesis_posterior=np.exp(logsumexp(lp,axis=1)-z).tolist(),joint_training_posterior=np.exp(lp-z))


def run():
    src=ROOT/'2026_09_27_ds6_phase_opportunity';planpath=src/f'{SID}-plan.json';cachepath=src/f'{SID}-frames.json';plan=json.loads(planpath.read_text());cache=json.loads(cachepath.read_text());fitpath=ROOT/'2026_09_27_ds6_envelope_refit/all-cfo_only.json';fit=json.loads(fitpath.read_text());parent=json.loads((ROOT/'2026_09_27_ds6_fresh_joint43/protocol.json').read_text());si=parent['splits']['all'].index(SID);point=np.array([fit['x'][0],fit['x'][1],fit['x'][si+2]]);model,_,banks=envelope.fresh.load_model(SID,parent['center']);lat,lon=model.coordinates(point)
    protocol=dict(plan_sha256=envelope.fresh.digest(planpath),frames_sha256=envelope.fresh.digest(cachepath),fit_sha256=envelope.fresh.digest(fitpath),site_from_training_cfo=[lat,lon],clock_from_training_cfo=float(point[2]),phase_kappa=16.,visit_contamination=.1,phase_grid=720,within_visit_slope_hz=[-.2,.2],models=['constant_response','geometry_42_baselines','linear_drift_0.02Hz','linear_drift_0.2Hz'],linear_grid_nodes=1601,selection='Two original training visits only; held visits use disjoint evaluation phasors; all nuisance parameters marginalized; no reference loaded',scope='Exploratory mechanism check at fixed CFO site and confident training-MAP identities; no geographic fit or calibrated baseline')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)
    f=np.linspace(-375,375,751);delta=np.linspace(-np.pi,np.pi,720,endpoint=False);slopes=np.linspace(-.2,.2,41);weights=np.ones(41);weights[[0,-1]]=.5;weights/=weights.sum();observations=[]
    for visit in plan['selected']:
        windows=[w for w in cache if w['visit']==visit['visit']];assert windows;ref=float(np.mean([w['start_ms']/1000+.0035 for w in windows]));ll=np.zeros((len(slopes),len(delta)));partition='fit' if visit['partition']=='train' else 'evaluation'
        for w in windows:
            post=prep.phase.posterior(prep.phase.base.extract(w['frame'],partition),16.,f,delta);density=np.array(post['probability'])*len(delta);shift=2*np.pi*slopes*(w['start_ms']/1000+.0035-ref);ll+=np.log(np.maximum(np.interp(delta[None,:]+shift[:,None],delta,density,period=2*np.pi),1e-300))
        lp=logsumexp(ll+np.log(weights)[:,None],axis=0);prob=np.exp(lp-logsumexp(lp));time_s=(visit['valid_start_counter']-plan['timing']['session_start_device_sample_counter'])/plan['rate_hz']+ref;z=np.sum(prob*np.exp(1j*delta));observations.append(dict(visit=visit['visit'],partition=visit['partition'],time_s=time_s,probability=prob.tolist(),mean_phase_deg=float(np.degrees(np.angle(z))),R=float(abs(z))))
    ids=[mode['rx0_track_id'] for mode in plan['selected'][0]['modes']];exact=banks(np.array([point[2]]));prediction=model.evaluate(point,False,exact_banks=exact)['predictions'];selected=[]
    rec=geo.geodetic_to_ecef_km(lat,lon,0);la,lo=np.radians([lat,lon]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]);rot=np.stack([[-np.sin(lo),np.cos(lo),0],[-np.sin(la)*np.cos(lo),-np.sin(la)*np.sin(lo),np.cos(la)],up],axis=-1)
    for tid in ids:
        ti=next(i for i,t in enumerate(model.tracks) if t['track_id']==tid);t=model.tracks[ti];a,_,_=envelope.solver.scores(t['y'][None,:]-prediction[ti],t['mask']);d=exact[tid][0][:,0]-rec;d/=np.linalg.norm(d,axis=-1,keepdims=True);a=np.where(np.any((d@up)[:,t['mask']]>=0,axis=-1),a,-np.inf);index=int(np.argmax(a));selected.append(dict(track_id=tid,candidate_index=int(exact[tid][2][index]),training_mass=float(np.exp(a[index]-logsumexp(a)))))
    source=json.loads((ROOT/'2026_09_27_ds6_cfo_dataset'/f'{SID}-plan.json').read_text());archive=envelope.fresh.TleArchiveReader(Path('/var/lib/leo/tle'));_,cat,provenance=envelope.fresh.catalogues(archive,source['start_utc_ns'],source['snapshot_digest']);times=np.array([o['time_s'] for o in observations]);p,v,valid=geo.propagate_candidate_states(cat,np.array([s['candidate_index'] for s in selected]),source['start_utc_ns'],times,np.array([point[2]]));assert valid.tolist()==[s['candidate_index'] for s in selected];d=p[:,0]-rec;d/=np.linalg.norm(d,axis=-1,keepdims=True)
    baselines=json.loads((ROOT/'2026_09_27_ds6_joint_phase/protocol.json').read_text())['grid']['baselines'];vectors=np.array([b['enu_m'] for b in baselines]);rf=next(t for t in plan['tracks'] if t['track_id']==ids[0])['rf_hz'];geom=2*np.pi*rf/299792458.*((d[1]-d[0])@rot@vectors.T).T;geom-=geom[:,0,None]
    train=np.array([o['partition']=='train' for o in observations]);prob=[o['probability'] for o in observations];models={};predictions={}
    hypotheses={'constant_response':np.zeros((1,len(times))),'geometry_42_baselines':geom}
    for limit in [.02,.2]:hypotheses[f'linear_drift_{limit:g}Hz']=2*np.pi*np.linspace(-limit,limit,1601)[:,None]*(times-times[0])[None,:]
    for name,shifts in hypotheses.items():
        w=np.ones(len(shifts));
        if name.startswith('linear'):w[[0,-1]]=.5
        w/=w.sum();r=evidence(prob,shifts,train,w);jointpost=r.pop('joint_training_posterior');models[name]=r
        z=np.sum(jointpost[:,:,None]*np.exp(1j*(delta[None,:,None]+shifts[:,None,:])),axis=(0,1));predictions[name]=dict(mean_deg=np.degrees(np.angle(z)).tolist(),R=abs(z).tolist())
    (HERE/'results.json').write_text(json.dumps(dict(complete=True,protocol_sha256=envelope.fresh.digest(HERE/'protocol.json'),observations=observations,selected_candidates=selected,element_provenance=provenance,baselines=baselines,geometry_shifts_rad=geom.tolist(),models=models,predictions=predictions),indent=2)+'\n');print(json.dumps(models,indent=2)[:1800])


if __name__=='__main__':run()
