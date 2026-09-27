"""Exact orbit local comparison with shared quarter-second timing grid."""
import sys,json,hashlib,time
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.sky.propagation import parse_element_sets
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states,REFERENCE_RF_HZ,LIGHT_KM_S
from leo.sky.frames import geodetic_to_ecef_km
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;OLD=ROOT/'2026_09_27_ds6_alltrack_phase'
sys.path.insert(0,str(ROOT/'2026_09_27_ds6_orbit_phase'))
from run import cfo_evidence,phase_evidence
from robust import robust_scores

def site(lat,lon):
    la,lo=np.radians([lat,lon]);return geodetic_to_ecef_km(lat,lon,0),np.array([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]),np.array([-np.sin(lo),np.cos(lo),0.])

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--robust',action='store_true');parser.add_argument('--extend',action='store_true');args=parser.parse_args()
    if args.extend and not args.robust:parser.error('--extend requires --robust')
    output=HERE/('robust-extended' if args.extend else 'robust') if args.robust else HERE;output.mkdir(exist_ok=True)
    started=time.monotonic();data=json.loads((OLD/'inputs.json').read_text());prior_path=HERE/'robust/results.json' if args.extend else OLD/'refine-3.json';prior=json.loads(prior_path.read_text());assert prior['complete'];center=prior['best']['quarter']['cfo'] if args.extend else prior['best_cfo'];lat0,lon0=center['latitude'],center['longitude'];taus=np.arange(-5,5.001,.25)
    coordinates=[(float(a),float(b)) for a in np.linspace(lat0-.0125,lat0+.0125,9) for b in np.linspace(lon0-.015625,lon0+.015625,9)]
    anchors=[(lat0,lon0),coordinates[0],coordinates[8],coordinates[-9],coordinates[-1]]
    protocol=dict(session_id=data['session_id'],inputs_sha256=hashlib.sha256((OLD/'inputs.json').read_bytes()).hexdigest(),prior_search_sha256=hashlib.sha256(prior_path.read_bytes()).hexdigest(),center_selected_from_prior_training_score=[lat0,lon0],timing_offsets_s=taus.tolist(),candidate_selection='Union of top eight per track/time at center and four corners from training CFO only; one-second preliminary propagation, exact propagation for retained candidates',coordinates=coordinates,arms=['exact_integer_time','exact_quarter_second_time'],phase='Same nominal-baseline joined phase factor as preceding all-track experiment; top six per source/time; omitted candidate mass neutral',selection='Training score only; operator coordinate absent from search',scope='Local single-development-scan comparison; catalogue shortlists are approximate')
    protocol['cfo_model']='Student-t4,100Hz; training-profiled offset frozen on held data' if args.robust else 'Gaussian100Hz with integrated constant offset'
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    tracks=data['tracks']
    for t in tracks:t.update(t=np.array(t['times_s']),y=np.array(t['measured_hz']),mask=np.array(t['training_mask']))
    tracks=[t for t in tracks if t['mask'].sum()>=2 and (~t['mask']).sum()>=1]
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));snap=archive.select_latest_before(data['start_utc_ns']-505_000_000_000);assert snap.digest==data['snapshot_digest'];payload,_=exclude_labelled_starlink_debris(archive.read(snap));cat=parse_element_sets(payload)
    nodes=np.arange(np.floor(min(t['t'].min() for t in tracks))-6,np.ceil(max(t['t'].max() for t in tracks))+7)
    pos,vel,ids=propagate_candidate_states(cat,np.arange(len(cat.satellite_numbers)),data['start_utc_ns'],nodes,np.array([0.]));pos=pos[:,0];vel=vel[:,0]
    selected={t['track_id']:set() for t in tracks};min_mass=1.
    for lat,lon in anchors:
        rec,up,_=site(lat,lon);dr=pos-rec;u=dr/np.linalg.norm(dr,axis=-1)[...,None];el=u@up;active=np.flatnonzero(np.any(el>=0,axis=1));pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(u[active]*vel[active],axis=-1)
        for t in tracks:
            q=t['t'][None,:]+taus[:,None]-nodes[0];lo=np.floor(q).astype(int);w=q-lo
            predicted=pred[:,lo]*(1-w)+pred[:,lo+1]*w;visibility=np.any((el[active][:,lo]*(1-w)+el[active][:,lo+1]*w)[:,:,t['mask']]>=0,axis=-1)
            residual=t['y'][None,None,:]-predicted
            score=np.where(visibility,robust_scores(residual,t['mask'])[0] if args.robust else cfo_evidence(residual[:,:,t['mask']]),-np.inf)
            chosen=np.argsort(score,axis=0)[-8:];selected[t['track_id']].update(ids[active[chosen.ravel()]].tolist())
            mass=np.exp(logsumexp(np.take_along_axis(score,chosen,axis=0),axis=0)-logsumexp(score,axis=0));min_mass=min(min_mass,float(mass.min()))
        print('shortlist anchor',lat,lon,'minimum top-eight mass',min_mass,flush=True)
    phase_pair=data['recurring_rx0_pairs'][0];allrows=json.loads((ROOT/'2026_09_27_latest_ten_phase'/f"{data['session_id']}.json").read_text())['rows'];obs=[]
    for visit in phase_pair['visits']:
        rr=[r for r in allrows if r['visit']==visit and r['both_qualified']]
        if rr:obs.append(dict(t=float(np.mean([r['time_s'] for r in rr])),y=float(np.angle(np.mean([np.exp(1j*(r['modes'][1]['evaluation']['phase_rad']-r['modes'][0]['evaluation']['phase_rad'])) for r in rr]))),train=rr[0]['partition']=='train'))
    phase_times=np.array([o['t'] for o in obs]);phase_y=np.array([o['y'] for o in obs]);phase_mask=np.array([o['train'] for o in obs])
    banks={};shortlists=[]
    for i,t in enumerate(tracks):
        chosen=np.array(sorted(selected[t['track_id']]));times=np.r_[t['t'],phase_times] if t['track_id'] in phase_pair['track_ids'] else t['t']
        p,v,valid=propagate_candidate_states(cat,chosen,data['start_utc_ns'],times,taus)
        banks[t['track_id']]=(p,v,valid)
        shortlists.append(dict(track_id=t['track_id'],catalogue_indices=valid.tolist(),satellite_numbers=np.array(cat.satellite_numbers)[valid].astype(str).tolist()))
        if i%10==0:print('exact banks',i+1,'of',len(tracks),flush=True)
    (output/'shortlists.json').write_text(json.dumps(dict(minimum_top_eight_mass_at_anchors=min_mass,tracks=shortlists),indent=2)+'\n')
    del pos,vel
    results=[];integer=np.isclose(taus,np.round(taus));diagnostics=[]
    for lat,lon in coordinates:
        rec,up,east=site(lat,lon);bytrack={};base=[];joint=[];projection={}
        for t in tracks:
            p,v,valid=banks[t['track_id']];dr=p-rec;u=dr/np.linalg.norm(dr,axis=-1)[...,None];n=len(t['t']);pr=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(u[:,:,:n]*v[:,:,:n],axis=-1);vis=np.any((u[:,:,:n]@up)[:,:,t['mask']]>=0,axis=-1)
            res=t['y'][None,None,:]-pr
            ca,cb=robust_scores(res,t['mask']) if args.robust else (cfo_evidence(res[:,:,t['mask']]),cfo_evidence(res))
            a=np.where(vis,ca,-np.inf);b=np.where(vis,cb,-np.inf)
            bytrack[t['track_id']]=(a,b);base.append(logsumexp(a,axis=0)-np.log(len(ids)));joint.append(logsumexp(b,axis=0)-np.log(len(ids)))
            if abs(lat-lat0)<1e-12 and abs(lon-lon0)<1e-12:
                ti=int(np.argmin(abs(taus-center['cfo_map_time_s'])));ci=int(np.argmax(a[:,ti]));r=res[ci,ti];offset=float(r[t['mask']].mean());centered=r-offset
                train_rms=float(np.sqrt(np.mean(centered[t['mask']]**2)));held_rms=float(np.sqrt(np.mean(centered[~t['mask']]**2)))
                slope=float(np.polyfit(t['t'][t['mask']]-t['t'][t['mask']].mean(),centered[t['mask']],1)[0])
                diagnostics.append(dict(track_id=t['track_id'],receiver_id=t['receiver_id'],channel=t['channel'],observations=n,span_s=float(np.ptp(t['t'])),candidate=str(cat.satellite_numbers[valid[ci]]),time_s=float(taus[ti]),train_rms_hz=train_rms,held_rms_hz=held_rms,training_residual_slope_hz_s=slope,offset_hz=offset))
            if t['track_id'] in phase_pair['track_ids']:projection[t['track_id']]=u[:,:,n:]@east
        bs=np.sum(base,axis=0);js=np.sum(joint,axis=0);pa,pb=phase_pair['track_ids'];a,aj=bytrack[pa];b,bj=bytrack[pb];extra=[];extraj=[]
        for ti in range(len(taus)):
            ia=np.argsort(a[:,ti])[-6:];ib=np.argsort(b[:,ti])[-6:];g=2*np.pi*.08*11.46e9/299792458.*(projection[pb][ib,ti][None,:,:]-projection[pa][ia,ti][:,None,:])
            for aa,bb,mask,target in [(a,b,phase_mask,extra),(aj,bj,np.ones(len(obs),bool),extraj)]:
                weight=aa[ia,ti,None]+bb[ib,ti][None,:]-logsumexp(aa[:,ti])-logsumexp(bb[:,ti]);mass=float(np.exp(logsumexp(weight)));factor=logsumexp(np.stack([phase_evidence(phase_y[mask],sign*g[:,:,mask],np.ones(mask.sum())) for sign in [-1,1]]),axis=0)-np.log(2)
                target.append(float(np.logaddexp(logsumexp(weight+factor),np.log(max(1-mass,1e-300)))))
        for name,mask in [('integer',integer),('quarter',np.ones(len(taus),bool))]:
            x=bs[mask];z=js[mask];xp=x+np.array(extra)[mask];zp=z+np.array(extraj)[mask]
            results.append(dict(arm=name,latitude=lat,longitude=lon,cfo_train=float(logsumexp(x)-np.log(mask.sum())),joint_train=float(logsumexp(xp)-np.log(mask.sum())),cfo_held=float(logsumexp(z)-logsumexp(x)),joint_held=float(logsumexp(zp)-logsumexp(xp)),cfo_map_time_s=float(taus[mask][np.argmax(x)]),joint_map_time_s=float(taus[mask][np.argmax(xp)])))
        if len(results)%18==0:
            print('local points',len(results)//2,'elapsed',round(time.monotonic()-started,1),flush=True)
            (output/'results.json').write_text(json.dumps(dict(complete=len(results)==162,rows=results,elapsed_s=time.monotonic()-started,best={arm:{key:max([r for r in results if r['arm']==arm],key=lambda r:r[key+'_train']) for key in ['cfo','joint']} for arm in ['integer','quarter']}),indent=2)+'\n')
    assert len(diagnostics)==len(tracks)
    (output/'track-diagnostics.json').write_text(json.dumps(diagnostics,indent=2)+'\n')
if __name__=='__main__':main()
