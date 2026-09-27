"""Shared response prediction using exact position-track CFO hypotheses."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.sky.propagation import parse_element_sets
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states,REFERENCE_RF_HZ,LIGHT_KM_S
from leo.sky.frames import geodetic_to_ecef_km
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'2026_09_27_ds6_exact_timing'))
from robust import robust_scores
sys.path.insert(0,str(ROOT/'2026_09_27_ds6_shared_phase_response'))
from study import integrate_groups

def main():
    plan=json.loads((HERE/'plan.json').read_text());replay=json.loads((HERE/'replay.json').read_text());assert replay['complete'];assert replay['plan_sha256']==hashlib.sha256((HERE/'plan.json').read_bytes()).hexdigest()
    inputs=json.loads((ROOT/'2026_09_27_ds6_alltrack_phase/inputs.json').read_text());tracks={t['track_id']:t for t in inputs['tracks']}
    shortlist_path=ROOT/'2026_09_27_ds6_exact_timing/robust-extended/shortlists.json';shortlists={r['track_id']:r for r in json.loads(shortlist_path.read_text())['tracks']}
    observer_path=ROOT/'2026_09_27_ds6_exact_timing/robust-extended/results.json';observer=json.loads(observer_path.read_text())['best']['quarter']['cfo'];lat,lon=observer['latitude'],observer['longitude'];la,lo=np.radians([lat,lon]);receiver=geodetic_to_ecef_km(lat,lon,0);east=np.array([-np.sin(lo),np.cos(lo),0.]);up=np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)])
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));snapshot=archive.select_latest_before(inputs['start_utc_ns']-505_000_000_000);assert snapshot.digest==inputs['snapshot_digest'];payload,_=exclude_labelled_starlink_debris(archive.read(snapshot));cat=parse_element_sets(payload);taus=np.arange(-5.,5.001,.25)
    banks=[];observations=[];selected_ids=[]
    for selected in plan['selected_groups']:
        key=selected['group'];visits=[v for v in plan['selected'] if v['group']==key];obs=[]
        for v in visits:
            rr=[r for r in replay['rows'] if r['visit']==v['visit'] and r['group']==key and r['original']['both_qualified']]
            if not rr:continue
            cf=[m['seeds'][0]['cfo_hz'] for m in v['modes']]
            obs.append(dict(visit=v['visit'],t=float(np.mean([r['time_s'] for r in rr])),phase=float(np.angle(np.mean([np.exp(1j*(r['original']['modes'][1]['evaluation']['phase_rad']-r['original']['modes'][0]['evaluation']['phase_rad'])) for r in rr]))),train=v['partition']=='train',df=cf[1]-cf[0],qualified_windows=len(rr)))
        times=np.array([o['t'] for o in obs]);y=np.array([o['phase'] for o in obs]);mask=np.array([o['train'] for o in obs]);assert mask.sum()>=2 and (~mask).sum()>=2
        ids=[m['rx0_track_id'] for m in visits[0]['modes']];selected_ids.extend(ids);state=[]
        for tid in ids:
            track=tracks[tid];t=np.array(track['times_s']);train=np.array(track['training_mask']);n=len(t);chosen=shortlists[tid]['catalogue_indices'];p,v,valid=propagate_candidate_states(cat,chosen,inputs['start_utc_ns'],np.r_[t,times],taus)
            dr=p-receiver;u=dr/np.linalg.norm(dr,axis=-1)[...,None];pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(u[:,:,:n]*v[:,:,:n],axis=-1);visible=np.any((u[:,:,:n]@up)[:,:,train]>=0,axis=-1)
            a,b=robust_scores(np.array(track['measured_hz'])[None,None,:]-pred,train);a=np.where(visible,a,-np.inf);b=np.where(visible,b,-np.inf)
            state.append(dict(train=a,joint=b,projection=u[:,:,n:]@east))
        geometry=[];ct=[];cj=[]
        for ti in range(len(taus)):
            a,b=state;ia=np.argsort(a['train'][:,ti])[-6:];ib=np.argsort(b['train'][:,ti])[-6:]
            geometry.append((2*np.pi*.08*visits[0]['rf_center_hz']/299792458.*(b['projection'][ib,ti][None,:,:]-a['projection'][ia,ti][:,None,:])).reshape(36,len(obs)))
            ct.append((a['train'][ia,ti,None]+b['train'][ib,ti][None,:]).ravel());cj.append((a['joint'][ia,ti,None]+b['joint'][ib,ti][None,:]).ravel())
        banks.append(dict(y=y,mask=mask,df=np.array([o['df'] for o in obs]),geometry=np.array(geometry),cfo_train=np.array(ct),cfo_joint=np.array(cj)));observations.append(dict(group=key,track_ids=ids,observations=obs))
    assert len(selected_ids)==len(set(selected_ids)),'Overlapping tracks require a factor graph rather than independent group products'
    def serial(v):return v.tolist() if isinstance(v,np.ndarray) else v
    (HERE/'response-banks.json').write_text(json.dumps(banks,default=serial)+'\n')
    (HERE/'response-protocol.json').write_text(json.dumps(dict(observer_from_training_cfo=[lat,lon],observer_sha256=hashlib.sha256(observer_path.read_bytes()).hexdigest(),shortlists_sha256=hashlib.sha256(shortlist_path.read_bytes()).hexdigest(),observations=observations,source_pipeline='Original qualified extraction; common-CFO refinement kept as separate diagnostic',baseline_m=[-.08,.08],delay_prior_us=[-10,10],phase_kappa=1,timing_s=taus.tolist(),cfo='Full position-track robust Student-t4 training score and held prediction, not six-visit GLRT-seed fits',scope='Conditional at previously selected observer; selected scan already used in development; catalogue/candidate assumptions remain unverified'),indent=2)+'\n')
    out={}
    for n in [201,401]:
        delay=np.linspace(-10e-6,10e-6,n);weights=np.ones(n);weights[[0,-1]]=.5;weights/=weights.sum();out[str(n)]=dict(delay_us=(delay*1e6).tolist(),scores=integrate_groups(banks,delay,weights))
    (HERE/'response-results.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:{a:{m:v for m,v in b.items() if m!='delay_posterior'} for a,b in r['scores'].items()} for k,r in out.items()},indent=2))
if __name__=='__main__':main()
