exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
from dataclasses import replace
import time
from leo.analysis.shared_scan_model import SharedScanObjective, CountedObjective, port
from leo.analysis.hard60_bounded_fit import _Problem
from leo.analysis.sequential_group_calibration import SequentialShift
from leo.application.shared_fast_position import plain

held=[]
for name,path in [('early','/tmp/rx1-ch2-50-75'),('ch4','/tmp/rx1-ch4-40-100'),('late','/tmp/rx1-ch2-170-190')]:
    rows=np.load(path+'/arrays.npz')['rows']
    if name=='early':rows=rows[np.isin(obs.times_s[rows],json.loads(Path(path+'/track_summary.json').read_text())['times'])]
    held.extend(rows.tolist())
held=np.array(sorted(set(held))); mask=np.ones(len(obs.times_s),bool);mask[held]=False
assert len(held)==129
high=stages[new['selection']['source']+'-high']['result']['fit']
shift=SequentialShift(tuple(high['group_receivers']),np.array(high['group_offsets_hz']))
training=SharedScanObjective(model.original,shift,mask=mask)
training.score=replace(training.score,relative_sigma_s=.5)
# Generic compressed start; no target-specific satellite or band correction.
start=v.copy(); total=np.clip(start[7]+zero_sum_basis(len(nums))@start[8:],-3,3)
start[7]=total.mean();start[8:]=zero_sum_basis(len(nums)).T@(total-total.mean())
initial_nuisance=n.copy()

def audit(model,fit,options,arm):
    vv=np.array(fit['vector']);nn=np.array(fit['nuisance'])
    problem=_Problem(model,vv,rf_arm=arm,local_center=options['local_center'],local_radius_km=options['local_radius_km'],slope_half_width_hz_s=60)
    limits=np.r_[np.full(model.clock_count,2000.),model.group_limits]
    scales=np.r_[np.full(model.clock_count,50.),model.group_scales]
    value,gradient,extra,terms=model.evaluate_joint(vv,nn)
    projected=scales*extra; projected[(nn<=-limits+1e-7)&(projected>=0)]=0;projected[(nn>=limits-1e-7)&(projected<=0)]=0
    stationarity=max(problem.stationarity(vv,gradient),float(np.max(abs(projected),initial=0)))
    closure=max(abs(stationarity-fit['stationarity']),abs(value-fit['objective']),abs(terms.nll-fit['likelihood_nll']))
    accepted=fit['converged'] and problem.feasible(vv) and np.all(abs(nn)<=limits+1e-7) and stationarity<=.001 and closure<=1e-7
    return dict(accepted=bool(accepted),stationarity=float(stationarity),replay_maximum_error=float(closure),objective=float(value),nll=float(terms.nll))

for arm in ['fitted-c','zero-c']:
    counted=CountedObjective(training,seconds=65,maximum=4999)
    options=dict(arm=arm,seconds=60.,iterations=600,local_center=start[:2],local_radius_km=25.)
    fit=port.fit(counted,start,initial_nuisance,**options)
    (root/('excluded_calibration_checkpoint_'+arm+'.json')).write_text(json.dumps(plain(fit),indent=2)+'\n')
    counted.maximum=5000;checked=audit(counted,fit,options,arm)
    # Invariance test: withheld measurements can be altered arbitrarily without
    # affecting the scored training objective, gradient or nuisance gradient.
    changed=object.__new__(type(training.original));changed.__dict__.update(training.original.__dict__)
    changed_obs=replace(obs,measured_hz=obs.measured_hz+np.where(mask,0.,1234567.))
    changed.observations=changed_obs
    altered=SharedScanObjective(changed,shift,mask=mask);altered.score=training.score
    aa=training.evaluate_joint(np.array(fit['vector']),np.array(fit['nuisance']))
    bb=altered.evaluate_joint(np.array(fit['vector']),np.array(fit['nuisance']))
    invariance=max(float(np.max(abs(np.asarray(x)-np.asarray(y)),initial=0)) for x,y in zip(aa[:3],bb[:3]))
    assert invariance==0
    terms=aa[3]; best=terms.responsibilities.argmax(axis=1);associated=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
    result=dict(qualification='129 target measurements excluded from calibration likelihood. Fixed full-scan candidate bank, high-band contrast and saved warm start remain conditioning assumptions; not end-to-end independent localization validation.',arm=arm,held_rows=held.tolist(),training_count=int(mask.sum()),training_associated=int(associated.sum()),withheld_measurement_invariance_maximum_error=invariance,fit=plain(fit),audit=checked,options=plain(options),objective_calls=counted.calls,elapsed_seconds=time.monotonic()-counted.begun)
    (root/('excluded_calibration_'+arm+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['arm','audit','training_count','training_associated','withheld_measurement_invariance_maximum_error','elapsed_seconds']}),flush=True)
