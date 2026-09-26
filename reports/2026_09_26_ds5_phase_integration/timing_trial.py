"""Bounded timing-marginalized orbital phase trial on real longer overlaps.

Acquisition-defined track membership; whole-dwell shared CFO/phase folds;
historical timing prior; train-only catalogue proposals and timing posteriors.
"""
from pathlib import Path
import argparse,hashlib,json,time
import numpy as np
from scipy.special import logsumexp
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.analysis.adaptive_tle_prediction import AdaptiveTrackInput
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories,PersistentHopTrajectoryConfig
import catalogue_trial as T
from timing_prior import age_bin,cdf,discrete_weights
from phase_factor import phase_evidence

HERE=Path(__file__).resolve().parent
OUT=HERE/'timing-trial'
C=299792458.

def quantile_indices(logweights,n):
    p=np.exp(logweights-logsumexp(logweights));cumulative=np.cumsum(p);cumulative[-1]=1.
    return np.searchsorted(cumulative,(np.arange(n)+.5)/n)

def prior_weights(cal,age,grid,coarse=False):
    if not coarse:return discrete_weights(cal['model'],age,grid)[0]
    edges=np.r_[grid[0],(grid[:-1]+grid[1:])/2,grid[-1]]
    mass=np.maximum(np.diff(cdf(cal['model'],age,edges)),1e-300)
    return np.log(mass)-np.log(mass.sum())

def residuals(p,track,site,indices,taus):
    position,velocity,valid=propagate_candidate_states(p.catalogue,indices,p.start_utc_ns,track.times_s,taus)
    receiver,up,_=T.site_vectors(site);dr=position-receiver;unit=dr/np.linalg.norm(dr,axis=-1)[...,None]
    prediction=-11.2e9/(C/1000)*np.sum(unit*velocity,axis=-1)
    mask=T.partition(p.session_id,track.times_s)
    visible=np.max(unit[:,:,mask]@up,axis=-1)>0
    residual=track.measured_hz-prediction
    return valid,visible,T.average_blocks(residual,track.times_s,mask),T.average_blocks(residual,track.times_s,~mask)

def make_bank(p,track,site,phase_times,cal,fold):
    path=OUT/f'{p.session_id}-f{fold}-{track.track_id[7:19]}.npz'
    if path.exists():return dict(np.load(path))
    epochs=p.catalogue.element_epoch_utc_ns();coarse=np.arange(-120.,121.,10.);pool=[];priors={}
    def prior(index,grid,coarse=False):
        age=(p.start_utc_ns-epochs[index])/3.6e12;key=(age_bin(cal['model'],age)['lower_h'],coarse)
        if key not in priors:priors[key]=prior_weights(cal,age,grid,coarse)
        return priors[key]
    # Union top eight proposals for both predefined CFO error scales.
    for begin in range(0,len(p.candidate_indices),128):
        valid,visible,tr,te=residuals(p,track,site,p.candidate_indices[begin:begin+128],coarse)
        for j,index in enumerate(valid):
            lp=prior(index,coarse,True)
            scores=[float(logsumexp(np.where(visible[j],T.constant_log_evidence(tr[j],sigma)+lp,-np.inf))) for sigma in (100.,200.)]
            if np.isfinite(scores).all():pool.append((int(index),scores))
    retained=sorted(set().union(*[{r[0] for r in sorted(pool,key=lambda r:-r[1][i])[:8]} for i in (0,1)]))
    fine=np.arange(-600,601)/5
    valid,visible,tr,te=residuals(p,track,site,retained,fine)
    lp=np.array([prior(index,fine) for index in valid]);lp=np.where(visible,lp,-np.inf)
    # Visibility is a likelihood constraint, not renormalized candidate by candidate.
    positions,_,pv=propagate_candidate_states(p.catalogue,valid,p.start_utc_ns,phase_times,fine)
    assert np.array_equal(valid,pv)
    receiver,_,axis=T.site_vectors(site);dr=positions-receiver;unit=dr/np.linalg.norm(dr,axis=-1)[...,None]
    data=dict(indices=valid,candidate_ids=np.asarray(p.catalogue.satellite_numbers)[valid],taus=fine,logprior=lp,train_residual=tr,held_residual=te,projection=unit@axis,coarse_candidates=np.array([r[0] for r in pool]),coarse_scores=np.array([r[1] for r in pool]))
    np.savez_compressed(path,**data)
    print(p.session_id,'fold',fold,'bank',track.track_id[:19],len(valid),'candidates',tr.shape[-1],te.shape[-1],'blocks',flush=True)
    return data

def options(bank,sigma,n):
    tr=T.constant_log_evidence(bank['train_residual'],sigma)
    joint=T.constant_log_evidence(np.concatenate([bank['train_residual'],bank['held_residual']],axis=-1),sigma)
    marginal=logsumexp(tr+bank['logprior'],axis=-1);chosen=np.argsort(-marginal)[:4];out=[]
    for i in chosen:
        lp=tr[i]+bank['logprior'][i];lp-=logsumexp(lp);ix=quantile_indices(lp,n)
        jx=quantile_indices(joint[i]+bank['logprior'][i],n)
        out.append(dict(candidate_id=str(bank['candidate_ids'][i]),train=float(marginal[i]),held=float(logsumexp(joint[i]+bank['logprior'][i])-marginal[i]),sample_held=joint[i,ix]-tr[i,ix],projection=bank['projection'][i,ix],joint_projection=bank['projection'][i,jx],sample_tau=bank['taus'][ix],tau_mean=float(np.exp(lp)@bank['taus']),tau_sd=float(np.sqrt(np.exp(lp)@(bank['taus']-(np.exp(lp)@bank['taus']))**2))))
    return out

def evaluate(left,right,y,train,f0,f1,kappa,n_baseline=81):
    baseline=np.linspace(-2,2,n_baseline);lp=[];held=[];phase_train=[];phase_joint=[];coupled=[];stable_coupled=[];pairs=[]
    for a in left:
        for b in right:
            # Nuisance draws are equal-mass deterministic posterior quantiles,
            # crossed independently for the two tracks and the baseline grid.
            geom=2*np.pi*(b['projection'][None,:,:]*f1-a['projection'][:,None,:]*f0)/C
            model=baseline[:,None,None,None]*geom[None,:,:,:]
            tr=phase_evidence(y[train],model[...,train],np.full(train.sum(),kappa))
            full=phase_evidence(y,model,np.full(len(y),kappa))
            norm=np.log(tr.size)
            phase_train.append(float(logsumexp(tr)-norm));phase_joint.append(float(logsumexp(full)-norm))
            ch=a['sample_held'][:,None]+b['sample_held'][None,:]
            # Same timing posterior must be updated by phase; preserve coupling
            # instead of multiplying separately marginalized held CFO terms.
            coupled.append(float(logsumexp(tr+ch[None,:,:])-norm))
            # Evaluate the numerator integral using its exact CFO-conditioned
            # timing posterior. Held CFO is used only in scoring that joint
            # density; phase training weights and identity updates remain train-only.
            jointgeom=2*np.pi*(b['joint_projection'][None,:,:]*f1-a['joint_projection'][:,None,:]*f0)/C
            jointmodel=baseline[:,None,None,None]*jointgeom[None,:,:,:]
            jointtr=phase_evidence(y[train],jointmodel[...,train],np.full(train.sum(),kappa))
            stable_coupled.append(float(logsumexp(jointtr)-norm+a['held']+b['held']))
            lp.append(a['train']+b['train']);held.append(a['held']+b['held'])
            pairs.append([a['candidate_id'],b['candidate_id']])
    lp=np.array(lp);lp-=logsumexp(lp);held=np.array(held);phase_train=np.array(phase_train);phase_joint=np.array(phase_joint)
    posterior=lp+phase_train;posterior-=logsumexp(posterior)
    before=float(logsumexp(lp+held))
    # Quantile error is measured explicitly against exact timing marginalization.
    sampleheld=np.array([logsumexp(a['sample_held'][:,None]+b['sample_held'][None,:])-np.log(len(a['sample_held'])*len(b['sample_held'])) for a in left for b in right])
    approximate_before=float(logsumexp(lp+sampleheld))
    after=float(logsumexp(lp+np.array(coupled))-logsumexp(lp+phase_train))
    stable_after=float(logsumexp(lp+np.array(stable_coupled))-logsumexp(lp+phase_train))
    identity_only=float(logsumexp(posterior+held))
    phase_held=float(logsumexp(lp+phase_joint)-logsumexp(lp+phase_train))
    constant=float(phase_evidence(y,np.zeros(len(y)),np.full(len(y),kappa))-phase_evidence(y[train],np.zeros(train.sum()),np.full(train.sum(),kappa)))
    return dict(kappa=kappa,pairs=pairs,cfo_probabilities=np.exp(lp).tolist(),phase_updated_probabilities=np.exp(posterior).tolist(),top_before=pairs[int(np.argmax(lp))],top_after=pairs[int(np.argmax(posterior))],maximum_probability_change=float(np.max(abs(np.exp(posterior)-np.exp(lp)))),exact_cfo_held=before,quantile_cfo_held=approximate_before,quantile_error_nats=approximate_before-before,cfo_held_after_phase=stable_after,cfo_gain=stable_after-before,train_quadrature_cfo_gain=after-approximate_before,identity_reweight_only_gain=identity_only-before,phase_held_vs_uniform=phase_held,constant_phase_held_vs_uniform=constant,phase_gain_vs_constant=phase_held-constant)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,choices=[0,1],required=True);parser.add_argument('--fold',type=int,choices=[0,1],required=True);parser.add_argument('--quantiles',type=int,default=17);parser.add_argument('--baseline-points',type=int,default=81);parser.add_argument('--kappa',type=float);args=parser.parse_args()
    OUT.mkdir(exist_ok=True);started=time.monotonic()
    plan=json.loads((HERE/'long-overlap/plan.json').read_text());scan=[s for s in plan['scans'] if s['selected']][args.scan];sid=scan['session_id']
    audit=next(s for s in json.loads((HERE/'catalogue-input-audit.json').read_text())['scans'] if s['session_id']==sid);site=audit['sites']['reference'];cal=json.loads((HERE/'timing-calibration.json').read_text())
    protocol=dict(scan=sid,fold=args.fold,quantiles=args.quantiles,site=site,coarse_grid_s=[-120,120,10],fine_grid_s=[-120,120,.2],cfo_sigma_hz=[100,200],selection='Union top8 full-catalogue coarse timing proposals at each CFO sigma; refine then top4 each track using train only',phase_kappas=[.5,1,2],baseline_m=[-2,2,81],partition_seed=20260930,phase_support='All selected dwell means, no quality gate',timing_prior_sha256=hashlib.sha256((HERE/'timing-calibration.json').read_bytes()).hexdigest(),plan_sha256=hashlib.sha256((HERE/'long-overlap/plan.json').read_bytes()).hexdigest(),meaning='Conditional reference-site exploratory retrospective evaluation; not identity ground truth')
    stem=f'{sid}-f{args.fold}-q{args.quantiles}'
    if args.baseline_points!=81:stem+=f'-b{args.baseline_points}'
    protocol['baseline_m'][-1]=args.baseline_points
    if args.kappa is not None:protocol['phase_kappas']=[args.kappa]
    (OUT/(stem+'-protocol.json')).write_text(json.dumps(protocol,indent=2)+'\n')
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
        source=store.load(sid)
    finally:store.close()
    assert p.evidence_sha256==audit['evidence_sha256'] and p.snapshot_digest==audit['snapshot_digest']
    assert cal['latest_history_snapshot_ns']<p.start_utc_ns
    rows=json.loads((HERE/'long-overlap'/(sid+'.json')).read_text())['rows'];obs=[]
    for v in scan['selected']:
        modes=[sorted([r for r in rows if r['visit']==v['visit'] and r['mode']==m],key=lambda r:r['start_ms']) for m in (0,1)]
        assert all(r['rx1_track_ids']==[scan['track_ids'][m]] for m in (0,1) for r in modes[m])
        assert [r['start_ms'] for r in modes[0]]==[r['start_ms'] for r in modes[1]]
        y=np.array([r['coefficients']['full']['phase_rad'] for r in modes[1]])-np.array([r['coefficients']['full']['phase_rad'] for r in modes[0]])
        obs.append(dict(visit=v['visit'],time_s=np.mean([r['utc_ns']-p.start_utc_ns for r in modes[0]])/1e9,phase=float(np.angle(np.mean(np.exp(1j*y)))),f0=modes[0][0]['rf_estimate_hz'],f1=modes[1][0]['rf_estimate_hz']))
    times=np.array([r['time_s'] for r in obs]);bins=np.unique(T.visit_bins(sid,times));rng=np.random.default_rng(protocol['partition_seed']);selected=set(map(int,rng.choice(bins,len(bins)//2,replace=False)))
    T.FOLD=args.fold;T.PARTITION_OVERRIDES[sid]={int(b):(int(b) in selected)^bool(args.fold) for b in bins};train=T.partition(sid,times)
    production_ids={t.track_id for t in p.tracks}
    projected=project_scanner_candidates(source);byid={c.candidate_id:c for c in projected}
    # Preserve the frozen acquisition plan's exact digest representation: 3
    # versus 3.0 is numerically equivalent but currently changes track IDs.
    trajectory=reconstruct_persistent_hop_trajectories(projected,config=PersistentHopTrajectoryConfig(minimum_span_s=3,minimum_support=6))
    production_trajectory=reconstruct_persistent_hop_trajectories(projected,config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
    tracks={};membership=[];source_sets=[]
    for tid in scan['track_ids']:
        raw=next(t for t in trajectory.tracklets if t.tracklet_id==tid)
        points=sorted(raw.points,key=lambda r:byid[r.candidate_id].support_center_utc_ns)
        tt=np.array([(byid[r.candidate_id].support_center_utc_ns-p.start_utc_ns)/1e9 for r in points])
        tracks[tid]=AdaptiveTrackInput(tid,tuple(r.candidate_id for r in points),tt,np.array([r.normalized_dealiased_cfo_hz for r in points]),T.partition(sid,tt))
        sources={byid[r.candidate_id].source_group_id for r in points};source_sets.append(sources)
        same=[t.tracklet_id for t in production_trajectory.tracklets if {(r.candidate_id,r.relative_alias_index) for r in t.points}=={(r.candidate_id,r.relative_alias_index) for r in raw.points}]
        for equivalent in same:
            accepted=next((t for t in p.tracks if t.track_id==equivalent),None)
            if accepted is not None:
                assert np.allclose(accepted.times_s,tt,rtol=0,atol=1e-9)
                assert np.allclose(accepted.measured_hz,tracks[tid].measured_hz,rtol=0,atol=1e-8)
        membership.append(dict(track_id=tid,in_production_input=tid in production_ids,equivalent_production_track_ids=same,equivalent_in_production_input=[t for t in same if t in production_ids],points=len(points),source_groups=len(sources),times_s=tt.tolist(),measured_hz=tracks[tid].measured_hz.tolist(),candidate_ids=list(tracks[tid].observation_ids)))
    equivalent_sets=[set(r['equivalent_production_track_ids']) for r in membership]
    joint_hypotheses=sum(all(ids.intersection(h.tracklet_ids) for ids in equivalent_sets) for h in production_trajectory.hypotheses)
    membership_audit=dict(tracks=membership,shared_probe_source_groups=len(source_sets[0]&source_sets[1]),joint_production_hypotheses=joint_hypotheses,meaning='Exact candidate-and-alias joins reconcile integer/float config digest IDs; equivalent production times and CFOs checked. Simultaneous modes can share probe groups that production hypotheses treat as exclusive.')
    (OUT/(stem+'-membership.json')).write_text(json.dumps(membership_audit,indent=2)+'\n')
    banks=[make_bank(p,tracks[tid],site,times,cal,args.fold) for tid in scan['track_ids']]
    experiments=[];summaries=[]
    for sigma in protocol['cfo_sigma_hz']:
        a,b=[options(bank,sigma,args.quantiles) for bank in banks]
        summaries.append(dict(sigma=sigma,left=[{k:v for k,v in r.items() if k not in ('projection','joint_projection','sample_held','sample_tau')} for r in a],right=[{k:v for k,v in r.items() if k not in ('projection','joint_projection','sample_held','sample_tau')} for r in b]))
        for k in protocol['phase_kappas']:
            result=evaluate(a,b,np.array([r['phase'] for r in obs]),train,np.array([r['f0'] for r in obs]),np.array([r['f1'] for r in obs]),k,n_baseline=args.baseline_points);result['cfo_sigma_hz']=sigma;experiments.append(result)
            print(sid,args.fold,sigma,k,'CFO gain',result['cfo_gain'],'phase gain',result['phase_gain_vs_constant'],'quadrature error',result['quantile_error_nats'],flush=True)
    out=dict(protocol=protocol,evidence_sha256=p.evidence_sha256,snapshot_digest=p.snapshot_digest,track_ids=scan['track_ids'],membership=membership_audit,observations=obs,phase_training_mask=train.tolist(),candidates=summaries,experiments=experiments,elapsed_s=time.monotonic()-started)
    (OUT/(stem+'.json')).write_text(json.dumps(out,indent=2)+'\n')

if __name__=='__main__':main()
