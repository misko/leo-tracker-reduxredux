"""Full candidate-pair association using marginalized training phase."""
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
spec=importlib.util.spec_from_file_location('pair_run',ROOT/'2026_09_27_ds6_pair_proposals/run.py');pair=importlib.util.module_from_spec(spec);spec.loader.exec_module(pair)


def factor(corr,shift,epsilon):
    # Independent per-dwell uniform contamination: two-dwell correlation.
    values=np.interp(shift,np.arange(len(corr))*2*np.pi/len(corr),corr,period=2*np.pi)
    return np.log(np.maximum((1-epsilon)**2*values+1-(1-epsilon)**2,1e-300))


def main():
    start=time.monotonic();ip=HERE/'inputs.json';inputs=json.loads(ip.read_text());sourcepath=ROOT/'2026_09_27_ds6_differential_cfo/results.json';source=json.loads(sourcepath.read_text());assert hashlib.sha256(sourcepath.read_bytes()).hexdigest()==inputs['cfo_source_sha256']
    base=json.loads((ROOT/'2026_09_27_ds6_pair_proposals/protocol.json').read_text());lat,lon=base['observer_from_other_scan_cfo'];taus=np.array(base['timing_s']);arms={'cfo_only':None,'phase_raw':0.,'phase_contamination_10pct':.1}
    protocol=dict(inputs_sha256=hashlib.sha256(ip.read_bytes()).hexdigest(),observer_from_cfo=[lat,lon],timing_s=taus.tolist(),arms=arms,
        scope='Fixed-observer full training-visible pair association, held CFO prediction; unknown constant response offset per pair integrated; no held phase used',
        phase_model='Training fit phasors, kappa16; within-dwell slope integrated; unknown pair response integrated by periodic correlation',
        selection='All causal training-visible pairs; original whole-visit CFO masks; baseline sign and timing shared across groups per scan')
    pp=HERE/'protocol.json';pp.write_text(json.dumps(protocol,indent=2)+'\n');receiver=geodetic_to_ecef_km(lat,lon,0);la,lo=np.radians([lat,lon]);east=np.array([-np.sin(lo),np.cos(lo),0]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]);rows=[]
    for scan,prepared in zip(source['scans'],inputs['scans']):
        sid=scan['session_id'];assert sid==prepared['session_id'];path=ROOT/'2026_09_27_ds6_common_rate_validation'/(sid+'-plan.json');plan=json.loads(path.read_text());cat=pair.u.load_catalogue(plan);tracks={t['track_id']:t for t in plan['tracks']};indices=np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')]);prior=-2*np.log(len(indices));groups=[]
        for g,pg in zip(scan['groups'],prepared['groups']):
            assert g['group']==pg['group'];paired=pair.dd.paired_observations(*[tracks[t] for t in g['track_ids']]);mask=paired['mask'];n=len(mask);measured=paired['measured'][1]-paired['measured'][0];pt=np.array([o['time_s'] for o in pg['observations']]);states=[]
            for mode in [0,1]:
                preds=[];projs=[];visible=[]
                for first in range(0,len(indices),256):
                    p,v,valid=propagate_candidate_states(cat,indices[first:first+256],plan['start_utc_ns'],np.r_[paired['source_times'][mode],pt],taus);d=p-receiver;d/=np.linalg.norm(d,axis=-1,keepdims=True)
                    preds.append(-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(d[:,:,:n]*v[:,:,:n],axis=-1));projs.append(d[:,:,n:]@east);visible.append(np.any((d[:,:,:n]@up)[...,mask]>=0,axis=-1))
                states.append(dict(pred=np.concatenate(preds),proj=np.concatenate(projs),visible=np.concatenate(visible)))
            a,b=states;scale=2*np.pi*.08*tracks[g['track_ids'][0]]['rf_hz']/299792458.;stats={arm:{k:np.full((2,len(taus)),-np.inf) for k in ['train','joint']} for arm in arms};counts=[]
            for ti,tau in enumerate(taus):
                ia=np.flatnonzero(a['visible'][:,ti]);ib=np.flatnonzero(b['visible'][:,ti]);counts.append(len(ia)*len(ib))
                for first in range(0,len(ia),16):
                    aa=ia[first:first+16];res=(measured-(b['pred'][ib,ti][None,:,:]-a['pred'][aa,ti][:,None,:])).reshape(-1,n);ct,cj=pair.u.robust_scores(res,mask,sigma=g['differential_scale_hz']);ct+=prior;cj+=prior
                    geom=(scale*(b['proj'][ib,ti][None,:,:]-a['proj'][aa,ti][:,None,:])).reshape(-1,2);change=geom[:,1]-geom[:,0]
                    for si,sign in enumerate([-1,1]):
                        for name,epsilon in arms.items():
                            ph=0 if epsilon is None else factor(pg['offset_correlation'],sign*change,epsilon)
                            stats[name]['train'][si,ti]=np.logaddexp(stats[name]['train'][si,ti],logsumexp(ct+ph));stats[name]['joint'][si,ti]=np.logaddexp(stats[name]['joint'][si,ti],logsumexp(cj+ph))
            groups.append(dict(group=g['group'],pair_counts=counts,arms={a:{k:v.tolist() for k,v in d.items()} for a,d in stats.items()}));print(sid,len(groups),'elapsed',round(time.monotonic()-start,1),flush=True)
        scores={}
        for arm in arms:
            train=sum(np.array(g['arms'][arm]['train']) for g in groups);joint=sum(np.array(g['arms'][arm]['joint']) for g in groups);z=logsumexp(train)
            scores[arm]=dict(held_cfo_log_predictive=float(logsumexp(joint)-z),timing_posterior=np.exp(logsumexp(train,axis=0)-z).tolist(),baseline_sign_posterior=np.exp(logsumexp(train,axis=1)-z).tolist())
        rows.append(dict(session_id=sid,plan_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),groups=groups,scores=scores))
        (HERE/'results.json').write_text(json.dumps(dict(complete=len(rows)==len(source['scans']),protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),elapsed_s=time.monotonic()-start,scans=rows),indent=2)+'\n')
    print(json.dumps([{k:v for k,v in r.items() if k!='groups'} for r in rows],indent=2))


if __name__=='__main__':main()
