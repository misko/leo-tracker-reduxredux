"""Paired, separately labelled original-catalogue restoration experiment."""
import argparse
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
from common import load_context,refit,measure,challenge_mask,endpoint_status,point_state,save_json
from bank_expansion import regional_bank,expandable_context
from profile_search import fit


def run(task):
    sid,arm,method=task
    path=HERE/'expanded-results'/f'{sid}-{arm}-{method}.json'
    if path.exists():
        return dict(task=path.stem,status='existing')
    begun=time.monotonic()
    original=load_context(sid)
    selection_path=HERE/f'candidate_screen_{sid}.json'
    selected=json.loads(selection_path.read_text())
    assert selected['authority']['tle_sha256']==original.source['tle_sha256']
    assert selected['authority']['tle_collected_utc_ns']==original.source['tle_collected_utc_ns']
    regional,authority=regional_bank(original,return_receipt=True)
    context,transport=expandable_context(original,selected['selected_ids'],regional=regional)
    v=context.vector.copy()
    if arm=='zero-c':
        v[6]=0
    context=replace(context,vector=v,fixed_c=arm=='zero-c')
    seed=(context.vector.copy(),context.nuisance.copy())
    initial=measure(context,*seed)
    preparation=time.monotonic()-begun
    context=replace(context,deadline=time.monotonic()+120)
    if method=='profile':
        result=fit(context,max_evaluations=1000,max_seconds=120)
    else:
        result=refit(context,*seed,max_evaluations=1000,max_seconds=120)
    v,n=result['vector'],result['nuisance']
    mask=challenge_mask(context)
    record=dict(source_id=sid,method=method,mode='full',arm=arm,experiment='expanded-original-catalogue',
        vector=v,nuisance=n,diagnostics=result['diagnostics'],audit=endpoint_status(context,v,n),
        full_scan=measure(context,v,n,original=seed),challenge=measure(context,v,n,mask=mask),
        outside=measure(context,v,n,mask=~mask),expanded_seed=initial,source=context.source,
        bank_additions=selected['selected_ids'],bank_transport=transport,bank_authority=authority,
        selection_receipt_sha256='sha256:'+hashlib.sha256(selection_path.read_bytes()).hexdigest(),
        preparation_seconds=preparation,budget=dict(full_objectives=1000,wall_seconds=120),
        qualification='Added candidates selected on fitted-c training data; identical additions for both RF arms. Within-record original metrics are relative to expanded transported seed, not old-bank endpoint. Full population unchanged.')
    _,_,best,associated,residual=point_state(context.full_model,v,n)
    path.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(path.with_suffix('.npz'),associated=associated,residual_hz=residual,
        satellite_number=context.bank.numbers[best],times_s=context.observations.times_s)
    save_json(path,record)
    return dict(source=sid,arm=arm,method=method,associated=record['full_scan']['associated'],
                challenge=record['challenge']['associated'],accepted=record['audit']['accepted'])


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--sources',nargs='+',default=['S01','S05'])
    p.add_argument('--workers',type=int,default=4)
    args=p.parse_args()
    tasks=[(s,a,m) for s in args.sources for a in ['fitted-c','zero-c'] for m in ['profile','continuation']]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(run,t) for t in tasks]):
            print(json.dumps(f.result()),flush=True)


if __name__=='__main__':
    main()
