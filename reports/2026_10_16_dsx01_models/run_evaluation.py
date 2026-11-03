"""Bounded parallel fixed-bank comparison; each result is independently saved."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import importlib
import hashlib
import json
from pathlib import Path
import time
import traceback

import numpy as np

from common import (HERE, DATASET, load_context, temporal_context, refit, measure,
                    challenge_mask, endpoint_status, save_json, point_state)


_contexts = {}


def execute(task):
    source_id, method, arm, mode, maximum, seconds, output = task
    name = f'{source_id}-{mode}-{arm}-{method}'
    out = Path(output)/f'{name}.json'
    if out.exists():
        return dict(task=name,status='existing',path=str(out))
    begun = time.monotonic()
    try:
        if source_id not in _contexts:
            _contexts[source_id] = load_context(source_id)
        original = _contexts[source_id]
        zero = arm == 'zero-c'
        if mode == 'full':
            v = original.vector.copy()
            if zero:
                v[6] = 0.
            context = replace(original,vector=v,nuisance=original.nuisance.copy(),fixed_c=zero)
        else:
            context = temporal_context(original,mode,fixed_c=zero)
        original_state = (original.vector,original.nuisance)
        mask = challenge_mask(context)
        if method == 'original':
            result = dict(vector=original.vector,nuisance=original.nuisance,
                          diagnostics=dict(reason='immutable saved endpoint; no fit'))
        else:
            context = replace(context,deadline=time.monotonic()+seconds)
            fn = refit if method == 'continuation' else importlib.import_module('model_'+method.lower()).fit
            if method == 'continuation':
                result = fn(context,context.vector,context.nuisance,max_evaluations=maximum,max_seconds=seconds)
            else:
                result = fn(context,max_evaluations=maximum,max_seconds=seconds)
        v,n = result['vector'],result['nuisance']
        audit = endpoint_status(context,v,n)
        record = dict(task=name,source_id=source_id,method=method,arm=arm,mode=mode,
            budget=dict(max_evaluations=maximum,max_seconds=seconds),
            inference_diagnostics=result['diagnostics'],endpoint_audit=audit,
            full_scan=measure(context,v,n,original=original_state if mode=='full' else None),
            challenge=measure(context,v,n,original=original_state if mode=='full' else None,mask=mask),
            outside_challenge=measure(context,v,n,original=original_state if mode=='full' else None,mask=~mask),
            source_receipt=context.source,vector=v,nuisance=n,
            evaluation_calls_outside_inference_budget='baseline replay, metrics, independent endpoint audit; never used for fitting/selection',
            elapsed_including_replay_seconds=time.monotonic()-begun)
        code_files = ['common.py','run_evaluation.py','EVALUATION.md']
        if method in ('A','B','C'):
            code_files.append('model_'+method.lower()+'.py')
        record['code_sha256'] = {p:'sha256:'+hashlib.sha256((HERE/p).read_bytes()).hexdigest() for p in code_files}
        record['dataset_sha256'] = 'sha256:'+hashlib.sha256((DATASET/'dataset.json').read_bytes()).hexdigest()
        _,_,best,associated,residual = point_state(context.full_model,v,n)
        np.savez_compressed(out.with_suffix('.npz'),associated=associated,residual_hz=residual,
                            satellite_number=context.bank.numbers[best],train_mask=context.train_mask,
                            challenge_mask=mask,times_s=context.observations.times_s)
        if mode != 'full':
            record['held'] = measure(context,v,n,mask=~context.train_mask)
            record['held_challenge'] = measure(context,v,n,mask=mask & ~context.train_mask)
            record['validation_qualification'] = 'neutral training-only seeds; zero frozen band contrast; candidate bank conditioned on original full-recording discovery'
        save_json(out,record)
        return dict(task=name,status='complete',associated=record['full_scan']['associated'],
                    rms_hz=record['full_scan']['associated_rms_hz'],accepted=audit['accepted'])
    except Exception as error:
        failure = dict(task=name,source_id=source_id,method=method,arm=arm,mode=mode,
                       status='failed',error_type=type(error).__name__,error=str(error),traceback=traceback.format_exc())
        save_json(out,failure)
        return failure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources',nargs='+',default=['S01','S02','S03','S04','S05'])
    parser.add_argument('--methods',nargs='+',default=['original','continuation','A','B','C'])
    parser.add_argument('--arms',nargs='+',default=['fitted-c','zero-c'])
    parser.add_argument('--modes',nargs='+',default=['full'])
    parser.add_argument('--workers',type=int,default=6)
    parser.add_argument('--max-evaluations',type=int,default=180)
    parser.add_argument('--seconds',type=float,default=120.)
    parser.add_argument('--output',type=Path,default=HERE/'results')
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    tasks = [(s,m,a,mode,args.max_evaluations,args.seconds,str(args.output))
             for mode in args.modes for a in args.arms for s in args.sources for m in args.methods
             if m != 'original' or (a=='fitted-c' and mode=='full')]
    begun = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(execute,t) for t in tasks]
        for future in as_completed(futures):
            print(json.dumps(future.result()),flush=True)
    print(json.dumps(dict(finished_tasks=len(tasks),elapsed_seconds=time.monotonic()-begun)),flush=True)


if __name__ == '__main__':
    main()
