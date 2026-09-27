"""Held-visit test of a shared frequency-dependent receiver phase response."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.sky.propagation import parse_element_sets
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.sky.frames import geodetic_to_ecef_km
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'2026_09_27_ds6_orbit_phase'))
from run import cfo_evidence,phase_evidence
C=299792458.

def integrate_groups(groups,delay,weights):
    """All groups share baseline sign, timing and (for delay arm) response delay."""
    scores={}
    for arm in ['independent_offsets','shared_delay']:
        tr=[];allphase=[];heldcfo=[]
        for g in groups:
            if arm=='independent_offsets':
                phase_train=np.stack([phase_evidence(g['y'][g['mask']],sign*g['geometry'][...,g['mask']],np.ones(g['mask'].sum())) for sign in [-1,1]])
                phase_all=np.stack([phase_evidence(g['y'],sign*g['geometry'],np.ones(len(g['y']))) for sign in [-1,1]])
            else:
                prediction=np.array([-1.,1.])[:,None,None,None,None]*g['geometry'][None,None,:,:,:]+2*np.pi*delay[None,:,None,None,None]*g['df'][None,None,None,None,:]
                residual=g['y'][None,None,None,None,:]-prediction
                # Density relative to uniform phase, kappa=1 per dwell.
                from scipy.special import i0
                density=np.cos(residual)-np.log(i0(1.))
                phase_train=density[...,g['mask']].sum(axis=-1)
                phase_all=density.sum(axis=-1)
            tr.append(logsumexp(g['cfo_train']+phase_train,axis=-1))
            allphase.append(logsumexp(g['cfo_train']+phase_all,axis=-1))
            heldcfo.append(logsumexp(g['cfo_joint']+phase_train,axis=-1))
        total=sum(tr);pa=sum(allphase);cf=sum(heldcfo)
        if arm=='shared_delay':
            logprior=np.log(weights)[None,:,None]-np.log(total.shape[0]*total.shape[-1])
        else:logprior=-np.log(total.size)
        z=logsumexp(total+logprior)
        scores[arm]=dict(training_log_evidence=float(z),held_phase_log_predictive=float(logsumexp(pa+logprior)-z),held_cfo_log_predictive=float(logsumexp(cf+logprior)-z))
        if arm=='shared_delay':
            posterior=np.exp(logsumexp(total+logprior,axis=(0,2))-z)
            scores[arm]['delay_posterior']=posterior.tolist();scores[arm]['delay_mean_us']=float(posterior@delay*1e6);scores[arm]['delay_map_us']=float(delay[np.argmax(posterior)]*1e6)
    # CFO-only shares scan time across groups; no phase enters this baseline.
    tr=sum(logsumexp(g['cfo_train'],axis=-1) for g in groups);joint=sum(logsumexp(g['cfo_joint'],axis=-1) for g in groups)
    scores['cfo_only']=dict(training_log_evidence=float(logsumexp(tr)-np.log(len(tr))),held_cfo_log_predictive=float(logsumexp(joint)-logsumexp(tr)))
    return scores

def main():
    sid='scan-fw-da2858f6cd2521b7';plan_path=ROOT/'2026_09_27_latest_ten_phase/plan.json';data_path=ROOT/'2026_09_27_latest_ten_phase'/f'{sid}.json'
    plan=json.loads(plan_path.read_text());scan=next(s for s in plan['scans'] if s['session_id']==sid);rows=json.loads(data_path.read_text())['rows']
    ds6=json.loads((ROOT/'2026_09_27_ds6_roof/manifest.json').read_text());assert next(r for r in ds6['captures'] if r['session_id']==sid)['manifest_sha256']==scan['capture_digest']
    observer_path=ROOT/'2026_09_27_ds6_exact_timing/robust-extended/results.json';observer=json.loads(observer_path.read_text())['best']['quarter']['cfo'];lat,lon=observer['latitude'],observer['longitude']
    groups=[]
    for key in sorted({v['group'] for v in scan['selected'] if v['partition'] in ['train','held']}):
        obs=[]
        for v in scan['selected']:
            if v['group']!=key:continue
            rr=[r for r in rows if r['visit']==v['visit'] and r['both_qualified']]
            if not rr:continue
            cf=[m['seeds'][0]['cfo_hz'] for m in v['modes']]
            obs.append(dict(visit=v['visit'],t=float(np.mean([r['time_s'] for r in rr])),phase=float(np.angle(np.mean([np.exp(1j*(r['modes'][1]['evaluation']['phase_rad']-r['modes'][0]['evaluation']['phase_rad'])) for r in rr]))),train=v['partition']=='train',cfo=cf,df=cf[1]-cf[0],rf=v['rf_center_hz'],channel=v['channel'],edge=v['edge']))
        groups.append(dict(key=key,observations=obs))
    assert len(groups)==2 and {(o['channel'],o['edge']) for g in groups for o in g['observations']}=={(3,'lower')}
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));snapshot=archive.select_latest_before(scan['capture_utc_ns']-505_000_000_000);payload,_=exclude_labelled_starlink_debris(archive.read(snapshot));catalogue=parse_element_sets(payload);taus=np.arange(-5.,6.)
    protocol=dict(session_id=sid,input_manifest_sha256=scan['capture_digest'],phase_sha256=hashlib.sha256(data_path.read_bytes()).hexdigest(),plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),observer_source_sha256=hashlib.sha256(observer_path.read_bytes()).hexdigest(),observer_from_other_scan_cfo=[lat,lon],snapshot_digest=snapshot.digest,groups=groups,timing_offsets_s=taus.tolist(),baseline_m=[-.08,.08],response_delay_prior_us=[-10,10],delay_grid_points=401,cfo_sigma_hz=100.,phase_kappa=1.,candidate_limit_per_source_per_timing=6,scope='Conditional shared-response development test; no location search, coordinate truth or verified satellite IDs',response_model='DD phase = nominal geometric DD + 2pi*(RX0 GLRT frequency separation)*shared delay. Compare independent uniform pair offsets. Delay and sign shared across both pairs.',limitations=['Physical group delay and calibrated RF baseline unavailable','GLRT frequency aliases and source-dependent antenna phase may violate shared-delay model','Different visits may have different hardware response after retuning','Candidate selection uses six visit CFO values per source; truncated catalogue support','Observer inferred from another already studied scan; not an independent global validation'])
    (HERE/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    rec=geodetic_to_ecef_km(lat,lon,0);la,lo=np.radians([lat,lon]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]);east=np.array([-np.sin(lo),np.cos(lo),0.]);banks=[]
    for group in groups:
        obs=group['observations'];t=np.array([o['t'] for o in obs]);y=np.array([o['phase'] for o in obs]);mask=np.array([o['train'] for o in obs]);cfo=np.array([o['cfo'] for o in obs]).T;rf=obs[0]['rf']
        p,v,ids=propagate_candidate_states(catalogue,np.arange(len(catalogue.satellite_numbers)),scan['capture_utc_ns'],t,taus);dr=p-rec;u=dr/np.linalg.norm(dr,axis=-1)[...,None];pred=-rf/(C/1000)*np.sum(u*v,axis=-1);visible=np.all((u@up)[:,:,mask]>0,axis=-1)
        residual=cfo[:,None,None,:]-pred[None,:,:,:];tr=cfo_evidence(residual[...,mask]);joint=cfo_evidence(residual);geometries=[];ct=[];cj=[];selected=[];jac=[]
        derivatives=[]
        for delta_lat,delta_lon in [(0.,np.degrees(1/6371.0088)/np.cos(la)),(np.degrees(1/6371.0088),0.)]:
            projections=[];receivers=[]
            for sign in [-1,1]:
                alt_lat,alt_lon=lat+sign*delta_lat,lon+sign*delta_lon
                receiver=geodetic_to_ecef_km(alt_lat,alt_lon,0);direction=p-receiver;direction/=np.linalg.norm(direction,axis=-1)[...,None];e=np.array([-np.sin(np.radians(alt_lon)),np.cos(np.radians(alt_lon)),0.])
                projections.append(direction@e);receivers.append(receiver)
            derivatives.append((projections[1]-projections[0])/np.linalg.norm(receivers[1]-receivers[0]))
        for ti in range(len(taus)):
            eligible=np.flatnonzero(visible[:,ti]);chosen=[eligible[np.argsort(tr[m,eligible,ti])[-6:]] for m in [0,1]];a,b=chosen
            geometries.append((2*np.pi*.08*rf/C*((u[b,ti]@east)[None,:,:]-(u[a,ti]@east)[:,None,:])).reshape(36,len(t)))
            jac.append(np.stack([(2*np.pi*.08*rf/C*(derivative[b,ti][None,:,:]-derivative[a,ti][:,None,:])).reshape(36,len(t)) for derivative in derivatives],axis=-1))
            ct.append((tr[0,a,ti,None]+tr[1,b,ti][None,:]).ravel()-2*np.log(len(ids)))
            cj.append((joint[0,a,ti,None]+joint[1,b,ti][None,:]).ravel()-2*np.log(len(ids)))
            selected.append([np.array(catalogue.satellite_numbers)[ids[idx]].astype(str).tolist() for idx in chosen])
        banks.append(dict(y=y,mask=mask,df=np.array([o['df'] for o in obs]),geometry=np.array(geometries),geometry_jacobian_rad_per_km=np.array(jac),cfo_train=np.array(ct),cfo_joint=np.array(cj)))
        group['shortlists']=selected
    def serial(v):return v.tolist() if isinstance(v,np.ndarray) else v
    (HERE/'banks.json').write_text(json.dumps(banks,default=serial)+'\n');(HERE/'shortlists.json').write_text(json.dumps(groups,indent=2)+'\n')
    results={}
    for n in [401,801]:
        delay=np.linspace(-10e-6,10e-6,n);weight=np.ones(n);weight[[0,-1]]=.5;weight/=weight.sum();results[str(n)]=dict(delay_us=(delay*1e6).tolist(),scores=integrate_groups(banks,delay,weight))
    (HERE/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps({n:{k:{a:b for a,b in v.items() if a!='delay_posterior'} for k,v in r['scores'].items()} for n,r in results.items()},indent=2))
if __name__=='__main__':main()
