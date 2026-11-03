"""Select a cold-discovery low calibration on training tracks, then score test."""
import argparse,hashlib,json,sys,time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'three-track-recovery-replay-20261016'))
from replay import replay
from shared_identity_search import select
from timing_batches import batches
from leo.application.channel_group_refinement import objective
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.hard60_bounded_fit import _Problem
from leo.analysis.regional_position_bootstrap import observation_subset
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import circular

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input',type=Path,required=True);parser.add_argument('--tle-root',type=Path,required=True)
parser.add_argument('--fold',choices=('early_to_late','late_to_early'),required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if args.output.exists():raise FileExistsError('Use a new experiment filename')
ctx=replay(args,return_context=True);begun=time.monotonic()
lookup=ctx.catalogue_lookup
full,_=build_regional_bank(ctx.catalogue,[lookup[n] for n in ctx.regional_candidate_numbers],
    ctx.origin_utc_ns,ctx.training_observations,ctx.prior)
low=observation_subset(ctx.training_observations,np.flatnonzero(ctx.training_observations.channel<=4))
targets=ctx.derivation['targets'];grid=np.linspace(-5,5,201);prior=(grid/2)**2
eligible=sorted([(key,row) for key,row in ctx.stages.items() if key.startswith('discovery-point:') and row['fits'].get('low',{}).get('converged')])
results=[];best={};models={}
train_rows=np.concatenate([np.array(target['training_rows']) for target in targets])
training=observation_subset(ctx.observations,train_rows)
boundaries=np.r_[0,np.cumsum([len(t['training_rows']) for t in targets])]
arms=['fitted-c','coefficient-zero-control'];prediction_check_error=0.
progress=args.output.with_suffix('.training-progress.jsonl')
progress.parent.mkdir(parents=True,exist_ok=True)
with progress.open('x') as stream:stream.write(json.dumps(dict(scope='Training-only progress; incomplete families never publish a winner',fold=args.fold,derived_input_sha256=ctx.derivation['derived_input_sha256']))+'\n')
for key,row in eligible:
    if time.monotonic()-begun>240:raise TimeoutError('Bounded 240s discovery-calibration audit exhausted; no partial winner published')
    subset=full.select(row['satellite_indices']);assert list(map(int,subset.numbers))==row['catalogue_numbers']
    original=objective(SimpleNamespace(observations=low),subset,ctx.prior,ctx.clock_nodes)
    fit=row['fits']['low'];v=np.array(fit['vector']);n=np.array(fit['nuisance'])
    assert abs(fit['training_time_center_s']-low.time_center_s)<1e-9
    assert abs(fit['training_rf_center_hz']-low.rf_center_hz)<1e-3
    problem=_Problem(original,v,fixed_position=True)
    value,g,extra,terms=original.evaluate_joint(v,n)
    limits=np.r_[np.full(original.clock_count,2000.),original.group_limits]
    scales=np.r_[np.full(original.clock_count,50.),original.group_scales]
    projected=scales*extra;projected[(n<=-limits+1e-7)&(projected>=0)]=0;projected[(n>=limits-1e-7)&(projected<=0)]=0
    stationarity=max(problem.stationarity(v,g),float(np.max(abs(projected),initial=0)))
    assert stationarity<=.001 and abs(value-fit['objective'])<1e-7 and problem.feasible(v)
    family=dict(stage=key,position_chart_km=v[:2].tolist(),source_stationarity=float(stationarity),arms={})
    calibrations={};corrected={}
    for arm in arms:
        vv=v.copy()
        if arm=='coefficient-zero-control':vv[6]=0.
        cal=freeze_group_calibration(original,dict(vector=vv,nuisance=n))
        calibrations[arm]=cal
        corrected[arm]=training.measured_hz-cal.predict(training.times_s,training.rf_hz,training.receiver,training.channel>=5)
    tables={arm:np.empty((3,len(grid),len(full.numbers))) for arm in arms}
    for start,prediction,visible in batches(predict_orbits,full,training,ctx.prior,v[:2],grid):
        # An actual orbit-port oracle checks both ends of every batch.
        for local in {0,len(prediction)-1}:
            oracle,oracle_visible,_,_=predict_orbits(full,training,ctx.prior,v[:2],np.full(len(full.numbers),grid[start+local]),derivatives=False)
            error=float(np.max(abs(oracle-prediction[local])));prediction_check_error=max(prediction_check_error,error)
            assert error<1e-7 and np.array_equal(oracle_visible,visible[local])
        for arm in arms:
            residual=circular(corrected[arm][None,:,None]-prediction)
            for i in range(3):
                selected=slice(boundaries[i],boundaries[i+1])
                score=np.sum((residual[:,selected,:]/125)**2,axis=1)
                score[~visible[:,selected,:].all(axis=1)]=np.inf
                tables[arm][i,start:start+len(prediction)]=score
    for arm in arms:
        cal=calibrations[arm];costs=tables[arm];assignment=select(costs,prior)
        summary=dict(training_score=assignment['score'],partition=assignment['partition'],tracks=[])
        for i,target in enumerate(targets):
            k=int(assignment['candidate_indices'][i]);t=int(assignment['timing_indices'][i])
            summary['tracks'].append(dict(track=target['track'],satellite=int(full.numbers[k]),timing_s=float(grid[t]),
                training_rms_hz=float(125*np.sqrt(costs[i,t,k]/len(target['training_rows'])))))
        family['arms'][arm]=summary
        if arm not in best or summary['training_score']<best[arm]['training_score']:
            best[arm]=dict(summary,stage=key,position_chart_km=v[:2].tolist());models[arm]=(cal,v[:2].copy())
    results.append(family)
    with progress.open('a') as stream:stream.write(json.dumps(family)+'\n')
    print(json.dumps(dict(stage=key,training_scores={a:s['training_score'] for a,s in family['arms'].items()})),flush=True)

# Only after training selection is complete are the outer test CFOs evaluated.
for arm,winner in best.items():
    cal,point=models[arm]
    for target,track in zip(targets,winner['tracks']):
        rows=np.array(target['test_rows']);observations=observation_subset(ctx.observations,rows)
        k=list(full.numbers).index(track['satellite'])
        prediction=predict_orbits(full.select([k]),observations,ctx.prior,point,np.array([track['timing_s']]),derivatives=False)[0][:,0]
        correction=cal.predict(observations.times_s,observations.rf_hz,observations.receiver,observations.channel>=5)
        residual=circular(observations.measured_hz-correction-prediction)
        track.update(test_count=len(rows),test_rms_hz=float(np.sqrt(np.mean(residual**2))),test_residuals_hz=residual.tolist())
output=dict(scope='Finite cold-discovery calibration-family diagnostic. All candidate identities, shared satellite timing and calibration-family selection use the declared training groups only; no test CFO evaluated until selection is complete. Full regional bank, common 125Hz Gaussian errors, +/-5s grid and 2s timing prior. Each reused satellite has one shared timing and one prior. The zero control deletes c from the same frozen calibration without refitting intercepts or clocks; it is not an independently optimized c=0 model. No independently known satellite labels or position accuracy.',fold=args.fold,derived_input_sha256=ctx.derivation['derived_input_sha256'],candidate_count=len(full.numbers),calibration_family_count=len(eligible),families=results,winners=best,elapsed_seconds=time.monotonic()-begun)
output['batched_prediction_maximum_error_hz']=prediction_check_error
args.output.parent.mkdir(parents=True,exist_ok=True)
with args.output.open('x') as stream:json.dump(output,stream,indent=2);stream.write('\n')
print(json.dumps(dict(winners=best,elapsed_seconds=output['elapsed_seconds']),indent=2))
