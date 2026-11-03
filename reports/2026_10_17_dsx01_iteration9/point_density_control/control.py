"""Matched old-density controls: source freeze, zero-fit qualification, gated run.

No new-point/coherent fit and no held scoring occur in this executable.
"""
from dataclasses import replace
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace

import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
PILOT=REPORTS/'2026_10_17_dsx01_iteration8/coherent_pilot'
RESULTS=PILOT/'inference_results'
CASES=('old_fitted-c','old_zero-c')


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);sys.modules[name]=result;spec.loader.exec_module(result)
    return result


io=module('point_control_frozen_io',PILOT/'inference.py')
read,save,digest,fingerprint=io.read,io.save,io.digest,io.fingerprint


def public_ports():
    sys.path.insert(0,str(PILOT))
    qualifier=module('point_control_frozen_qualifier',PILOT/'qualify.py')
    adapter=module('point_control_frozen_adapter',PILOT.parent/'coherent_model/adapter.py')
    from common import refit,endpoint_status
    return SimpleNamespace(qualifier=qualifier,adapter=adapter,refit=refit,endpoint_status=endpoint_status)


def verify():io.verify_bindings(read(HERE/'source_freeze.json')['files'])


def freeze():
    sources=dict(read(PILOT/'source_freeze.json')['source_sha256'])
    io.verify_bindings(sources)
    for sealname,field in [('outcomes_seal.json','outcomes'),('predictions_seal.json','predictions')]:
        seal=read(RESULTS/sealname)
        if seal['all_four_sealed'] is not True:raise ValueError('Immutable complete pilot required')
        for row in seal[field]:sources[row['path']]=row['sha256']
    paths=[Path(__file__),HERE/'test_control.py',HERE/'PROTOCOL.md',PILOT/'inference.py',
        PILOT/'source_freeze.json',PILOT/'qualification.json',PILOT/'actual_inventory.json',
        PILOT/'inference_source_freeze.json',RESULTS/'preparation.json',RESULTS/'outcomes_seal.json',
        RESULTS/'predictions_seal.json']
    ports=public_ports()  # Import only: zero source preparation/numerical calls.
    for name,loaded in tuple(sys.modules.items()):
        path=getattr(loaded,'__file__',None)
        if name.startswith('leo.') and path and Path(path).is_file():paths.append(Path(path).resolve())
    sources.update({str(path.resolve()):digest(path) for path in paths})
    io.verify_bindings(sources)
    save(HERE/'source_freeze.json',dict(files=sources,cases=CASES,posthoc_hypothesis_selected=True,
        new_point_states_refitted=False,maximum_refit_calls_each=1000,maximum_refit_seconds_each=120,
        maximum_independent_audit_calls_each=1,qualification_external_TERM=120,qualification_external_KILL=125,
        fit_external_TERM=300,fit_external_KILL=305,no_held_score=True,no_station_reference=True))


def exact_seed(context,coherent,arm,inventory,preparation,fit):
    key='independent_'+arm;plan=inventory['cases'][key];seed=preparation['qualified_seeds'][key]
    for name,value in [('vector',context.vector),('nuisance',context.nuisance)]:
        for authority in [plan,seed,fit['original_seed']]:
            np.testing.assert_array_equal(value,authority[name])
    np.testing.assert_array_equal(coherent.model.labels,plan['labels'])
    np.testing.assert_array_equal(context.bank.numbers,seed['candidate_numbers'])
    np.testing.assert_array_equal(context.train_mask,seed['train_mask'])
    if context.fixed_c!=(arm=='zero-c') or (context.fixed_c and context.vector[6]!=0):
        raise ValueError('Exact c/c0 policy required')
    for attr in ['original','band_design','original_offsets_hz','basis','group_limits','group_scales','precision']:
        a,b=getattr(context.model,attr),getattr(coherent.model,attr)
        if fingerprint(a)!=fingerprint(b):raise ValueError('Density-only transport changed '+attr)


def prepare(ports):
    base=ports.qualifier.load_training_context()
    if len(base.observations.times_s)!=2073 or len(base.bank.numbers)!=45:
        raise ValueError('Exact TRAIN-only source2073/K45 required')
    inventory=read(PILOT/'actual_inventory.json');preparation=read(RESULTS/'preparation.json')
    contexts,coherent,sources={},{},{}
    for arm in ('fitted-c','zero-c'):
        vector=base.vector.copy()
        if arm=='zero-c':vector[6]=0.
        source=replace(base,vector=vector,nuisance=base.nuisance.copy(),fixed_c=arm=='zero-c')
        new=ports.adapter.make_context(source,policy='independent',eta=.10,epsilon=.12)
        old=replace(new,model=new.model.joint_model,full_model=new.full_model.joint_model,
            vector=new.vector.copy(),nuisance=new.nuisance.copy())
        exact_seed(old,new,arm,inventory,preparation,read(RESULTS/f'fit_independent_{arm}.json'))
        contexts['old_'+arm]=old;coherent['old_'+arm]=new;sources['old_'+arm]=source
    return contexts,coherent,sources


def qualify():
    begun=time.monotonic();verify();ports=public_ports();contexts,new,sources=prepare(ports)
    inherited_qualification={row['case']:row for row in read(PILOT/'qualification.json')['cases']}
    # The already-qualified singleton adapter supplies labels for the inventory;
    # physical cells, coordinates, priors and bounds are identical in oldtarget.
    plans={key:ports.qualifier.inventory(new[key]) for key in contexts}
    maximum=sum(plan['FDobjectives'] for plan in plans.values())+4
    state={key:fingerprint(ctx) for key,ctx in contexts.items()}
    save(HERE/'actual_inventory.json',dict(cases=plans,maximum_objectives=maximum,
        additional_metadata_predictors=4,public_preparations=1,public_selected_model_replay_calls=1,
        source_state_sha256=state,new_fit_count=0,held_CFO_scored=False))
    calls=0;results=[]
    def evaluate(model,v,n):
        nonlocal calls
        if calls>=maximum or time.monotonic()-begun>=118:raise TimeoutError('Declared qualification bound')
        calls+=1
        return model.evaluate_details(v,n)
    for key,ctx in contexts.items():
        ev,details=evaluate(ctx.model,ctx.vector,ctx.nuisance)
        native,_=evaluate(sources[key].model,sources[key].vector,sources[key].nuisance)
        for a,b in [(ev[0],native[0]),(ev[1],native[1]),(ev[2][:len(native[2])],native[2]),
            (ev[3].nll,native[3].nll),(ev[3].responsibilities,native[3].responsibilities)]:
            np.testing.assert_allclose(a,b,atol=1e-8,rtol=0)
        other,other_details=evaluate(new[key].model,ctx.vector,ctx.nuisance)
        inherited=inherited_qualification['independent_'+key.split('_',1)[1]]
        np.testing.assert_allclose(other[0],inherited['base_objective'],atol=1e-7,rtol=0)
        np.testing.assert_allclose(other[3].nll,inherited['base_training_nll'],atol=1e-7,rtol=0)
        np.testing.assert_array_equal(ev[3].residual_hz,other[3].residual_hz)
        for name in ['prediction_hz','correction_hz','visibility_weight','detection_probability']:
            # Old native details do not expose prediction/correction; use exact
            # complete metadata ports below for those two fields.
            if name in details:np.testing.assert_array_equal(details[name],other_details[name])
        np.testing.assert_allclose(ev[0]-ev[3].nll,other[0]-other[3].nll,atol=1e-10,rtol=0)
        metadata=replace(ctx.observations,measured_hz=np.zeros(len(ctx.observations.times_s)))
        old_prediction=ports.adapter.joint.predict_joint(ctx,ctx.vector,ctx.nuisance,metadata)
        new_prediction=ports.adapter.predict_coherent(new[key],ctx.vector,ctx.nuisance,metadata)
        ports.qualifier.ports.same_predictions(old_prediction,new_prediction)
        np.testing.assert_allclose(old_prediction['prediction_hz'],other_details['prediction_hz'],atol=1e-9,rtol=0)
        errors=[]
        for coordinate in plans[key]['coordinate_stencils']:
            dv,dn=np.asarray(coordinate['dv']),np.asarray(coordinate['dn']);stencil=coordinate['stencil']
            values=[evaluate(ctx.model,ctx.vector+h*dv,ctx.nuisance+h*dn)[0][0] for h in stencil['offsets']]
            observed=ports.qualifier.stencils.finite_difference(ev[0],values,stencil)
            analytic=float(ev[1]@dv+ev[2]@dn)
            allowed=ports.qualifier.stencils.tolerance(ev[0],analytic,stencil)
            record=dict(name=coordinate['name'],analytic=analytic,FD=observed,absolute_error=abs(observed-analytic),allowed=allowed)
            errors.append(record)
            if record['absolute_error']>allowed:
                save(HERE/f'failed_direction_{key}.json',record)
                raise ValueError('Native old-shared full-gradient qualification failed')
        if fingerprint(ctx)!=state[key]:raise ValueError('Qualification mutated complete source/model state')
        results.append(dict(case=key,passed=True,native_J=float(native[0]),old_shared_J=float(ev[0]),
            new_point_J=float(other[0]),prior_penalty=float(ev[0]-ev[3].nll),directions=errors,
            seed_exact=True,inherited_new_point_J_NLL_replayed=True,physical_q_calibration_predictor_exact=True))
    verify()
    save(HERE/'qualification.json',dict(passed=True,cases=results,objectives=calls,maximum_objectives=maximum,
        explicit_metadata_predictors=4,public_training_preparations=1,public_selected_model_replay_calls=1,
        elapsed_seconds=time.monotonic()-begun,source_freeze_sha256=digest(HERE/'source_freeze.json'),
        fits=0,held_CFO_scored=False,station_reference_read=False,root_fit_gate_required=True))


def execute(contexts,*,output,services,verify_frozen,authorities):
    """Two direct fits; retain all endpoints, seal before metadata predictions."""
    output=Path(output);output.mkdir(exist_ok=False);completed=[];key=None;phase='prepare'
    state={key:fingerprint(ctx) for key,ctx in contexts.items()}
    def check():
        verify_frozen()
        if any(fingerprint(ctx)!=state[key] for key,ctx in contexts.items()):
            raise ValueError('Immutable source/model/input changed')
    try:
        if tuple(contexts)!=CASES:raise ValueError('Exact two old control cases required')
        save(output/'preparation.json',dict(source_state_sha256=state,public_training_preparations=1,
            public_selected_model_replay_calls=1,additional_seed_objectives=0,**authorities))
        for key,source in contexts.items():
            phase='fit';check();ctx=io.fresh_context(source);before=fingerprint(ctx)
            result=services.refit(ctx,ctx.vector.copy(),ctx.nuisance.copy(),max_evaluations=1000,max_seconds=120.,fixed_c=ctx.fixed_c)
            raw=output/f'raw_{key}.json';save(raw,result)
            if fingerprint(ctx)!=before:raise ValueError('Fit mutated its complete state')
            check();count=result['diagnostics']['evaluations']
            if not isinstance(count,(int,np.integer)) or not 1<=count<=1000:raise ValueError('Objective budget violation')
            phase='independent_audit';counter=io.AuditCounter(ctx.model)
            audit=services.endpoint_status(replace(ctx,model=counter),result['vector'],result['nuisance'])
            if fingerprint(ctx)!=before:raise ValueError('Audit mutated its complete state')
            check();path=output/f'fit_{key}.json'
            save(path,dict(case=key,result=result,independent_endpoint_status=audit,**authorities,
                original_seed=dict(vector=source.vector,nuisance=source.nuisance),source_state_sha256=state[key],
                raw_result_sha256=digest(raw),cost=dict(refit_objectives=count,independent_audit_objectives=counter.calls,
                    combined_objectives=count+counter.calls,maximum_combined=1001),held_CFO_scored=False))
            completed.append(dict(case=key,path=str(path.resolve()),sha256=digest(path)))
        phase='outcomes_seal';check();seal=output/'outcomes_seal.json'
        score=contexts[CASES[0]].model.score
        save(seal,dict(all_two_sealed=True,outcomes=completed,**authorities,prediction_not_started=True,
            original_shared_score=dict(clutter_rate=score.clutter_rate,detection_budget=score.detection_budget),held_CFO_scored=False))
        phase='metadata';metadata,masks=services.load_metadata()
        if np.any(metadata.measured_hz!=0):raise ValueError('Metadata CFO must be blank')
        metadata_hash=fingerprint((metadata,masks));predictions=[]
        for key,source in contexts.items():
            phase='prediction';check();ctx=io.fresh_context(source);before=fingerprint(ctx)
            fitted=read(output/f'fit_{key}.json')['result']
            prediction=services.predict(ctx,np.asarray(fitted['vector']),np.asarray(fitted['nuisance']),metadata)
            if fingerprint(ctx)!=before or fingerprint((metadata,masks))!=metadata_hash:raise ValueError('Predictor mutated immutable state')
            check();path=output/f'predictions_{key}.npz'
            with path.open('xb') as stream:np.savez_compressed(stream,observation_id=np.asarray(metadata.window_ids),
                times_s=metadata.times_s,rf_hz=metadata.rf_hz,receiver=metadata.receiver,channel=metadata.channel,
                **{name+'_mask':mask for name,mask in masks.items()},**prediction)
            predictions.append(dict(case=key,path=str(path.resolve()),sha256=digest(path)))
        check();save(output/'predictions_seal.json',dict(all_two_sealed=True,predictions=predictions,
            outcomes_seal_sha256=digest(seal),metadata_sha256=metadata_hash,explicit_predictor_calls=2,**authorities,held_CFO_scored=False))
    except Exception as error:
        save(output/'failure.json',dict(phase=phase,case=key,type=type(error).__name__,message=str(error),
            traceback=traceback.format_exc(),completed_outcomes=completed,automatic_retry=False,**authorities))
        raise


def validate_fit_gate(path):
    gate=read(path)
    if gate.get('authorized') is not True or gate.get('cases')!=list(CASES):raise ValueError('Explicit root two-fit gate required')
    if gate.get('max_evaluations_per_fit')!=1000 or gate.get('max_seconds_per_fit')!=120:raise ValueError('Matched budget gate required')
    for key,file in [('qualification_sha256','qualification.json'),('source_freeze_sha256','source_freeze.json'),
        ('actual_inventory_sha256','actual_inventory.json'),('runner_sha256','control.py')]:
        if gate.get(key)!=digest(HERE/file):raise ValueError('Root gate binding differs: '+key)
    qualification=read(HERE/'qualification.json')
    if qualification.get('passed') is not True or qualification.get('fits')!=0:raise ValueError('Passed zero-fit qualification required')
    verify()


def run(gate_path):
    gate_path=Path(gate_path).resolve();validate_fit_gate(gate_path);ports=public_ports();contexts,_,_=prepare(ports)
    inventory=read(HERE/'actual_inventory.json')
    for key,ctx in contexts.items():
        np.testing.assert_array_equal(ctx.vector,inventory['cases'][key]['vector'])
        np.testing.assert_array_equal(ctx.nuisance,inventory['cases'][key]['nuisance'])
        if fingerprint(ctx)!=inventory['source_state_sha256'][key]:raise ValueError('Qualified complete source/model arrays differ')
    source=next(iter(contexts.values()))
    def metadata():
        rows=[]
        fields=('observation_id','time_s','actual_rf_hz','receiver','channel')
        path=REPORTS/'2026_10_16_dsx01_fast_association_losses/context-observations.jsonl'
        for line in path.read_text().splitlines():
            row=json.loads(line)
            if row['source_id']=='S03':rows.append({name:row[name] for name in fields})
        blank=ports.qualifier.ports.metadata_only(rows)
        derivation=REPORTS/'2026_10_17_dsx01_iteration5/blocked_cold/S03-block20-parity0/derivation.json'
        masks=ports.qualifier.ports.role_masks(blank.window_ids,read(derivation)['membership'])
        if len(rows)!=3988 or {k:int(v.sum()) for k,v in masks.items()}!={'train':2073,'held':1909,'boundary':6}:
            raise ValueError('Exact full metadata/masks required')
        np.testing.assert_array_equal(np.asarray(blank.window_ids)[masks['train']],source.observations.window_ids)
        return blank,masks
    authorities=dict(root_gate_path=str(gate_path),root_gate_sha256=digest(gate_path),
        qualification_sha256=digest(HERE/'qualification.json'),source_freeze_sha256=digest(HERE/'source_freeze.json'),
        immutable_new_point_outcomes_sha256=digest(RESULTS/'outcomes_seal.json'),
        immutable_new_point_predictions_sha256=digest(RESULTS/'predictions_seal.json'))
    save(HERE/'execution_gate.json',dict(**authorities,cases=CASES,fit_not_started=True))
    execute(contexts,output=HERE/'inference_results',verify_frozen=lambda:(verify(),validate_fit_gate(gate_path)),authorities=authorities,
        services=SimpleNamespace(refit=ports.refit,endpoint_status=ports.endpoint_status,predict=ports.adapter.joint.predict_joint,load_metadata=metadata))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['freeze','qualify','run'])
    parser.add_argument('--gate',type=Path);args=parser.parse_args()
    if args.action=='freeze':freeze()
    elif args.action=='qualify':
        try:qualify()
        except Exception as error:
            save(HERE/'qualification_failure.json',dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc(),fits=0))
            raise
    else:
        if args.gate is None:parser.error('run requires --gate')
        run(args.gate)
