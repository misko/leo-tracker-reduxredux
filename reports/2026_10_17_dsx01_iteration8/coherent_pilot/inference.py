"""Explicitly gated four-fit runner; writes frozen metadata predictions, no scores.

Run `freeze --gate PATH` separately before `run --gate PATH`. A passed actual
qualification alone never authorizes fitting. No imports prepare data until
the root gate and all frozen source bindings have been checked.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
CASES = ('independent_fitted-c', 'automatic_fitted-c', 'independent_zero-c', 'automatic_zero-c')
MAX_EVALUATIONS = 1000
MAX_SECONDS = 120.


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def plain(value):
    if isinstance(value, np.ndarray):return plain(value.tolist())
    if isinstance(value, np.generic):return plain(value.item())
    if isinstance(value, dict):return {str(k):plain(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):return [plain(v) for v in value]
    if isinstance(value, Path):return str(value)
    if isinstance(value, float) and not np.isfinite(value):
        return {'nonfinite_float':repr(value)}
    return value


def save(path, value):
    """Exclusive, durable record: a failed namespace cannot silently retry."""
    import os
    with Path(path).open('x') as stream:
        json.dump(plain(value), stream, indent=2, allow_nan=False)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())


def fingerprint(value):
    """Hash complete arrays/object state, including metadata, calibration and q.

    Identity markers preserve sharing/cycles without memory-address dependence.
    Scientific callable code is bound separately by the execution source seal.
    """
    h, seen = hashlib.sha256(), {}
    def feed(x):
        if isinstance(x, np.generic):x=x.item()
        if x is None or isinstance(x,(str,int,float,bool,complex)):
            h.update((type(x).__name__+':'+repr(x)+';').encode());return
        if isinstance(x,Path):feed(str(x));return
        if callable(x):
            feed(('callable',getattr(x,'__module__',''),getattr(x,'__qualname__',type(x).__qualname__)));return
        identity=id(x)
        if identity in seen:
            h.update(('ref:'+str(seen[identity][0])+';').encode());return
        seen[identity]=(len(seen),x)  # Keep temporary containers alive: no id reuse.
        if isinstance(x,np.ndarray):
            feed(('array',x.dtype.str,x.shape))
            if x.dtype.hasobject:feed(x.tolist())
            else:h.update(np.ascontiguousarray(x).tobytes())
        elif isinstance(x,dict):
            h.update(b'dict;')
            for key in sorted(x,key=repr):feed(key);feed(x[key])
        elif isinstance(x,(list,tuple)):
            h.update((type(x).__name__+';').encode())
            for item in x:feed(item)
        elif isinstance(x,(set,frozenset)):
            feed((type(x).__name__,sorted(x,key=repr)))
        elif hasattr(x,'__dict__'):
            feed((type(x).__module__,type(x).__qualname__,vars(x)))
        else:raise TypeError('Unsupported fingerprint state: '+type(x).__qualname__)
    feed(value)
    return 'sha256:'+h.hexdigest()


def verify_bindings(bindings):
    for path, expected in bindings.items():
        if digest(path)!=expected:raise ValueError('Frozen source/input changed: '+str(path))


def validate_gate(gate_path, *, directory=HERE):
    directory=Path(directory).resolve();gate_path=Path(gate_path).resolve()
    gate=read(gate_path)
    if gate.get('authorized') is not True:raise ValueError('Explicit root fit authorization is required')
    if gate.get('cases')!=list(CASES):raise ValueError('Exact ordered four-case gate required')
    if gate.get('max_evaluations_per_fit')!=MAX_EVALUATIONS or gate.get('max_seconds_per_fit')!=MAX_SECONDS:
        raise ValueError('Gate must preserve declared1000-call/120-second budgets')
    qualification_path=Path(gate['qualification_path'])
    if not qualification_path.is_absolute():qualification_path=gate_path.parent/qualification_path
    if qualification_path.resolve()!=directory/'qualification.json':raise ValueError('Gate must bind this namespace qualification')
    required={'qualification_sha256':'qualification.json','source_freeze_sha256':'source_freeze.json',
        'actual_inventory_sha256':'actual_inventory.json','runner_sha256':'inference.py'}
    for field,name in required.items():
        if gate.get(field)!=digest(directory/name):raise ValueError('Root gate hash mismatch: '+field)
    qualification=read(qualification_path)
    if qualification.get('passed') is not True or qualification.get('fits')!=0 or qualification.get('held_CFO_scored') is not False:
        raise ValueError('Passed zero-fit/no-held-score qualification required')
    if [row['case'] for row in qualification['cases']]!=list(CASES):raise ValueError('Qualification cases differ')
    inventory=read(directory/'actual_inventory.json')
    if list(inventory['cases'])!=list(CASES):raise ValueError('Actual qualified inventory cases differ')
    verify_bindings(read(directory/'source_freeze.json')['source_sha256'])
    return gate


def freeze(gate_path):
    """No preparation/objectives: bind this runner to the actual passed gate."""
    gate_path=Path(gate_path).resolve();validate_gate(gate_path)
    bindings=dict(read(HERE/'source_freeze.json')['source_sha256'])
    for path in [Path(__file__),HERE/'test_inference.py',HERE/'ROOT_GATE.md',gate_path,
        HERE/'source_freeze.json',HERE/'qualification.json',HERE/'actual_inventory.json',
        HERE.parent/'coherent_model/manifest.json',HERE.parent/'coherent_density/manifest.json']:
        bindings[str(path.resolve())]=digest(path)
    verify_bindings(bindings)
    save(HERE/'inference_source_freeze.json',dict(files=bindings,root_gate_path=str(gate_path),
        root_gate_sha256=digest(gate_path),qualification_sha256=digest(HERE/'qualification.json'),
        actual_inventory_sha256=digest(HERE/'actual_inventory.json'),cases=CASES,
        maximum_refit_calls=1000,maximum_refit_seconds=120,maximum_independent_audit_calls=1,
        maximum_combined_objective_calls_per_case=1001,external_TERM_seconds=600,external_KILL_seconds=605,
        new_fit_count=0,held_CFO_scored=False,source_freeze_only=True))


def check_inventory(contexts, inventory):
    if list(contexts)!=list(CASES) or list(inventory['cases'])!=list(CASES):
        raise ValueError('All four exact ordered cases are required')
    for key,ctx in contexts.items():
        plan=inventory['cases'][key]
        for field,actual in [('vector',ctx.vector),('nuisance',ctx.nuisance),('labels',ctx.model.labels)]:
            np.testing.assert_array_equal(actual,np.asarray(plan[field]))
        if bool(ctx.fixed_c)!=key.endswith('zero-c'):raise ValueError('RF arm differs from qualified inventory')
        if ctx.fixed_c and ctx.vector[6]!=0:raise ValueError('c0 seed is not exactly zero')
    first=contexts[CASES[0]]
    for ctx in contexts.values():
        for name in ['numbers','nodes_s','position_km','velocity_km_s']:
            np.testing.assert_array_equal(getattr(first.bank,name),getattr(ctx.bank,name))
        for name in ['window_ids','times_s','measured_hz','rf_hz','receiver','channel','margin']:
            np.testing.assert_array_equal(getattr(first.observations,name),getattr(ctx.observations,name))
        np.testing.assert_array_equal(first.train_mask,ctx.train_mask)
    for arm in ('fitted-c','zero-c'):
        a,b=contexts['independent_'+arm],contexts['automatic_'+arm]
        np.testing.assert_array_equal(a.vector,b.vector);np.testing.assert_array_equal(a.nuisance,b.nuisance)


class AuditCounter:
    """Narrow transparent audit proxy: count independent terminal objectives."""
    def __init__(self, model):self._model=model;self.calls=0
    def __getattr__(self,name):return getattr(self._model,name)
    def evaluate_joint(self,*args,**kwargs):
        if self.calls>=1:raise RuntimeError('Independent terminal audit exceeded one objective')
        self.calls+=1
        return self._model.evaluate_joint(*args,**kwargs)


def fresh_context(context):
    """Pure sequential fitting shares immutable physics, never parameter arrays.

    Public calibration proxies intentionally are not deepcopy-compatible. Their
    complete immutable state is guarded by fingerprints instead of cloning.
    """
    return replace(context,vector=context.vector.copy(),nuisance=context.nuisance.copy(),
        train_mask=context.train_mask.copy())


def execute(contexts, *, output, services, verify_frozen, authorities, preparation):
    """Pure orchestration seam used by owned no-hardware tests; no retry logic."""
    output=Path(output);output.mkdir(exist_ok=False)
    phase,key,completed='startup',None,[]
    original_hashes={case:fingerprint(ctx) for case,ctx in contexts.items()}
    def check_originals():
        if any(fingerprint(ctx)!=original_hashes[case] for case,ctx in contexts.items()):
            raise ValueError('Original qualified context model/input state mutated')
    start=time.monotonic()
    try:
        save(output/'preparation.json',dict(**preparation,case_state_sha256=original_hashes,
            qualified_seeds={case:dict(vector=ctx.vector,nuisance=ctx.nuisance,labels=ctx.model.labels,
                candidate_numbers=ctx.bank.numbers,train_mask=ctx.train_mask) for case,ctx in contexts.items()},
            **authorities,held_CFO_scored=False))
        for key in CASES:
            phase='fit';verify_frozen()
            check_originals()
            ctx=fresh_context(contexts[key]);before=fingerprint(ctx)
            begun=time.monotonic()
            result=services.refit(ctx,ctx.vector.copy(),ctx.nuisance.copy(),
                max_evaluations=MAX_EVALUATIONS,max_seconds=MAX_SECONDS,fixed_c=ctx.fixed_c)
            raw=output/f'raw_{key}.json';save(raw,result)
            if fingerprint(ctx)!=before:raise ValueError('Fit mutated its qualified model/input state')
            check_originals();verify_frozen()
            count=result['diagnostics']['evaluations']
            if not isinstance(count,(int,np.integer)) or not 1<=count<=MAX_EVALUATIONS:
                raise ValueError('Refit violated actual objective-call budget')
            phase='independent_endpoint_audit'
            counter=AuditCounter(ctx.model)
            audit=services.endpoint_status(replace(ctx,model=counter),result['vector'],result['nuisance'])
            if fingerprint(ctx)!=before:raise ValueError('Independent audit mutated model/input state')
            check_originals();verify_frozen()
            policy,arm=key.split('_',1)
            path=output/f'fit_{key}.json'
            save(path,dict(case=key,policy=policy,arm=arm,result=result,independent_endpoint_status=audit,
                raw_result_path=str(raw.resolve()),raw_result_sha256=digest(raw),
                original_seed=dict(vector=ctx.vector,nuisance=ctx.nuisance),original_seed_sha256=original_hashes[key],
                unchanged_state_sha256=fingerprint(ctx),**authorities,
                cost=dict(refit_objective_calls=count,independent_audit_objective_calls=counter.calls,
                    combined_objective_calls=count+counter.calls,maximum_combined_calls=1001,
                    refit_seconds_budget=120.,fit_plus_audit_elapsed_seconds=time.monotonic()-begun),
                held_CFO_scored=False,reference_read=False))
            completed.append(dict(case=key,path=str(path.resolve()),sha256=digest(path)))
        verify_frozen()
        check_originals()
        phase='seal_all_outcomes'
        seal=output/'outcomes_seal.json'
        save(seal,dict(all_four_sealed=True,outcomes=completed,**authorities,
            elapsed_seconds=time.monotonic()-start,held_CFO_scored=False,prediction_not_started=True,
            reference_read=False,refit_call_budget_each=1000,independent_audit_maximum_each=1,
            original_shared_score=dict(clutter_rate=float(contexts[CASES[0]].model.score.clutter_rate),
                detection_budget=float(contexts[CASES[0]].model.score.detection_budget))))
        # Not even excluded metadata preparation occurs until all four immutable
        # terminal outcomes have been sealed. No measured held CFO is requested.
        phase='load_metadata'
        metadata,masks=services.load_metadata()
        if np.any(metadata.measured_hz!=0):raise ValueError('Prediction metadata requires blank CFO')
        metadata_hash=fingerprint((metadata,masks))
        prediction_records=[]
        for key in CASES:
            phase='metadata_prediction';verify_frozen()
            record=read(output/f'fit_{key}.json')
            check_originals();ctx=fresh_context(contexts[key]);before=fingerprint(ctx)
            prediction=services.predict(ctx,np.asarray(record['result']['vector']),
                np.asarray(record['result']['nuisance']),metadata)
            if fingerprint(ctx)!=before or fingerprint((metadata,masks))!=metadata_hash:
                raise ValueError('Metadata prediction mutated frozen state')
            check_originals();verify_frozen()
            path=output/f'predictions_{key}.npz'
            with path.open('xb') as stream:
                np.savez_compressed(stream,observation_id=np.asarray(metadata.window_ids),times_s=metadata.times_s,
                    rf_hz=metadata.rf_hz,receiver=metadata.receiver,channel=metadata.channel,
                    **{name+'_mask':mask for name,mask in masks.items()},**prediction)
            prediction_records.append(dict(case=key,path=str(path.resolve()),sha256=digest(path)))
        phase='seal_all_predictions';verify_frozen()
        save(output/'predictions_seal.json',dict(all_four_sealed=True,predictions=prediction_records,
            outcomes_seal_sha256=digest(seal),metadata_sha256=metadata_hash,**authorities,
            explicit_prediction_calls=4,held_CFO_scored=False,reference_read=False))
    except Exception as error:
        failure=output/'failure.json'
        if not failure.exists():save(failure,dict(phase=phase,case=key,type=type(error).__name__,
            message=str(error),traceback=traceback.format_exc(),completed_outcomes=completed,
            automatic_retry=False,held_CFO_scored=False,**authorities))
        raise


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    loaded=importlib.util.module_from_spec(spec);sys.modules[name]=loaded;spec.loader.exec_module(loaded)
    return loaded


def run(gate_path, *, output=None):
    begun=time.monotonic();gate_path=Path(gate_path).resolve();validate_gate(gate_path)
    frozen=read(HERE/'inference_source_freeze.json')
    if frozen['root_gate_path']!=str(gate_path) or frozen['root_gate_sha256']!=digest(gate_path):
        raise ValueError('Execution source seal binds a different root gate')
    verify=lambda:verify_bindings(frozen['files'])
    verify()
    blocked=REPORTS/'2026_10_17_dsx01_iteration5/blocked_cold'
    sys.path.insert(0,str(blocked));sys.path.insert(0,str(REPORTS/'2026_10_16_dsx01_models'))
    from training_context import load_training_context
    from common import endpoint_status,refit
    adapter=module('coherent_inference_adapter',HERE.parent/'coherent_model/adapter.py')
    ports=module('coherent_inference_ports',HERE/'ports.py')
    base=load_training_context()  # Exactly one original public endpoint replay.
    if len(base.observations.times_s)!=2073 or len(base.bank.numbers)!=45:
        raise ValueError('Exact public TRAIN source required')
    contexts={}
    for arm in ('fitted-c','zero-c'):
        vector=base.vector.copy()
        if arm=='zero-c':vector[6]=0.
        source=replace(base,vector=vector,nuisance=base.nuisance.copy(),fixed_c=arm=='zero-c')
        for policy in ('independent','automatic'):
            contexts[policy+'_'+arm]=adapter.make_context(source,policy=policy,eta=.10,epsilon=.12)
    check_inventory(contexts,read(HERE/'actual_inventory.json'))
    verify()
    def load_metadata():
        fields=('observation_id','time_s','actual_rf_hz','receiver','channel')
        rows=[]
        path=REPORTS/'2026_10_16_dsx01_fast_association_losses/context-observations.jsonl'
        for line in path.read_text().splitlines():
            row=json.loads(line)
            if row['source_id']=='S03':rows.append({name:row[name] for name in fields})
        metadata=ports.metadata_only(rows)
        masks=ports.role_masks(metadata.window_ids,read(blocked/'S03-block20-parity0/derivation.json')['membership'])
        if len(rows)!=3988 or {k:int(v.sum()) for k,v in masks.items()}!={'train':2073,'held':1909,'boundary':6}:
            raise ValueError('Exact3988 metadata/role inventory required')
        np.testing.assert_array_equal(np.asarray(metadata.window_ids)[masks['train']],base.observations.window_ids)
        return metadata,masks
    authorities=dict(root_gate_path=str(gate_path),root_gate_sha256=digest(gate_path),
        qualification_sha256=digest(HERE/'qualification.json'),
        runner_source_freeze_sha256=digest(HERE/'inference_source_freeze.json'))
    execute(contexts,output=output or HERE/'inference_results',verify_frozen=verify,authorities=authorities,
        preparation=dict(public_training_context_loads=1,public_selected_endpoint_replay_calls=1,
            additional_runner_seed_objective_calls=0,qualification_objectives_separate=read(HERE/'qualification.json')['objectives'],
            elapsed_seconds=time.monotonic()-begun,qualified_inventory_exact=True),
        services=SimpleNamespace(refit=refit,endpoint_status=endpoint_status,predict=adapter.predict_coherent,
            load_metadata=load_metadata))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['freeze','run']);parser.add_argument('--gate',required=True,type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.action=='freeze':
        if args.output is not None:parser.error('--output is only valid for run')
        freeze(args.gate)
    else:run(args.gate,output=args.output)
