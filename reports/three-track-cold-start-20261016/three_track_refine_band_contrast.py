"""Matched cold-training test of free versus frozen receiver band contrasts."""
exec(open('/tmp/three_track_cold_context.py').read())
import sys,time
from dataclasses import replace
from leo.analysis.shared_scan_model import SmoothVisibilityModel,CountedObjective
from leo.analysis.channel_group_calibration import fit_group_calibration
from leo.analysis.hard60_bounded_fit import _Problem
from leo.application.shared_fast_position import plain

variant,arm=sys.argv[1:3];assert variant in ['free','fixed'] and arm in ['fitted-c','zero-c']
pass_number=int(os.environ.get('THREE_TRACK_BAND_PASS','1'));assert pass_number in [1,2]
training_joint=objective(SimpleNamespace(observations=cold_obs),bank,prior,nodes)
seed_v=np.array(fit['vector']);seed_n=np.array(fit['nuisance'])
if variant=='free':
    training=SmoothVisibilityModel(training_joint,np.ones(len(cold_obs.times_s),bool))
    for rx,fraction,offset in zip(training_joint.frame.receivers,training_joint.frame.high_fractions,shift.offsets_hz,strict=True):seed_v[2+2*rx]+=fraction*offset
    seed_n=np.r_[seed_n[:cold_model.clock_count],shift.offsets_hz,seed_n[cold_model.clock_count:]]
else:training=SharedScanObjective(cold_model.original,shift)
before_cold=cold_model.evaluate_joint(np.array(fit['vector']),np.array(fit['nuisance']))
before=training.evaluate_joint(seed_v,seed_n)
seed_closure=max(abs(before[0]-before_cold[0]),abs(before[3].nll-before_cold[3].nll))
assert seed_closure<1e-7,seed_closure
training.score=replace(training.score,relative_sigma_s=.5)
total=np.clip(seed_v[7]+zero_sum_basis(len(nums))@seed_v[8:],-3,3)
seed_v[7]=total.mean();seed_v[8:]=zero_sum_basis(len(nums)).T@(total-total.mean())
local_center=seed_v[:2].copy()
if pass_number==2:
    previous=json.loads((root/f'refine_band_contrast_{variant}_{arm}.json').read_text())
    seed_v=np.array(previous['fit']['vector']);seed_n=np.array(previous['fit']['nuisance'])

# Check the exposed band-contrast, clock and detectability gradients before fitting.
evaluation=training.evaluate_joint(seed_v,seed_n);checks=[]
indices=[0,len(seed_n)-1]+(list(range(training.clock_count,training.base_nuisance_count)) if variant=='free' else [])
for index in indices:
    step=.01 if index<training.base_nuisance_count else 1e-5
    plus=seed_n.copy();minus=seed_n.copy();plus[index]+=step;minus[index]-=step
    fd=(training.evaluate_joint(seed_v,plus)[0]-training.evaluate_joint(seed_v,minus)[0])/(2*step)
    analytic=evaluation[2][index];error=float(abs(fd-analytic)/max(1,abs(fd),abs(analytic)))
    checks.append(dict(index=index,relative_error=error));assert error<5e-4,checks

counted=CountedObjective(training,seconds=65,maximum=4999)
options=dict(arm=arm,seconds=60.,iterations=600,local_center=local_center,local_radius_km=25.)
fitted=fit_group_calibration(counted,seed_v,seed_n,**options);counted.maximum=5000
vv=np.array(fitted['vector']);nn=np.array(fitted['nuisance'])
problem=_Problem(training,vv,rf_arm=arm,local_center=options['local_center'],local_radius_km=25.,slope_half_width_hz_s=60)
limits=np.r_[np.full(training.clock_count,2000.),training.group_limits];scales=np.r_[np.full(training.clock_count,50.),training.group_scales]
value,gradient,extra,terms=counted.evaluate_joint(vv,nn);projected=scales*extra
projected[(nn<=-limits+1e-7)&(projected>=0)]=0;projected[(nn>=limits-1e-7)&(projected<=0)]=0
kkt=max(problem.stationarity(vv,gradient),float(np.max(abs(projected),initial=0)))
closure=max(abs(kkt-fitted['stationarity']),abs(value-fitted['objective']),abs(terms.nll-fitted['likelihood_nll']))
accepted=bool(fitted['converged'] and problem.feasible(vv) and np.all(abs(nn)<=limits+1e-7) and kkt<=.001 and closure<=1e-7)
audit=dict(accepted=accepted,stationarity=float(kkt),objective=float(value),nll=float(terms.nll),replay_maximum_error=float(closure))
result=dict(qualification='Cold training observations and candidate bank only; matched seed predictions, compressed timing initialization, 0.5s relative timing prior and 60s fitter/65s total allowance. Free arm jointly estimates receiver high-low contrasts; fixed arm retains donor contrasts. Declared withheld probe groups remain absent throughout fit. No target satellite IDs or corrections supplied.',variant=variant,arm=arm,fold=derivation['fold'],derived_input_sha256=derivation['derived_input_sha256'],training_count=len(cold_obs.times_s),seed_objective_closure=seed_closure,derivative_checks=checks,options=options,fit=fitted,audit=audit,elapsed_seconds=time.monotonic()-counted.begun,objective_calls=counted.calls)
result['pass_number']=pass_number;suffix='' if pass_number==1 else '_pass2'
(root/f'refine_band_contrast_{variant}_{arm}{suffix}.json').write_text(json.dumps(plain(result),indent=2)+'\n')
print(json.dumps(plain({k:result[k] for k in ['variant','arm','audit','seed_objective_closure','elapsed_seconds']})),flush=True)
