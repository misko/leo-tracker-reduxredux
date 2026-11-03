"""Training-only, exact-objective timing basin search over every retained satellite."""
import argparse
from dataclasses import asdict
import hashlib,json,sys,time
from pathlib import Path
from types import SimpleNamespace
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'three-track-local-segments-20261016'))
from evaluate import observations,audit,classify_frozen_endpoint
from replay import verify_capsule
from profile_kernel import components,replacement_nll,replaced_timing_penalty,timing_penalty,predict_single_candidate
from leo.cli.shared_fast_position import load_input
from leo.application.shared_orbit_replay import selected_model
from leo.application.channel_group_refinement import objective
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import ALIAS_HZ,zero_sum_basis
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.hard60_bounded_fit import _Problem
from leo.analysis.shared_scan_model import horizon_weight,elevation_geometry,CountedObjective,donor_state
from leo.analysis.sequential_group_calibration import SequentialShift
from leo.analysis.channel_group_calibration import fit_group_calibration
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def context(args):
    verify_capsule()
    terminal=json.loads((args.attempt/'output/terminal.json').read_text())
    if terminal['state']!='complete':raise ValueError('Accepted cold endpoint required')
    derivation=json.loads((args.attempt/'derivation.json').read_text())
    payload=(args.attempt/'training-input.json').read_bytes()
    if hashlib.sha256(payload).hexdigest()!=derivation['derived_input_sha256']:raise ValueError('Training input differs')
    source=load_input(json.loads(payload));obs=observations(source);stages={}
    for binding in terminal['stage_receipts']:
        data=Path(binding['path']).read_bytes()
        if 'sha256:'+hashlib.sha256(data).hexdigest()!=binding['sha256']:raise ValueError('Stage input differs')
        stages[Path(binding['path']).stem]=json.loads(data)
    prior=RegionalPrior(**terminal['provenance']['prior']);nodes=np.array(terminal['provenance']['clock_nodes_s'])
    archive=TleArchiveReader(args.tle_root)
    snapshot=next(s for s in archive.list_snapshots() if s.digest==terminal['provenance']['tle_sha256'])
    catalogue=parse_element_sets(archive.read(snapshot));lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    numbers=terminal['candidate_numbers']
    bank,_=build_regional_bank(catalogue,[lookup[n] for n in numbers],source.timing.first_sample_estimate_utc_ns,obs,prior)
    order={int(n):i for i,n in enumerate(bank.numbers)};bank=bank.select([order[n] for n in numbers])
    model,fit,checked=selected_model(dict(all=SimpleNamespace(observations=obs)),bank,prior,nodes,terminal,stages)
    if not checked['accepted']:raise ValueError('Cold endpoint failed original strict replay')
    selected=terminal['selection']['source']
    if selected=='B-all':
        joint=objective(SimpleNamespace(observations=obs),bank,prior,nodes)
        _,shift,_,_,_=donor_state(joint,stages[f"B-{stages['source-selection']['B_index']}"]['result']['fit'])
    else:
        high=stages[selected+'-high']['result']['fit']
        shift=SequentialShift(tuple(high['group_receivers']),np.array(high['group_offsets_hz']))
    return SimpleNamespace(model=model,fit=fit,obs=obs,terminal=terminal,derivation=derivation,
                           prior=prior,nodes=nodes,bank=bank,shift=shift,cold_audit=checked)


def profile(ctx,arm,folder):
    model=ctx.model;obs=ctx.obs;v=np.array(ctx.fit['vector']);n=np.array(ctx.fit['nuisance'])
    if arm=='zero-c':v[6]=0.
    problem=_Problem(model,v,rf_arm=arm,local_center=v[:2],local_radius_km=25.,slope_half_width_hz_s=60)
    if not problem.feasible(v):raise ValueError('Initial RF arm is infeasible')
    (initial,details)=model.evaluate_details(v,n);value=initial[0];start_value=value
    sigma=details['sigma_hz'];q=details['detection_probability'];weight=details['visibility_weight'].copy()
    timings=v[7]+model.basis@v[8:]
    prediction=predict_orbits(ctx.bank,obs,ctx.prior,v[:2],timings,derivatives=False)[0]
    correction=model.original.correction(v,n[:model.clock_count]);prediction+=correction[:,None]
    odds,signal=components(obs.measured_hz[:,None],prediction,weight,sigma[:,None],q,ALIAS_HZ)
    old_nll=float(replacement_nll(odds.sum(axis=1),signal.sum(axis=1),0.,0.,model.score.clutter_rate,ALIAS_HZ))
    if abs(old_nll-initial[3].nll)>1e-7:raise ValueError('Initial normalized likelihood cache differs')
    grid=np.linspace(-20,20,801);started=time.monotonic();moves=[];checked_candidates=[]
    max_prediction_error=0.;max_sine_error=0.;max_objective_error=0.
    for k in np.argsort(ctx.bank.numbers,kind='stable'):
        if time.monotonic()-started>=180.:break
        other=np.arange(len(timings))!=k
        other_odds=odds[:,other].sum(axis=1);other_signal=signal[:,other].sum(axis=1)
        old_prior=float(timing_penalty(timings,model.score.common_sigma_s,model.score.relative_sigma_s))
        best_value=value;best_timing=float(timings[k]);best_arrays=None
        single=ctx.bank.select([k])
        allowed=grid[(abs((timings.sum()-timings[k]+grid)/len(timings))<=10)]
        complete=True
        for start in range(0,len(allowed),16):
            if time.monotonic()-started>=180.:complete=False;break
            tau=allowed[start:start+16]
            predicted,sine=predict_single_candidate(single,obs,ctx.prior,v[:2],tau)
            # Check the actual ephemeris kernel at both search-domain ends.
            if start==0 or start+16>=len(allowed):
                for j in {0,len(tau)-1}:
                    oracle=predict_orbits(single,obs,ctx.prior,v[:2],np.array([tau[j]]),derivatives=False)[0][:,0]
                    elevation=elevation_geometry(single,obs,ctx.prior,v[:2],np.array([tau[j]]))[0][:,0]
                    pe=float(np.max(abs(oracle-predicted[j])));se=float(np.max(abs(elevation-sine[j])))
                    max_prediction_error=max(max_prediction_error,pe);max_sine_error=max(max_sine_error,se)
                    if pe>=1e-7 or se>=1e-13:raise ValueError('Batched orbital port differs from actual public port')
            w=horizon_weight(sine,model.visibility_width)[0]
            new_odds,new_signal=components(obs.measured_hz[None,:],predicted+correction[None,:],w,sigma[None,:],q[k],ALIAS_HZ)
            nll=replacement_nll(other_odds,other_signal,new_odds,new_signal,model.score.clutter_rate,ALIAS_HZ)
            prior=replaced_timing_penalty(timings,k,tau,model.score.common_sigma_s,model.score.relative_sigma_s)
            values=value-old_nll-old_prior+nll+prior;j=int(np.argmin(values))
            if values[j]<best_value-.01:
                best_value=float(values[j]);best_timing=float(tau[j]);best_arrays=(new_odds[j].copy(),new_signal[j].copy(),w[j].copy(),predicted[j].copy()+correction,float(nll[j]))
        if not complete:break
        checked_candidates.append(int(ctx.bank.numbers[k]))
        if best_arrays is not None:
            trial=timings.copy();trial[k]=best_timing
            vv=v.copy();vv[7]=trial.mean();vv[8:]=model.basis.T@(trial-trial.mean())
            if not problem.feasible(vv):raise ValueError('Timing replacement violates original physical constraints')
            direct=model.evaluate_joint(vv,n)
            error=abs(direct[0]-best_value);max_objective_error=max(max_objective_error,error)
            if error>1e-6 or direct[0]>value+1e-7:raise ValueError('Profile step does not replay or worsens original objective')
            row=dict(satellite=int(ctx.bank.numbers[k]),before_timing_s=float(timings[k]),after_timing_s=best_timing,
                     before_objective=float(value),after_objective=float(direct[0]),objective_replay_error=error)
            moves.append(row);timings=trial;v=vv;value=float(direct[0]);old_nll=float(direct[3].nll)
            odds[:,k],signal[:,k],weight[:,k],prediction[:,k]=best_arrays[:4]
            with (folder/'profile-progress.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')
            print(json.dumps(dict(event='profile-move',arm=arm,**row)),flush=True)
    return v,n,dict(complete=len(checked_candidates)==len(timings),candidates_checked=checked_candidates,
        candidate_count=len(timings),moves=moves,start_objective=float(start_value),end_objective=float(value),
        elapsed_seconds=time.monotonic()-started,maximum_seconds=180.,
        maximum_prediction_oracle_error_hz=max_prediction_error,maximum_sine_oracle_error=max_sine_error,
        maximum_objective_replay_error=max_objective_error)


def run(args):
    if args.output.exists():raise FileExistsError('Use a new coordinate-search namespace')
    ctx=context(args);args.output.mkdir(parents=True,exist_ok=False)
    v,n,receipt=profile(ctx,args.arm,args.output)
    result=dict(arm=args.arm,derived_input_sha256=ctx.derivation['derived_input_sha256'],
        terminal_sha256=hashlib.sha256((args.attempt/'output/terminal.json').read_bytes()).hexdigest(),
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')},
        scope='All-candidate, training-only timing coordinate search in the unchanged normalized point likelihood. No target membership, target identity, per-target correction or held frequency enters search or refitting. Both RF arms start from the same new cold fitted-c checkpoint and frozen band contrast, with c set to zero only in the zero arm. Candidate set, priors, constraints, spatial continuation domain and work budgets are matched. Actual frozen classification is evaluated only after completion; forward hypotheses are not independent identity truth. No position accuracy claim.',
        score=asdict(ctx.model.score),profile=receipt,fit={},audit=dict(accepted=False,reason='Incomplete timing sweep'))
    (args.output/'profile.json').write_text(json.dumps(dict(vector=v,nuisance=n,**receipt),indent=2,default=lambda a:a.tolist())+'\n')
    if receipt['complete']:
        options=dict(arm=args.arm,seconds=60.,iterations=600,local_center=ctx.fit['vector'][:2],local_radius_km=25.)
        counted=CountedObjective(ctx.model,seconds=65.,maximum=4999);begun=time.monotonic()
        try:
            fit=fit_group_calibration(counted,v,n,**options);counted.maximum=5000
            checked=audit(counted,fit,options)
            if time.monotonic()-begun>65:checked.update(accepted=False,reason='65s total fit allowance exceeded')
            result.update(fit=fit,audit=checked,options=options,fit_elapsed_seconds=time.monotonic()-begun,
                          actual_objective_calls=counted.calls)
        except (ValueError,TimeoutError) as error:
            result['audit']=dict(accepted=False,reason=str(error),error_type=type(error).__name__)
        if result['fit']:
            document=json.loads(args.input.read_text())
            if hashlib.sha256(args.input.read_bytes()).hexdigest()!=ctx.derivation['parent_input_sha256']:
                raise ValueError('Original evaluation input differs')
            full=observations(load_input(document))
            result['pipeline_classification']=classify_frozen_endpoint(ctx.model,result['fit'],ctx.shift,full,
                ctx.derivation,ctx.nodes)
    (args.output/'result.json').write_text(json.dumps(result,indent=2,default=lambda a:a.tolist())+'\n')
    print(json.dumps(dict(arm=args.arm,profile_complete=receipt['complete'],moves=len(receipt['moves']),
        improvement=receipt['start_objective']-receipt['end_objective'],audit=result['audit'],
        tracks=result.get('pipeline_classification',{}).get('tracks',[])),default=lambda a:a.tolist()),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['input','attempt','tle-root','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--arm',choices=['fitted-c','zero-c'],required=True);run(p.parse_args())
