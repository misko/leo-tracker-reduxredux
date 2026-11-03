import os
if os.environ.get('THREE_TRACK_COLD_ROOT'):
    exec(open('/tmp/three_track_cold_context.py').read())
else:
    exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
import sys,time
from dataclasses import replace
from frozen_band_bias_joint import FrozenBandBiasJoint
from leo.analysis.shared_scan_model import SharedScanObjective,CountedObjective
from leo.analysis.channel_group_calibration import fit_group_calibration
from leo.analysis.sequential_group_calibration import SequentialShift
from leo.analysis.hard60_bounded_fit import _Problem
from leo.application.shared_fast_position import plain

fold=sys.argv[1];arm=sys.argv[2]
variant=sys.argv[3] if len(sys.argv)>3 else 'band_bias'
pass_number=int(sys.argv[4]) if len(sys.argv)>4 else 1
assert pass_number in [1,2]
assert variant in ['band_bias','no_bias']
assert fold in ['early_to_late','late_to_early'] and arm in ['fitted-c','zero-c']
if os.environ.get('THREE_TRACK_COLD_ROOT'):
    record=dict(fit=dict(vector=v,nuisance=n),audit=cold_audit)
else:record=json.loads((root/'excluded_calibration_fitted-c_from_zero.json').read_text())
assert record['audit']['accepted']
reference_v=np.array(record['fit']['vector']);reference_n=np.array(record['fit']['nuisance'])
if not os.environ.get('THREE_TRACK_COLD_ROOT'):
    high=stages[new['selection']['source']+'-high']['result']['fit'];shift=SequentialShift(tuple(high['group_receivers']),np.array(high['group_offsets_hz']))
if os.environ.get('THREE_TRACK_COLD_ROOT'):
    source_suffix='_source_'+os.environ['THREE_TRACK_COLD_SOURCE'] if os.environ.get('THREE_TRACK_COLD_SOURCE') else ''
    search=json.loads((root/('cold_candidate_temporal_transfer'+source_suffix+'.json')).read_text())
    proposals=dict(results=[dict(track=r['track'],split=r['split'],records=[dict(satellite=r['ranked'][0]['satellite'],timing_s=r['ranked'][0]['timing_s'],passes_predeclared_gate=r['ranked'][0]['training_rms_hz']<=375 and r['ranked'][1]['training_objective']-r['ranked'][0]['training_objective']>=20)]) for r in search['results']])
else:proposals=json.loads((root/'generic_recovery_target_excluded_controls.json').read_text())
reference_eval,reference_details=model.evaluate_details(reference_v,reference_n)
reference_best=reference_eval[3].responsibilities.argmax(axis=1)
reference_associated=reference_eval[3].responsibilities[np.arange(len(reference_best)),reference_best]>reference_eval[3].clutter_probability
reference_shifts=reference_v[7]+zero_sum_basis(len(nums))@reference_v[8:]
ref_pred,_,_,ref_derivative=predict_orbits(bank,obs,prior,reference_v[:2],reference_shifts)
ref_correction=model.original.correction(reference_v,reference_n[:model.clock_count])
mask=np.ones(len(obs.times_s),bool);target_sets=[];hypotheses=[];bias_indices=[];basis=[];amp=[];start_shifts=reference_shifts.copy()
for name,path in [('early_ch2','/tmp/rx1-ch2-50-75'),('ch4','/tmp/rx1-ch4-40-100'),('late_ch2','/tmp/rx1-ch2-170-190')]:
    rows=np.load(path+'/arrays.npz')['rows']
    if name=='early_ch2':rows=rows[np.isin(obs.times_s[rows],json.loads(Path(path+'/track_summary.json').read_text())['times'])]
    early=obs.times_s[rows]<=np.median(obs.times_s[rows]);train=early if fold=='early_to_late' else ~early
    target_sets.append((name,rows,train));mask[rows[~train]]=False
    proposal=next(r['records'][0] for r in proposals['results'] if r['track']==name and r['split']==fold)
    assert proposal['passes_predeclared_gate']
    satellite=proposal['satellite'];k=nums.index(satellite)
    upper=np.flatnonzero(reference_associated&(reference_best==k)&(obs.channel>=5))
    strong_upper=len(upper)>=10 and np.ptp(obs.times_s[upper])>=10
    hypotheses.append(dict(track=name,satellite=satellite,training_count=int(train.sum()),test_count=int((~train).sum()),background_upper_support_count=len(upper),background_upper_span_s=float(np.ptp(obs.times_s[upper])) if len(upper) else 0.,mode='lower_band_frequency_basis' if strong_upper else 'shared_timing_initialization'))
    if strong_upper and variant=='band_bias':
        column=ref_derivative[:,k]*(obs.channel<=4)
        rr=circular(obs.measured_hz[rows[train]]-ref_correction[rows[train]]-ref_pred[rows[train],k])
        amplitude=float(column[rows[train]]@rr/(column[rows[train]]@column[rows[train]]))
        bias_indices.append(k);basis.append(column);amp.append(amplitude)
    elif not strong_upper:start_shifts[k]=proposal['timing_s']
full_basis=np.column_stack(basis) if basis else np.zeros((len(obs.times_s),0))
base=SharedScanObjective(model.original,shift,mask=mask);base.score=replace(base.score,relative_sigma_s=.5)
joint=FrozenBandBiasJoint(base,full_basis,bias_indices)
start=reference_v.copy();start[7]=start_shifts.mean();start[8:]=zero_sum_basis(len(nums)).T@(start_shifts-start_shifts.mean())
n0=np.r_[reference_n,np.clip(amp,-1.99,1.99)]
variant_suffix='' if variant=='band_bias' else '_no_bias'
if os.environ.get('THREE_TRACK_START_FROM_BAND'):
    assert variant=='no_bias'
    bridge=json.loads((root/f'generic_joint_{fold}_{arm}.json').read_text());assert bridge['audit']['accepted']
    start=np.array(bridge['fit']['vector']);n0=np.array(bridge['fit']['nuisance'])[:joint.base_count]
    variant_suffix='_no_bias_from_band'
if pass_number==2:
    previous=json.loads((root/f'generic_joint_{fold}_{arm}{variant_suffix}.json').read_text())
    start=np.array(previous['fit']['vector']);n0=np.array(previous['fit']['nuisance'])

# Verify analytic physical, clock, detectability, and band-bias derivatives.
e=joint.evaluate_joint(start,n0);checks=[]
for kind,indices,steps in [('physical',[0,2,6,7,8],[1e-4,.01,.01,3e-6,1e-5]),('nuisance',[0,len(reference_n)-1,len(n0)-1],[.01,1e-5,1e-5])]:
    for index,step in zip(indices,steps):
        plus=start.copy() if kind=='physical' else n0.copy();minus=plus.copy();plus[index]+=step;minus[index]-=step
        hi=joint.evaluate_joint(plus,n0)[0] if kind=='physical' else joint.evaluate_joint(start,plus)[0]
        lo=joint.evaluate_joint(minus,n0)[0] if kind=='physical' else joint.evaluate_joint(start,minus)[0]
        fd=(hi-lo)/(2*step);analytic=e[1 if kind=='physical' else 2][index];error=float(abs(fd-analytic)/max(1,abs(fd),abs(analytic)))
        checks.append(dict(kind=kind,index=index,analytic=float(analytic),finite_difference=float(fd),relative_error=error))
assert max(x['relative_error'] for x in checks)<5e-4,checks

audit_text=Path('/tmp/three_track_excluded_calibration_fit.py').read_text().split('def audit(')[1].split("for arm in ['fitted-c','zero-c']:")[0]
exec(compile('def audit('+audit_text,'independent_joint_audit','exec'))

def full_summary(vv,nn):
    all_base=SharedScanObjective(model.original,shift);all_base.score=base.score
    all_model=FrozenBandBiasJoint(all_base,full_basis,bias_indices)
    ee,dd=all_model.evaluate_details(vv,nn);terms=ee[3];best=terms.responsibilities.argmax(axis=1);associated=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
    result=dict(all_associated=int(associated.sum()),background_associated=int(np.sum(associated[np.setdiff1d(np.arange(len(obs.times_s)),np.concatenate([r for _,r,_ in target_sets]))])),withheld_nll=float(np.sum(dd['row_nll'][~mask])),band_frequency_amplitude_s=nn[joint.base_count:].tolist(),tracks=[])
    for (name,rows,train),proposal in zip(target_sets,hypotheses):
        k=nums.index(proposal['satellite']);test=rows[~train];rr=terms.residual_hz[test,k]
        result['tracks'].append(dict(track=name,satellite=proposal['satellite'],test_count=len(test),test_rms_hz=float(np.sqrt(np.mean(rr**2))),test_associated=int(associated[test].sum()),test_intended_matches=int(np.sum(associated[test]&(best[test]==k))),test_within_375hz=int(np.sum(abs(rr)<=375)),upper_matches=int(np.sum(associated&(best==k)&(obs.channel>=5))),test_times_s=obs.times_s[test].tolist(),test_residuals_hz=rr.tolist()))
    result['upper_bias_satellite_matches']={str(nums[k]):int(np.sum(associated&(best==k)&(obs.channel>=5))) for k in bias_indices}
    return result

before=full_summary(start,n0)
counted=CountedObjective(joint,seconds=65,maximum=4999);options=dict(arm=arm,seconds=60.,iterations=600,local_center=reference_v[:2],local_radius_km=25.)
fit=fit_group_calibration(counted,start,n0,**options);counted.maximum=5000;checked=audit(counted,fit,options,arm)
after=full_summary(np.array(fit['vector']),np.array(fit['nuisance']))
# Rebuild the scoring adapter with changed held-out measurements.
changed=object.__new__(type(model.original));changed.__dict__.update(model.original.__dict__)
changed.observations=replace(obs,measured_hz=obs.measured_hz+np.where(mask,0.,1234567.))
altered_base=SharedScanObjective(changed,shift,mask=mask);altered_base.score=base.score
altered=FrozenBandBiasJoint(altered_base,full_basis,bias_indices)
aa=joint.evaluate_joint(np.array(fit['vector']),np.array(fit['nuisance']));bb=altered.evaluate_joint(np.array(fit['vector']),np.array(fit['nuisance']))
invariance=max(float(np.max(abs(np.asarray(x)-np.asarray(y)),initial=0)) for x,y in zip(aa[:3],bb[:3]));assert invariance==0
qualification='Research joint fit. Track proposals and band coefficients use only the declared training halves; withheld values are excluded from likelihood. Frozen derivative frequency basis applies to all lower-band observations of automatically selected satellites, across both receivers, with a 0.5s coefficient prior and +/-2s coefficient bound; no timestamps changed.'
qualification+=(' Background discovery, calibration and initialization are cold-trained on the declared fold.' if os.environ.get('THREE_TRACK_COLD_ROOT') else ' Conditional background bank/high-band contrast/saved warm start remain.')
result=dict(qualification=qualification,fold=fold,arm=arm,variant=variant,pass_number=pass_number,initialized_from_band_fit=bool(os.environ.get('THREE_TRACK_START_FROM_BAND')),training_count=int(mask.sum()),withheld_rows=np.flatnonzero(~mask).tolist(),hypotheses=hypotheses,derivative_checks=checks,held_measurement_invariance_error=invariance,before=before,after=after,fit=plain(fit),audit=checked,objective_calls=counted.calls,elapsed_seconds=time.monotonic()-counted.begun)
suffix=variant_suffix+('_pass2' if pass_number==2 else '')
(root/f'generic_joint_{fold}_{arm}{suffix}.json').write_text(json.dumps(result,indent=2)+'\n')
compact={k:result[k] for k in ['fold','arm','variant','audit','elapsed_seconds']}
compact['after']={k:val for k,val in after.items() if k!='tracks'}
compact['after']['tracks']=[{k:val for k,val in row.items() if k not in ['test_times_s','test_residuals_hz']} for row in after['tracks']]
print(json.dumps(compact,indent=2),flush=True)
