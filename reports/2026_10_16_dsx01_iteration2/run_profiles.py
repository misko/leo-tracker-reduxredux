"""Bounded parallel research run; original model remains unchanged."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import replace
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_10_16_dsx01_models'))
from common import load_context,refit,measure,challenge_mask,endpoint_status,point_state,save_json,temporal_context
from profile_search import fit,Profiles,timing_vector

_contexts={}


def run(task):
    sid,arm,method,budget,mode=task
    suffix='' if mode=='full' else '-'+mode
    path=HERE/'results'/f'{sid}-{arm}-{method}{suffix}.json'
    if path.exists():
        return dict(task=path.stem,status='existing')
    if sid not in _contexts:
        _contexts[sid]=load_context(sid)
    ctx=_contexts[sid]
    if mode!='full':
        ctx=temporal_context(ctx,mode,fixed_c=arm=='zero-c')
    ctx=replace(ctx,vector=ctx.vector.copy(),fixed_c=arm=='zero-c',deadline=time.monotonic()+120)
    if ctx.fixed_c:
        ctx.vector[6]=0
    if method=='profile':
        result=fit(ctx,max_evaluations=budget,max_seconds=120)
    elif method=='arc':
        from model_a import fit as fit_arc
        result=fit_arc(ctx,max_evaluations=budget,max_seconds=120)
    else:
        result=refit(ctx,ctx.vector,ctx.nuisance,max_evaluations=budget,max_seconds=120)
    v,n=result['vector'],result['nuisance']
    baseline=(ctx.vector,ctx.nuisance)
    mask=challenge_mask(ctx)
    r=dict(source_id=sid,arm=arm,method=method,mode=mode,vector=v,nuisance=n,diagnostics=result['diagnostics'],
           audit=endpoint_status(ctx,v,n),full_scan=measure(ctx,v,n,original=baseline),
           challenge=measure(ctx,v,n,original=baseline,mask=mask),
           outside=measure(ctx,v,n,original=baseline,mask=~mask),source=ctx.source,
           budget=dict(full_objectives=budget,wall_seconds=120))
    if mode!='full':
        r['held']=measure(ctx,v,n,mask=~ctx.train_mask)
        r['held_challenge']=measure(ctx,v,n,mask=mask & ~ctx.train_mask)
        r['validation_qualification']='Neutral training-only seed and zero frozen band contrast; fixed candidate bank conditioned on prior full-recording discovery.'
    ev,_,best,assoc,residual=point_state(ctx.full_model,v,n)
    path.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(path.with_suffix('.npz'),associated=assoc,residual_hz=residual,
                        satellite_number=ctx.bank.numbers[best],times_s=ctx.observations.times_s,
                        train_mask=ctx.train_mask)
    save_json(path,r)
    return dict(source=sid,arm=arm,method=method,mode=mode,associated=r['full_scan']['associated'],
                challenge=r['challenge']['associated'],rms=r['full_scan']['associated_rms_hz'],
                accepted=r['audit']['accepted'],stationarity=r['audit'].get('stationarity'))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--sources',nargs='+',default=['S01','S02','S03','S04','S05'])
    p.add_argument('--arms',nargs='+',default=['fitted-c','zero-c'])
    p.add_argument('--methods',nargs='+',default=['profile','continuation'])
    p.add_argument('--budget',type=int,default=1000)
    p.add_argument('--modes',nargs='+',default=['full'])
    p.add_argument('--workers',type=int,default=6)
    args=p.parse_args()
    tasks=[(s,a,m,args.budget,mode) for mode in args.modes for s in args.sources for a in args.arms for m in args.methods]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(run,t) for t in tasks]):
            print(json.dumps(f.result()),flush=True)


if __name__=='__main__':
    main()
