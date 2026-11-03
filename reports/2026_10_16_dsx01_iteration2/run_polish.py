"""Uniform numerical cleanup of failed audits using only unspent allowances."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_10_16_dsx01_models'))
from common import load_context,temporal_context,endpoint_status,point_state,save_json
from bank_expansion import regional_bank,expandable_context
from endpoint_polish import polish


def run(parent_path):
    parent_path=Path(parent_path)
    parent=json.loads(parent_path.read_text())
    name=parent_path.parent.name+'-'+parent_path.stem
    path=HERE/'polished-results'/f'{name}.json'
    if path.exists():
        return dict(task=name,status='existing')
    used=parent['diagnostics']['evaluations']
    elapsed=parent['diagnostics'].get('elapsed_seconds',parent['diagnostics'].get('elapsed_s',120.))
    maximum=min(134,1000-used)
    seconds=min(78.,120.-elapsed)
    if maximum<1 or seconds<=0:
        save_json(path,dict(parent_path=str(parent_path),status='skipped-exhausted-allowance',
                           parent_evaluations=used,parent_elapsed_seconds=elapsed))
        return dict(task=name,status='skipped-exhausted-allowance')
    ctx=load_context(parent['source_id'])
    mode=parent.get('mode','full')
    if mode!='full':
        ctx=temporal_context(ctx,mode,fixed_c=parent['arm']=='zero-c')
    if parent.get('experiment')=='expanded-original-catalogue':
        regional=regional_bank(ctx)
        ctx,_=expandable_context(ctx,parent['bank_additions'],regional=regional)
    v,n=np.array(parent['vector']),np.array(parent['nuisance'])
    ctx=replace(ctx,vector=v,nuisance=n,fixed_c=parent['arm']=='zero-c',deadline=time.monotonic()+seconds)
    result=polish(ctx,v,n,max_evaluations=maximum,max_seconds=seconds,
                  expected_objective=parent['audit']['training_objective'])
    audit=endpoint_status(ctx,result['vector'],result['nuisance'])
    _,_,best,assigned,residual=point_state(ctx.full_model,result['vector'],result['nuisance'])
    old=np.load(parent_path.with_suffix('.npz'))
    record=dict(parent_path=str(parent_path),parent_sha256='sha256:'+hashlib.sha256(parent_path.read_bytes()).hexdigest(),
        source_id=parent['source_id'],arm=parent['arm'],method=parent['method'],mode=mode,
        experiment=parent.get('experiment','fixed-bank'),parent_audit=parent['audit'],audit=audit,
        vector=result['vector'],nuisance=result['nuisance'],diagnostics=result['diagnostics'],
        total_inference_calls=used+result['diagnostics']['evaluations'],
        total_inference_seconds=elapsed+result['diagnostics']['total_elapsed_seconds'],
        membership_changes=int(np.sum(assigned!=old['associated'])),
        qualification='Uniform failed-audit cleanup with unused original allowance only; original endpoint is immutable. Independent audit/scoring are outside inference.')
    save_json(path,record)
    np.savez_compressed(path.with_suffix('.npz'),associated=assigned,residual_hz=residual,
                        satellite_number=ctx.bank.numbers[best],times_s=ctx.observations.times_s)
    return dict(task=name,accepted=audit['accepted'],stationarity=audit.get('stationarity'),
                total_calls=record['total_inference_calls'],membership_changes=record['membership_changes'])


def main():
    parents=[p for folder in ['results','expanded-results'] for p in (HERE/folder).glob('*.json')
             if not json.loads(p.read_text())['audit']['accepted']]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(run,str(p.resolve())) for p in parents]):
            print(json.dumps(future.result()),flush=True)


if __name__=='__main__':
    main()
