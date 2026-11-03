"""Fit or independently replay the cold grouped-track experiment."""
import argparse,hashlib,json,sys,time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'three-track-recovery-replay-20261016'))
from replay import replay
from leo.application.channel_group_refinement import objective
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import zero_sum_basis,circular
from leo.analysis.hard60_score import predict_orbits

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input',required=True,type=Path)
parser.add_argument('--tle-root',required=True,type=Path)
parser.add_argument('--fold',required=True,choices=('early_to_late','late_to_early'))
parser.add_argument('--variant',required=True,choices=('coherent','independent','acquisition'))
parser.add_argument('--arm',required=True,choices=('fitted-c','zero-c'))
parser.add_argument('--output',required=True,type=Path)
parser.add_argument('--retain-discovery',action='store_true')
parser.add_argument('--training-timing-seed',action='store_true')
parser.add_argument('--proposal-closure',action='store_true')
parser.add_argument('--pass-number',type=int,choices=(1,2),default=1)
parser.add_argument('--resume',type=Path)
parser.add_argument('--audit-checkpoint',type=Path)
parser.add_argument('--polish-checkpoint',type=Path)
args=parser.parse_args()
if args.output.exists():raise FileExistsError('Output exists; use a new attempt filename')
if args.resume and args.audit_checkpoint:raise ValueError('Resume and replay are mutually exclusive')
if args.polish_checkpoint and (args.resume or args.audit_checkpoint):raise ValueError('Polish is a separate checkpoint operation')
if args.proposal_closure and not (args.retain_discovery and args.training_timing_seed):raise ValueError('Proposal closure requires discovery candidates and training timing proposals')
context=replay(args,return_context=True)
obs=context.observations;cold_obs=context.training_observations
bank=context.bank;prior=context.prior;nodes=context.clock_nodes
fit=context.training_fit;shift=context.shift;derivation=context.derivation
nums=context.candidate_numbers;stages=context.stages
cat=context.catalogue;lookup=context.catalogue_lookup;origin=context.origin_utc_ns
from dataclasses import replace
from coherent_track_model import CoherentTrackModel,coherent_density
from leo.analysis.shared_scan_model import SmoothVisibilityModel,CountedObjective,density,elevation_geometry,horizon_weight
from leo.analysis.channel_group_calibration import fit_group_calibration
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.hard60_bounded_fit import _Problem
from leo.application.shared_fast_position import plain
from leo.analysis.regional_position_bootstrap import observation_subset
from acquisition_clutter import AcquisitionClutterModel,covariate,conditioned_density

variant,arm=args.variant,args.arm
pass_number=args.pass_number
retained=args.retain_discovery
old_nums=nums.copy();old_bank=bank;old_v=np.array(fit['vector']);old_nuisance=np.array(fit['nuisance'])
if retained:
    nums=sorted({int(num) for key,row in stages.items() if key.startswith('discovery-point:') for num in row['catalogue_numbers']}|set(old_nums))
    bank,_=build_regional_bank(cat,[lookup[num] for num in nums],origin,cold_obs,prior)
    order={int(num):i for i,num in enumerate(bank.numbers)};bank=bank.select([order[num] for num in nums])
original=objective(SimpleNamespace(observations=cold_obs),bank,prior,nodes)
location={key:i for i,key in enumerate(cold_obs.window_ids)}
groups=[np.array([location[obs.window_ids[r]] for r in target['training_rows']]) for target in derivation['targets']]
acquisition_x,acquisition_meta=(covariate(cold_obs.margin,np.ones(len(cold_obs.times_s),bool))
    if variant=='acquisition' else (None,None))
def observation_model(base):
    if variant=='coherent':return CoherentTrackModel(base,groups)
    if variant=='acquisition':return AcquisitionClutterModel(base,acquisition_x)
    return base
mask=np.ones(len(cold_obs.times_s),bool)
if variant=='coherent':mask[np.concatenate(groups)]=False
base=SmoothVisibilityModel(original,mask);base.score=replace(base.score,relative_sigma_s=.5)
training=observation_model(base)
seed_v=old_v.copy();seed_n=old_nuisance.copy()
if retained:
    old_total=old_v[7]+zero_sum_basis(len(old_nums))@old_v[8:]
    new_total=np.zeros(len(nums))
    for number,total_s in zip(old_nums,old_total):new_total[nums.index(number)]=total_s
    seed_v=np.r_[old_v[:7],new_total.mean(),zero_sum_basis(len(nums)).T@(new_total-new_total.mean())]
    seed_n=np.r_[old_nuisance[:original.clock_count],np.zeros(base.observation_parameter_count)]
for rx,fraction,offset in zip(original.frame.receivers,original.frame.high_fractions,shift.offsets_hz,strict=True):seed_v[2+2*rx]+=fraction*offset
seed_n=np.r_[seed_n[:original.clock_count],shift.offsets_hz,seed_n[original.clock_count:]]
total=np.clip(seed_v[7]+zero_sum_basis(len(nums))@seed_v[8:],-3,3)
timing_proposals=[]
if args.training_timing_seed:
    correction=original.correction(seed_v,seed_n[:base.base_nuisance_count])
    for target,rows in zip(derivation['targets'],groups):
        subset=observation_subset(cold_obs,rows)
        best_score=np.full(len(nums),np.inf);best_timing=np.zeros(len(nums))
        for tau in np.linspace(-5,5,201):
            prediction,visible,_,_=predict_orbits(bank,subset,prior,seed_v[:2],np.full(len(nums),tau),derivatives=False)
            residual=circular(subset.measured_hz[:,None]-correction[rows,None]-prediction)
            score=np.sum((residual/125)**2,axis=0)+(tau/2)**2
            score[~visible.all(axis=0)]=np.inf
            take=score<best_score;best_score[take]=score[take];best_timing[take]=tau
        k=int(np.argmin(best_score))
        timing_proposals.append(dict(track=target['track'],satellite=nums[k],timing_s=float(best_timing[k]),training_score=float(best_score[k]),count=len(rows)))
    for number in {p['satellite'] for p in timing_proposals}:
        proposals=[p for p in timing_proposals if p['satellite']==number]
        total[nums.index(number)]=sum(p['count']*p['timing_s'] for p in proposals)/sum(p['count'] for p in proposals)
seed_v[7]=total.mean();seed_v[8:]=zero_sum_basis(len(nums)).T@(total-total.mean())
proposal_pool_count=len(nums);q_seed_error=0.
if args.proposal_closure:
    from leo.analysis.research.model_b_conditional_cfo import detection_probabilities
    selected=sorted(set(old_nums)|{p['satellite'] for p in timing_proposals})
    selected_indices=[nums.index(number) for number in selected]
    total=total[selected_indices];bank=bank.select(selected_indices);nums=selected
    original=objective(SimpleNamespace(observations=cold_obs),bank,prior,nodes)
    base=SmoothVisibilityModel(original,mask);base.score=replace(base.score,relative_sigma_s=.5)
    training=observation_model(base)
    seed_v=np.r_[seed_v[:7],total.mean(),zero_sum_basis(len(nums)).T@(total-total.mean())]
    old_tail=old_nuisance[original.clock_count:]
    if nums==old_nums:new_tail=old_tail.copy()
    else:
        old_q=detection_probabilities(zero_sum_basis(len(old_nums)),old_tail,base.score.detection_budget)[0]
        target_q=np.full(len(nums),base.score.detection_budget/len(nums))
        for number,probability in zip(old_nums,old_q):target_q[nums.index(number)]=probability*len(old_nums)/len(nums)
        logits=np.log(target_q/(1-target_q))
        new_tail=np.clip(zero_sum_basis(len(nums)).T@logits,-1.99,1.99)
        actual_q=detection_probabilities(zero_sum_basis(len(nums)),new_tail,base.score.detection_budget)[0]
        q_seed_error=float(np.max(abs(actual_q-target_q)))
    seed_n=np.r_[seed_n[:base.base_nuisance_count],new_tail]
if variant=='acquisition':seed_n=np.r_[seed_n,0.]
if pass_number==2:
    if not args.resume:raise ValueError('Second pass requires an explicit resume checkpoint')
    previous=json.loads(args.resume.read_text())
    assert previous['variant']==variant and previous['arm']==arm and previous['derived_input_sha256']==derivation['derived_input_sha256'] and previous['candidate_numbers']==nums
    assert previous.get('training_timing_seed',False)==args.training_timing_seed
    assert previous.get('proposal_closure',False)==args.proposal_closure
    seed_v=np.array(previous['fit']['vector']);seed_n=np.array(previous['fit']['nuisance'])

evaluation=training.evaluate_joint(seed_v,seed_n);checks=[]
nuisance_indices=[0,original.clock_count,original.clock_count+1,len(seed_n)-1]
nuisance_steps=[.01,.01,.01,1e-5]
if variant=='acquisition':
    nuisance_indices.append(len(base.initial_nuisance)-1);nuisance_steps.append(1e-5)
    parent=base.evaluate_joint(seed_v,seed_n[:-1]);child=training.evaluate_joint(seed_v,seed_n)
    if not (args.resume or args.audit_checkpoint or args.polish_checkpoint):
        assert abs(parent[0]-child[0])<1e-7 and np.max(abs(parent[1]-child[1]))<1e-7
for kind,indices,steps in [('physical',[0,1,2,6,7,8],[1e-4,1e-4,.01,.01,3e-6,1e-5]),('nuisance',nuisance_indices,nuisance_steps)]:
    for index,step in zip(indices,steps):
        plus=(seed_v if kind=='physical' else seed_n).copy();minus=plus.copy();plus[index]+=step;minus[index]-=step
        hi=training.evaluate_joint(plus,seed_n)[0] if kind=='physical' else training.evaluate_joint(seed_v,plus)[0]
        lo=training.evaluate_joint(minus,seed_n)[0] if kind=='physical' else training.evaluate_joint(seed_v,minus)[0]
        fd=(hi-lo)/(2*step);analytic=evaluation[1 if kind=='physical' else 2][index]
        error=float(abs(fd-analytic)/max(1,abs(fd),abs(analytic)))
        checks.append(dict(kind=kind,index=index,relative_error=error));assert error<5e-4,checks

counted=CountedObjective(training,seconds=65,maximum=4999)
options=dict(arm=arm,seconds=60.,iterations=600,local_center=np.zeros(2),local_radius_km=prior.radius_km)
if args.audit_checkpoint or args.polish_checkpoint:
    authority=json.loads((args.audit_checkpoint or args.polish_checkpoint).read_text())
    assert authority['variant']==variant and authority['arm']==arm and authority['candidate_numbers']==nums and authority['derived_input_sha256']==derivation['derived_input_sha256']
    assert authority.get('training_timing_seed',False)==args.training_timing_seed and authority.get('proposal_closure',False)==args.proposal_closure
    fitted=authority['fit']
else:fitted=fit_group_calibration(counted,seed_v,seed_n,**options)
polish_audit=None
if args.polish_checkpoint:
    from strict_polish import polish
    fitted,polish_audit=polish(training,fitted,arm=arm,local_center=options['local_center'],local_radius_km=options['local_radius_km'])
counted.maximum=5000
vv=np.array(fitted['vector']);nn=np.array(fitted['nuisance'])
problem=_Problem(training,vv,rf_arm=arm,local_center=options['local_center'],local_radius_km=options['local_radius_km'],slope_half_width_hz_s=60)
limits=np.r_[np.full(training.clock_count,2000.),training.group_limits];scales=np.r_[np.full(training.clock_count,50.),training.group_scales]
value,gradient,extra,terms=counted.evaluate_joint(vv,nn);projected=scales*extra
projected[(nn<=-limits+1e-7)&(projected>=0)]=0;projected[(nn>=limits-1e-7)&(projected<=0)]=0
kkt=max(problem.stationarity(vv,gradient),float(np.max(abs(projected),initial=0)))
closure=max(abs(kkt-fitted['stationarity']),abs(value-fitted['objective']),abs(terms.nll-fitted['likelihood_nll']))
accepted=bool(fitted['converged'] and problem.feasible(vv) and np.all(abs(nn)<=limits+1e-7) and kkt<=.001 and closure<=1e-7)
audit=dict(accepted=accepted,stationarity=float(kkt),objective=float(value),nll=float(terms.nll),replay_maximum_error=float(closure))
# Assign each supplied group using training only; no candidate or timing is selected on test data.
train_shift=vv[7]+zero_sum_basis(len(nums))@vv[8:]
train_correction=original.correction(vv,nn[:base.base_nuisance_count])
records=[]
calibration=freeze_group_calibration(original,dict(vector=vv,nuisance=nn[:base.base_nuisance_count]))
all_correction=calibration.predict(obs.times_s,obs.rf_hz,obs.receiver,obs.channel>=5)
pred_all=predict_orbits(bank,obs,prior,vv[:2],train_shift,derivatives=False)[0]+all_correction[:,None]
sine=elevation_geometry(bank,obs,prior,vv[:2],train_shift)[0];weight=horizon_weight(sine,base.visibility_width)[0]
q=base.hyperparameters(nn[base.base_nuisance_count:len(base.initial_nuisance)])[2]
if variant=='acquisition':
    all_x=(np.log(obs.margin)-acquisition_meta['center'])/acquisition_meta['scale']
    all_terms,_=conditioned_density(obs.measured_hz,pred_all,weight,np.full(len(obs.times_s),125.),q,base.score,nn[-1]*all_x)
else:all_terms,_=density(obs.measured_hz,pred_all,weight,np.full(len(obs.times_s),125.),q,base.score)
best=all_terms.responsibilities.argmax(axis=1);associated=all_terms.responsibilities[np.arange(len(best)),best]>all_terms.clutter_probability
for target,rows in zip(derivation['targets'],groups):
    subset=observation_subset(cold_obs,rows)
    prediction=predict_orbits(bank,subset,prior,vv[:2],train_shift,derivatives=False)[0]+train_correction[rows,None]
    visible=horizon_weight(elevation_geometry(bank,subset,prior,vv[:2],train_shift)[0],base.visibility_width)[0]
    group=coherent_density(subset.measured_hz,prediction,visible);k=int(group[1].argmax())
    test=np.array(target['test_rows']);rr=all_terms.residual_hz[test,k]
    records.append(dict(track=target['track'],satellite=nums[k],training_count=len(rows),test_count=len(test),training_identity_probability=float(group[1][k]),training_rms_hz=float(np.sqrt(np.mean(group[4][:,k]**2))),test_rms_hz=float(np.sqrt(np.mean(rr**2))),test_intended_point_matches=int(np.sum(associated[test]&(best[test]==k))),test_within_375hz=int(np.sum(abs(rr)<=375)),test_residuals_hz=rr.tolist(),training_selected_above_horizon=bool(np.all(elevation_geometry(bank,subset,prior,vv[:2],train_shift)[0][:,k]>0))))
result=dict(qualification='Research matched fit on cold training input only. Same cold candidate bank and initial corrections, free receiver band offsets, 0.5s relative timing prior, compressed +/-3s initial satellite shifts, full original 250km spatial prior, and 60s fitter/65s total allowance in both observation models and c arms. Coherent model conditions on supplied tracks being real single-satellite tracks; no clutter alternative within these groups and no supplied satellite labels. Outer held probe groups remain absent; group identities selected on training only. Frequency predictions are not independent identity truth or position accuracy.',variant=variant,arm=arm,pass_number=pass_number,fold=derivation['fold'],derived_input_sha256=derivation['derived_input_sha256'],candidate_numbers=nums,training_count=len(cold_obs.times_s),background_count=int(mask.sum()),options=options,fit=fitted,audit=audit,derivative_checks=checks,tracks=records,all_associated=int(associated.sum()),elapsed_seconds=time.monotonic()-counted.begun,objective_calls=counted.calls)
result['retain_discovery_candidates']=retained
if retained:result['qualification']+=' Candidate bank is the union of all cold discovery-point proposals plus the original final bank. Original candidate timing seeds are carried; newly retained candidates start at zero timing; detectability starts uniformly for all candidates. No candidate identity is supplied by the inspected target results.'
suffix=('_retained' if retained else '')+('' if pass_number==1 else '_pass2')
result['replay_only']=bool(args.audit_checkpoint)
result['polish_audit']=polish_audit
if variant=='acquisition':
    result['acquisition_clutter_slope']=float(nn[-1]);result['acquisition_covariate']=acquisition_meta
    result['qualification']+=' Acquisition arm learns one bounded +/-2 log-clutter slope with unit Gaussian prior. Log-margin center and population standard deviation use the cold training observations only. Margins condition clutter odds and are not treated as calibrated detection probabilities. Test margins affect test classification only.'
result['training_timing_seed']=args.training_timing_seed
result['timing_proposals']=timing_proposals
result['proposal_closure']=args.proposal_closure
result['proposal_pool_count']=proposal_pool_count
result['detectability_seed_projection_error']=q_seed_error
if args.proposal_closure:result['qualification']+=' To bound final fitting, the final bank retains every original cold-final candidate and every training-winning coherent proposal from the discovery union. Detectability seeds preserve the original trained values, with mass shared with newly proposed candidates and explicit bounded-coordinate projection. The full discovery union is used for proposal search, not retained indiscriminately in final fitting.'
if args.training_timing_seed:result['qualification']+=' Training-only initial timing proposals use a common +/-5s grid in 0.05s steps and 2s timing prior for every candidate, under the common cold initial calibration. Proposals initialize timing only; final track identities remain latent. These proposal and calibration conditioning assumptions are shared by both c arms.'
if args.audit_checkpoint:
    result['checkpoint_sha256']=hashlib.sha256(args.audit_checkpoint.read_bytes()).hexdigest()
    for previous,current in zip(authority['tracks'],records):
        assert previous['satellite']==current['satellite'] and abs(previous['test_rms_hz']-current['test_rms_hz'])<1e-6 and previous['test_intended_point_matches']==current['test_intended_point_matches']
    assert abs(authority['audit']['objective']-audit['objective'])<1e-7
args.output.parent.mkdir(parents=True,exist_ok=True)
with args.output.open('x') as stream:stream.write(json.dumps(plain(result),indent=2)+'\n')
print(json.dumps(plain({k:result[k] for k in ['variant','arm','fold','pass_number','audit','tracks','elapsed_seconds']}),indent=2),flush=True)
