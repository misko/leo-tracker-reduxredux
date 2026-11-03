"""Verify a new cold endpoint, run matched RF arms and evaluate frozen timing proposals."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import time

import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'three-track-recovery-replay-20261016'))
sys.path.insert(0,str(HERE.parent/'three-track-discovery-ensemble-20261016'))
from replay import verify_capsule,verified_json
from timing_batches import batches
from leo.cli.shared_fast_position import load_input
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.application.shared_orbit_replay import selected_model
from leo.application.channel_group_refinement import objective
from leo.analysis.regional_position_bootstrap import observation_subset
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import circular
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.hard60_bounded_fit import _Problem
from leo.analysis.channel_group_calibration import fit_group_calibration,project_calibration_seed
from leo.analysis.sequential_group_calibration import freeze_sequential_calibration,SequentialShift,fixed_shift_objective
from leo.analysis.shared_scan_model import CountedObjective,donor_state,SharedScanObjective
from leo.contracts.regional_position import PositionObservations,RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def observations(source):
    winners={}
    for p in project_scanner_candidates(source):
        old=winners.get(p.source_group_id)
        if old is None or (-p.margin,p.candidate_rank,p.candidate_id)<(-old.margin,old.candidate_rank,old.candidate_id):winners[p.source_group_id]=p
    points=sorted(winners.values(),key=lambda p:(p.support_center_utc_ns,p.source_group_id))
    origin=source.timing.first_sample_estimate_utc_ns
    return PositionObservations(tuple(p.source_group_id for p in points),
        np.array([(p.support_center_utc_ns-origin)/1e9 for p in points]),
        np.array([p.measured_cfo_hz for p in points]),np.array([p.actual_rf_hz for p in points]),
        np.array([p.receiver_id for p in points]),np.array([p.channel for p in points]),
        np.array([p.margin for p in points]))


def audit(model,fit,options):
    v=np.array(fit['vector']);n=np.array(fit['nuisance'])
    problem=_Problem(model,v,rf_arm=options['arm'],local_center=options['local_center'],
                     local_radius_km=options['local_radius_km'],slope_half_width_hz_s=60,
                     fixed_position=options.get('fixed_position',False))
    value,g,extra,terms=model.evaluate_joint(v,n)
    limits=np.r_[np.full(model.clock_count,2000.),model.group_limits]
    scales=np.r_[np.full(model.clock_count,50.),model.group_scales]
    projected=scales*extra
    projected[(n<=-limits+1e-7)&(projected>=0)]=0
    projected[(n>=limits-1e-7)&(projected<=0)]=0
    stationarity=max(problem.stationarity(v,g),float(np.max(abs(projected),initial=0)))
    closure=max(abs(value-fit['objective']),abs(terms.nll-fit['likelihood_nll']),abs(stationarity-fit['stationarity']))
    return dict(accepted=bool(fit['converged'] and problem.feasible(v) and np.all(abs(n)<=limits+1e-7)
        and stationarity<=.001 and closure<=1e-7),objective=float(value),nll=float(terms.nll),
        stationarity=float(stationarity),replay_maximum_error=float(closure))


def classify_frozen_endpoint(model,fit,shift,full_obs,derivation,nodes):
    """Evaluate actual learned assignments; do not fit target-specific timings."""
    v=np.array(fit['vector']);n=np.array(fit['nuisance'])
    calibration=freeze_sequential_calibration(model.original,
        dict(vector=v,nuisance=n[:model.clock_count]),shift)
    joint=objective(SimpleNamespace(observations=full_obs),model.bank,model.prior,nodes)
    raw=fixed_shift_objective(joint.base,shift)
    correction=calibration.predict(full_obs.times_s,full_obs.rf_hz,full_obs.receiver,full_obs.channel>=5)
    projection=project_calibration_seed(raw,correction-raw.baseline)
    vv=v.copy();vv[2:7]=projection['coefficients'][:5]
    nn=np.r_[projection['coefficients'][5:],n[model.clock_count:]]
    full_model=SharedScanObjective(raw,shift)
    error=float(np.max(abs(raw.correction(vv,nn[:full_model.clock_count])-correction)))
    if error>=1e-6:raise ValueError('Frozen classifier calibration transport differs')
    terms=full_model.evaluate_joint(vv,nn)[3]
    original_terms=model.evaluate_joint(v,n)[3]
    lookup={key:i for i,key in enumerate(full_obs.window_ids)}
    training_indices=np.array([lookup[key] for key in model.observations.window_ids])
    posterior_error=float(np.max(abs(terms.responsibilities[training_indices]-original_terms.responsibilities)))
    if posterior_error>=1e-8:raise ValueError('Original training classifier posterior differs after transport')
    selected=np.argmax(terms.responsibilities,axis=1)
    associated=terms.responsibilities[np.arange(len(selected)),selected]>terms.clutter_probability
    records=[]
    hypotheses=dict(early_ch2=69433,ch4=69333,late_ch2=69522)
    for target in derivation['targets']:
        train=np.array(target['training_rows']);test=np.array(target['test_rows'])
        # Choose the group label from training posterior mass only, even when
        # held point classifications favor some other candidate.
        k=int(np.argmax(terms.responsibilities[train].sum(axis=0)))
        signal_mass=float(terms.responsibilities[train,k].sum())
        clutter_mass=float(terms.clutter_probability[train].sum())
        supported=signal_mass>clutter_mass
        counts={int(model.bank.numbers[j]):int(np.sum((selected[test]==j)&associated[test]))
                for j in np.unique(selected[test][associated[test]])}
        hypothesis=hypotheses[target['track']]
        records.append(dict(track=target['track'],training_satellite=int(model.bank.numbers[k]) if supported else None,
            training_label_supported=supported,training_signal_mass=signal_mass,training_clutter_mass=clutter_mass,
            diagnostic_best_mass_candidate=int(model.bank.numbers[k]),
            training_rms_hz=float(np.sqrt(np.mean(terms.residual_hz[train,k]**2))) if supported else None,
            test_rms_hz=float(np.sqrt(np.mean(terms.residual_hz[test,k]**2))) if supported else None,
            test_count=len(test),test_associated_count=int(associated[test].sum()),
            test_matches_training_satellite=int(np.sum((selected[test]==k)&associated[test])) if supported else 0,
            test_assigned_satellite_counts=counts,forward_consistent_hypothesis=hypothesis,
            hypothesis_in_bank=bool(hypothesis in model.bank.numbers),
            test_matches_forward_hypothesis=counts.get(hypothesis,0),
            test_residuals_hz=terms.residual_hz[test,k].tolist() if supported else None))
    return dict(scope='Actual frozen pipeline classifier, with its learned candidate bank, timing and detectability. No per-target timing search or additional fit. Group label is selected by training posterior mass only; forward-consistent hypotheses are not independent identity labels.',
        calibration_transport_maximum_error_hz=error,
        training_posterior_transport_maximum_error=posterior_error,tracks=records)


def run(args):
    if args.output.exists():raise FileExistsError('Use a new evaluation namespace')
    verify_capsule();terminal=verified_json(args.attempt/'output/terminal.json')
    derivation=verified_json(args.attempt/'derivation.json')
    expected=verified_json(HERE.parent/'three-track-recovery-replay-20261016/checkpoints'/args.fold/'derivation.json')
    if derivation!=expected:raise ValueError('Target/fold definitions differ from original frozen checkpoint')
    result=dict(fold=args.fold,state=terminal['state'],
        terminal_sha256=hashlib.sha256((args.attempt/'output/terminal.json').read_bytes()).hexdigest(),
        derived_input_sha256=derivation['derived_input_sha256'],arms=[],
        qualification='Research development-fold evaluation. Entire held probe groups are absent from cold source generation and refitting. Matched fitted-c and c=0 continuations use identical observations, bank, priors, local search domain and 60s/65s budgets, conditional on the same new fitted-c cold endpoint and frozen band contrasts. Training-only satellite/timing proposals are searched against all regional candidates; test CFO values are evaluated only after proposal selection. No independent satellite identity or geographic truth. Segment hyperparameters were developed using training membership coverage in both temporal folds; these are not pristine external validation data.')
    if terminal['state']!='complete':
        result['reason']=terminal.get('reason','No accepted cold endpoint');return result
    document=verified_json(args.input,derivation['parent_input_sha256']);source=load_input(document)
    full_obs=observations(source)
    cold_source=load_input(verified_json(args.attempt/'training-input.json',derivation['derived_input_sha256']))
    cold=observations(cold_source);held=derivation['withheld_original_rows']
    keep=np.ones(len(full_obs.times_s),bool);keep[held]=False
    if tuple(np.array(full_obs.window_ids)[keep])!=cold.window_ids:raise ValueError('Held source-group inventory differs')
    for name in ['times_s','measured_hz','rf_hz','receiver','channel','margin']:
        np.testing.assert_array_equal(getattr(full_obs,name)[keep],getattr(cold,name))
    if 'sha256:'+derivation['derived_input_sha256']!=terminal['input_sha256']:raise ValueError('Terminal training-input digest differs')
    stages={}
    for binding in terminal['stage_receipts']:
        path=Path(binding['path']);payload=path.read_bytes()
        if path.resolve().parent!=(args.attempt/'output/stages').resolve():raise ValueError('Stage receipt outside attempt')
        if 'sha256:'+hashlib.sha256(payload).hexdigest()!=binding['sha256']:raise ValueError('Stage hash differs')
        stages[path.stem]=json.loads(payload)
    prior=RegionalPrior(**terminal['provenance']['prior']);archive=TleArchiveReader(args.tle_root)
    snapshot=next(s for s in archive.list_snapshots() if s.digest==terminal['provenance']['tle_sha256'])
    catalogue=parse_element_sets(archive.read(snapshot));lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    origin=source.timing.first_sample_estimate_utc_ns;nums=terminal['candidate_numbers']
    bank,_=build_regional_bank(catalogue,[lookup[n] for n in nums],origin,cold,prior)
    order={int(n):i for i,n in enumerate(bank.numbers)};bank=bank.select([order[n] for n in nums])
    model,seed,cold_audit=selected_model(dict(all=SimpleNamespace(observations=cold)),bank,prior,
        np.array(terminal['provenance']['clock_nodes_s']),terminal,stages)
    result['cold_audit']=cold_audit
    if not cold_audit['accepted']:raise ValueError('New cold endpoint fails replay audit')
    selected=terminal['selection']['source']
    if selected=='B-all':
        joint=objective(SimpleNamespace(observations=cold),bank,prior,np.array(terminal['provenance']['clock_nodes_s']))
        _,shift,_,_,_=donor_state(joint,stages[f"B-{stages['source-selection']['B_index']}"]['result']['fit'])
    else:
        high=stages[selected+'-high']['result']['fit']
        shift=SequentialShift(tuple(high['group_receivers']),np.array(high['group_offsets_hz']))
    frozen=freeze_sequential_calibration(model.original,dict(vector=np.array(seed['vector']),
        nuisance=np.array(seed['nuisance'])[:model.clock_count]),shift)
    difference=frozen.predict(cold.times_s,cold.rf_hz,cold.receiver,cold.channel>=5)-model.original.correction(
        np.array(seed['vector']),np.array(seed['nuisance'])[:model.clock_count])
    result['calibration_transport_maximum_error_hz']=float(np.max(abs(difference)))
    if result['calibration_transport_maximum_error_hz']>=1e-6:raise ValueError('Frozen calibration differs')
    result['cold_pipeline_classification']=classify_frozen_endpoint(model,seed,shift,full_obs,
        derivation,np.array(terminal['provenance']['clock_nodes_s']))
    if args.check_held_isolation:
        changed=full_obs.measured_hz.copy();changed[held]+=1234567.
        check=classify_frozen_endpoint(model,seed,shift,replace(full_obs,measured_hz=changed),
            derivation,np.array(terminal['provenance']['clock_nodes_s']))
        maximum=0.
        for before,after in zip(result['cold_pipeline_classification']['tracks'],check['tracks']):
            if before['training_satellite']!=after['training_satellite']:
                raise ValueError('Held CFO values changed the training group identity')
            if before['training_rms_hz'] is not None:
                maximum=max(maximum,abs(before['training_rms_hz']-after['training_rms_hz']))
        if maximum>=1e-8:raise ValueError('Held CFO values changed training carrier predictions')
        result['held_classifier_isolation']=dict(perturbation_hz=1234567.,
            withheld_rows=len(held),training_identity_unchanged=True,
            training_rms_maximum_change_hz=maximum)
    if args.checkpoint_only:return result
    full_bank,_=build_regional_bank(catalogue,[lookup[n] for n in terminal['provenance']['full_candidate_numbers']],origin,cold,prior)
    args.output.mkdir(parents=True,exist_ok=False)
    for arm in ['fitted-c','zero-c']:
        v=np.array(seed['vector']);n=np.array(seed['nuisance']);begun=time.monotonic()
        options=dict(arm=arm,seconds=60.,iterations=600,local_center=v[:2].tolist(),local_radius_km=25.)
        counted=CountedObjective(model,seconds=65.,maximum=4999)
        try:
            fit=fit_group_calibration(counted,v,n,**options)
            counted.maximum=5000;checked=audit(counted,fit,options)
        except (ValueError,TimeoutError) as error:
            row=dict(arm=arm,options=options,audit=dict(accepted=False,reason=str(error),
                error_type=type(error).__name__),actual_objective_calls=counted.calls,
                elapsed_seconds=time.monotonic()-begun,tracks=[])
            (args.output/(arm+'.json')).write_text(json.dumps(row,indent=2)+'\n')
            result['arms'].append(row);continue
        elapsed=time.monotonic()-begun
        if elapsed>65:checked.update(accepted=False,reason='65s overall allowance exceeded')
        row=dict(arm=arm,options=options,fit=fit,audit=checked,elapsed_seconds=elapsed,
                 actual_objective_calls=counted.calls,tracks=[])
        row['pipeline_classification']=classify_frozen_endpoint(model,fit,shift,full_obs,
            derivation,np.array(terminal['provenance']['clock_nodes_s']))
        # Rejected endpoints remain diagnostic; never promote their metrics.
        cal=freeze_sequential_calibration(model.original,dict(vector=np.array(fit['vector']),
            nuisance=np.array(fit['nuisance'])[:model.clock_count]),shift)
        for target in derivation['targets']:
            train=observation_subset(full_obs,np.array(target['training_rows']));grid=np.linspace(-5,5,201)
            correction=cal.predict(train.times_s,train.rf_hz,train.receiver,train.channel>=5)
            best=np.inf;chosen=None
            for start,pred,visible in batches(predict_orbits,full_bank,train,prior,np.array(fit['vector'])[:2],grid):
                residual=circular(train.measured_hz[None,:,None]-correction[None,:,None]-pred)
                cost=np.sum((residual/125)**2,axis=1)+(grid[start:start+len(pred),None]/2)**2
                cost[~visible.all(axis=1)]=np.inf
                ti,k=np.unravel_index(np.argmin(cost),cost.shape)
                if cost[ti,k]<best:best=float(cost[ti,k]);chosen=(k,float(grid[start+ti]),float(np.sqrt(np.mean(residual[ti,:,k]**2))))
            if chosen is None:raise ValueError('No visible training proposal')
            k,timing,training_rms=chosen;test=observation_subset(full_obs,np.array(target['test_rows']))
            prediction=predict_orbits(full_bank.select([k]),test,prior,np.array(fit['vector'])[:2],np.array([timing]),derivatives=False)[0][:,0]
            error=circular(test.measured_hz-cal.predict(test.times_s,test.rf_hz,test.receiver,test.channel>=5)-prediction)
            row['tracks'].append(dict(track=target['track'],satellite=int(full_bank.numbers[k]),timing_s=timing,
                training_rms_hz=training_rms,test_rms_hz=float(np.sqrt(np.mean(error**2))),test_count=len(error),test_residuals_hz=error.tolist()))
        (args.output/(arm+'.json')).write_text(json.dumps(row,indent=2,default=lambda a:a.tolist())+'\n')
        result['arms'].append(row)
        print(json.dumps(dict(arm=arm,audit=checked,tracks=row['tracks'])),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['input','tle-root','attempt','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--checkpoint-only',action='store_true')
    p.add_argument('--check-held-isolation',action='store_true')
    p.add_argument('--fold',choices=['early_to_late','late_to_early'],required=True);args=p.parse_args()
    result=run(args)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'evaluation.json').write_text(json.dumps(result,indent=2,default=lambda a:a.tolist())+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='arms'}),flush=True)
