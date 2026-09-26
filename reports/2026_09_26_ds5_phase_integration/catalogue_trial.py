"""Bounded real catalogue-pair trial with shared whole-second holdouts.

This is a zero-orbit-time-offset baseline, not a replacement for DS5's timing
marginalization. It tests whether real phase changes held candidate predictions.
"""
from pathlib import Path
import argparse,hashlib,json
from collections import defaultdict
import numpy as np
from scipy.special import logsumexp
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.sky.frames import geodetic_to_ecef_km
from phase_factor import phase_evidence

HERE=Path(__file__).resolve().parent
C=299792458.
VISIT_STARTS={}
PARTITION_OVERRIDES={}
FOLD=0

def visit_bins(sid,times):
    # Bind all phase/CFO observations in a visit to its start-time bin, so a
    # midpoint crossing a second boundary cannot split the same raw dwell.
    if sid not in VISIT_STARTS:
        raw=json.loads((Path('/srv/bulk/leo/scanner-adaptive-recordings')/sid/'manifest.json').read_text())['manifest']
        t=raw['timing']
        VISIT_STARTS[sid]=np.array([(e['valid_start_counter']-t['session_start_device_sample_counter'])/t['sample_rate_hz'] for e in raw['receipt']['events']])
    starts=VISIT_STARTS[sid];index=np.searchsorted(starts,np.asarray(times),side='right')-1
    if np.any(index<0):raise ValueError('observation precedes first valid visit')
    bins=np.floor(starts[index]).astype(int)
    return bins

def partition(sid,times):
    bins=visit_bins(sid,times);overrides=PARTITION_OVERRIDES.get(sid,{})
    return np.array([overrides.get(int(b),(int(hashlib.sha256(f'phase-catalogue-20260927:{sid}:{b}'.encode()).hexdigest()[:8],16)%10<6) ^ bool(FOLD)) for b in bins])

def average_blocks(values,times,mask):
    bins=np.floor(times).astype(int)
    return np.stack([values[...,mask&(bins==b)].mean(axis=-1) for b in np.unique(bins[mask])],axis=-1)

def constant_log_evidence(residual,sigma=100.,prior_sigma=1e6):
    n=residual.shape[-1];v=sigma**2;B=prior_sigma**2;mean=residual.mean(axis=-1)
    return -.5*(n*np.log(2*np.pi)+(n-1)*np.log(v)+np.log(v+n*B)+np.sum((residual-mean[...,None])**2,axis=-1)/v+n*mean**2/(v+n*B))

def site_vectors(site):
    lat,lon=np.radians([site['latitude_deg'],site['longitude_deg']])
    ecef=geodetic_to_ecef_km(site['latitude_deg'],site['longitude_deg'],0)
    east=np.array([-np.sin(lon),np.cos(lon),0.]);north=np.array([-np.sin(lat)*np.cos(lon),-np.sin(lat)*np.sin(lon),np.cos(lat)])
    up=np.array([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])
    axis=np.sin(np.radians(79))*east+np.cos(np.radians(79))*north
    return ecef,up,axis

def shortlist(p,track,site,calibrate_scale=False):
    receiver,up,_=site_vectors(site);mask=partition(p.session_id,track.times_s)
    if min(mask.sum(),(~mask).sum())<2:raise ValueError('insufficient grouped CFO split')
    retained=[]
    for start in range(0,len(p.candidate_indices),512):
        position,velocity,indices=propagate_candidate_states(p.catalogue,p.candidate_indices[start:start+512],p.start_utc_ns,track.times_s,np.array([0.]))
        dr=position[:,0]-receiver;distance=np.linalg.norm(dr,axis=-1)
        unit=dr/distance[...,None]
        prediction=-11.2e9/(C/1000)*np.sum(unit*velocity[:,0],axis=-1)
        # Candidate visibility is selected only on training observations.
        visible=np.max(np.sum(unit[:,mask]*up,axis=-1),axis=-1)>0
        residual=track.measured_hz[None,:]-prediction
        tr=average_blocks(residual,track.times_s,mask);te=average_blocks(residual,track.times_s,~mask)
        train=constant_log_evidence(tr);joint=constant_log_evidence(np.concatenate([tr,te],axis=-1))
        for i in np.flatnonzero(visible):
                retained.append(dict(candidate_id=str(p.catalogue.satellite_numbers[indices[i]]),catalogue_index=int(indices[i]),train_log_evidence=float(train[i]),held_log_predictive=float(joint[i]-train[i]),train_blocks=tr.shape[-1],held_blocks=te.shape[-1],training_rms_hz=float(np.sqrt(np.mean((tr[i]-tr[i].mean())**2))),train_residuals=tr[i].tolist(),held_residuals=te[i].tolist()))
    result=sorted(retained,key=lambda r:(-r['train_log_evidence'],r['candidate_id']))[:4]
    sigma=max(100.,result[0]['training_rms_hz']) if calibrate_scale else 100.
    for r in result:
        tr=np.array(r.pop('train_residuals'));te=np.array(r.pop('held_residuals'))
        score=constant_log_evidence(tr,sigma=sigma)
        r.update(cfo_sigma_hz=sigma,train_log_evidence=float(score),held_log_predictive=float(constant_log_evidence(np.concatenate([tr,te]),sigma=sigma)-score))
    return result

def main():
    global FOLD
    parser=argparse.ArgumentParser();parser.add_argument('--alias-equivalent',action='store_true');parser.add_argument('--balanced-groups',action='store_true');parser.add_argument('--fold',type=int,choices=[0,1],default=0);parser.add_argument('--calibrate-cfo-scale',action='store_true');args=parser.parse_args()
    FOLD=args.fold
    stem='catalogue-alias-trial' if args.alias_equivalent else 'catalogue-trial'
    if args.balanced_groups:stem+=f'-balanced-f{args.fold}'
    if args.calibrate_cfo_scale:stem+='-dispersion'
    audit=json.loads((HERE/'catalogue-input-audit.json').read_text());out=[]
    protocol=dict(seed_policy='sha256 phase-catalogue-20260927:session:visit-start-second-bin, modulo10 <6 training; same assignment for all CFO/phase samples in each dwell',selection='existing real phase groups with at least four exact recurring production-track pair visits; full visible catalogue top4 per CFO track on train only',site='previous DS5 fixed reference evaluation coordinate; conditional site hypothesis, not newly surveyed',baseline_grid_m=[-2.,2.,.01],baseline_prior='uniform grid; illustrative unmeasured range; zero included',phase_kappas=[.5,1.,2.],orbit_time_offset_s=0.,phase_intercept='one constant per recurring pair, analytically integrated',likelihood='CFO 100Hz per occupied-second block; phase one circular mean per dwell',meaning='conditional held predictive scores, not satellite identity ground truth; no deployment')
    protocol['membership']='same-epoch CFO-alias equivalent, unique per receiver' if args.alias_equivalent else 'exact acquisition candidate'
    protocol.update(balanced_phase_groups=args.balanced_groups,fold=args.fold,cfo_scale='max(100 Hz, best candidate training RMS), fixed across candidates per track' if args.calibrate_cfo_scale else '100 Hz')
    (HERE/(stem+'-protocol.json')).write_text(json.dumps(protocol,indent=2)+'\n')
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        for scan in audit['scans']:
            groups=[g for g in scan['equivalent_recurring_pairs' if args.alias_equivalent else 'recurring_pairs'] if len(g['visits'])>=4]
            if not groups:continue
            sid=scan['session_id'];p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
            assert p.evidence_sha256==scan['evidence_sha256'] and p.snapshot_digest==scan['snapshot_digest']
            tracks={t.track_id:t for t in p.tracks};phase_rows=json.loads((HERE/(sid+'.json')).read_text())['rows']
            receiver,up,axis=site_vectors(scan['sites']['reference']);cache={}
            for group in groups:
                _,_,left_id,right_id=json.loads(group['key']);pair_ids=[left_id,right_id]
                observations=[]
                for visit in group['visits']:
                    modes=[sorted([r for r in phase_rows if r['visit']==visit and r['mode']==m],key=lambda r:r['start_ms']) for m in (0,1)]
                    a,b=[np.array([r['coefficients']['full']['phase_rad'] for r in s]) for s in modes]
                    z=np.mean(np.exp(1j*(b-a)));utc=round(np.mean([r['utc_ns']-p.start_utc_ns for r in modes[0]]))
                    observations.append(dict(visit=visit,time_s=utc/1e9,dd_phase=float(np.angle(z)),dd_R=float(abs(z)),rf0_hz=modes[0][0]['rf_estimate_hz'],rf1_hz=modes[1][0]['rf_estimate_hz']))
                times=np.array([r['time_s'] for r in observations])
                if args.balanced_groups:
                    bins=np.unique(visit_bins(sid,times));rng=np.random.default_rng(20260927)
                    chosen=set(map(int,rng.choice(bins,len(bins)//2,replace=False)))
                    PARTITION_OVERRIDES[sid]={int(b):(int(b) in chosen)^bool(FOLD) for b in bins}
                train=partition(sid,times)
                if not train.any() or train.all():
                    out.append(dict(session_id=sid,group=group,status='no mixed whole-second phase partition',observations=observations));continue
                for tid in pair_ids:
                    if tid not in cache:cache[tid]=shortlist(p,tracks[tid],scan['sites']['reference'],args.calibrate_cfo_scale)
                aopts,bopts=[cache[t] for t in pair_ids];unique=sorted({r['catalogue_index'] for r in aopts+bopts})
                positions,_,valid=propagate_candidate_states(p.catalogue,unique,p.start_utc_ns,times,np.array([0.]))
                vectors=positions[:,0]-receiver;vectors/=np.linalg.norm(vectors,axis=-1)[...,None]
                projections={int(index):vectors[i]@axis for i,index in enumerate(valid)}
                B=np.linspace(-2,2,401);pairs=[];models=[]
                f0=np.array([r['rf0_hz'] for r in observations]);f1=np.array([r['rf1_hz'] for r in observations])
                for a in aopts:
                    for b in bopts:
                        u0=projections[a['catalogue_index']];u1=projections[b['catalogue_index']]
                        models.append(2*np.pi*B[:,None]*(f1*u1-f0*u0)[None,:]/C)
                        pairs.append(dict(left_id=a['candidate_id'],right_id=b['candidate_id'],cfo_train=a['train_log_evidence']+b['train_log_evidence'],cfo_held=a['held_log_predictive']+b['held_log_predictive']))
                predicted=np.array(models);observed=np.array([r['dd_phase'] for r in observations]);lp=np.array([r['cfo_train'] for r in pairs]);lp-=logsumexp(lp)
                cfo_held=np.array([r['cfo_held'] for r in pairs]);baseline_score=float(logsumexp(lp+cfo_held))
                modes=[]
                for k in protocol['phase_kappas']:
                    kt=np.full(train.sum(),k);ka=np.full(len(train),k)
                    tr=phase_evidence(observed[train],predicted[...,train],kt);full=phase_evidence(observed,predicted,ka)
                    logtr=logsumexp(tr,axis=1)-np.log(len(B));logfull=logsumexp(full,axis=1)-np.log(len(B))
                    posterior=lp+logtr;posterior-=logsumexp(posterior)
                    jointheld=float(logsumexp(lp+cfo_held+logfull)-logsumexp(lp+logtr))
                    phaseheld=float(logsumexp(lp+logfull)-logsumexp(lp+logtr))
                    cfo_withphase=float(logsumexp(posterior+cfo_held))
                    constant=float(phase_evidence(observed,np.zeros(len(observed)),ka)-phase_evidence(observed[train],np.zeros(train.sum()),kt))
                    modes.append(dict(kappa=k,cfo_only_held_log_predictive=baseline_score,cfo_held_after_phase_training=cfo_withphase,cfo_held_gain=cfo_withphase-baseline_score,phase_held_log_predictive_vs_uniform=phaseheld,constant_phase_held_log_predictive_vs_uniform=constant,phase_held_gain_vs_constant=phaseheld-constant,joint_cfo_phase_held_log_predictive=jointheld,posterior_probabilities=np.exp(posterior).tolist(),top_pair=pairs[int(np.argmax(posterior))]))
                result=dict(session_id=sid,group=group,status='scored',phase_training_dwell_count=int(train.sum()),phase_identity_information_possible=bool(train.sum()>1),snapshot_digest=p.snapshot_digest,site=scan['sites']['reference'],observations=observations,phase_training_mask=train.tolist(),left_candidates=aopts,right_candidates=bopts,pairs=pairs,cfo_only_probabilities=np.exp(lp).tolist(),experiments=modes)
                out.append(result);print(sid,'scored',len(pairs),'candidate pairs',len(observations),'dwells','gains',[m['cfo_held_gain'] for m in modes],flush=True)
    finally:store.close()
    (HERE/(stem+'.json')).write_text(json.dumps(dict(protocol=protocol,groups=out),indent=2)+'\n')

if __name__=='__main__':main()
