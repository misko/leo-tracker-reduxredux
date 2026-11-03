"""Bounded matched timing-prior matrix; sealed sigma=2 endpoints are replayed."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
MODELS=REPORTS/'2026_10_16_dsx01_models'
PREVIOUS=REPORTS/'2026_10_16_dsx01_iteration2'
sys.path.insert(0,str(MODELS))
sys.path.insert(0,str(PREVIOUS))
from common import load_context, refit, measure, endpoint_status, challenge_mask, point_state, save_json
from profile_search import fit
from timing_prior import prior_context

_contexts={}


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sigma_label(value):
    return f'{float(value):g}'.replace('.','p')


def reuse_two(context,arm,method,path):
    """Require sealed source/algorithm/budget receipts, not a polished endpoint."""
    origin=PREVIOUS/'results'/f'{context.source_id}-{arm}-{method}.json'
    manifest=json.loads((PREVIOUS/'manifest.json').read_text())
    entries={entry['path']:entry for entry in manifest['files']}
    for target in [origin,origin.with_suffix('.npz'),PREVIOUS/'profile_search.py']:
        key=str(target.relative_to(PREVIOUS))
        if entries[key]['sha256']!=digest(target):
            raise ValueError(f'Sealed sigma=2 artifact changed: {key}')
    common_entry=next(x for x in manifest['inputs'] if x['path']==str(MODELS/'common.py'))
    if common_entry['sha256']!=digest(MODELS/'common.py'):
        raise ValueError('Shared fitting harness differs from sealed sigma=2 run')
    record=json.loads(origin.read_text())
    assert record['source_id']==context.source_id and record['arm']==arm and record['method']==method
    assert record.get('mode','full')=='full'
    assert record['budget']==dict(full_objectives=1000,wall_seconds=120)
    assert record['source']['tracking_input_sha256']==context.source['tracking_input_sha256']
    assert list(record['full_scan']['total_timing_s'])==list(map(str,map(int,context.bank.numbers)))
    assert context.model.score.common_sigma_s==3. and context.model.score.relative_sigma_s==2.
    assert record['diagnostics'].get('orbit_projection_calls',0)<=200
    saved=np.load(origin.with_suffix('.npz'))
    np.testing.assert_array_equal(saved['times_s'],context.observations.times_s)
    path.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(origin.with_suffix('.npz'),path.with_suffix('.npz'))
    record.update(relative_sigma_s=2.,common_sigma_s=3.,reused_sealed_endpoint=True,
        reuse=dict(json_path=str(origin),json_sha256=digest(origin),
                   npz_sha256=digest(origin.with_suffix('.npz')),manifest_sha256=digest(PREVIOUS/'manifest.json')),
        sensitivity_qualification='Reused exact unpolished sigma=2 endpoint with matching sealed source, bank, algorithm and 1000/120 budget.')
    save_json(path,record)
    return record


def run(task):
    sid,width,arm,method=task
    path=HERE/'results'/f'{sid}-sigma{sigma_label(width)}-{arm}-{method}.json'
    if path.exists():return dict(task=path.stem,status='existing')
    begun=time.monotonic()
    if sid not in _contexts:_contexts[sid]=load_context(sid)
    original=_contexts[sid]
    if width==2.:
        r=reuse_two(original,arm,method,path)
    else:
        context=prior_context(original,width,fixed_c=arm=='zero-c')
        context=replace(context,deadline=time.monotonic()+120.)
        if method=='profile':result=fit(context,max_evaluations=1000,max_seconds=120)
        else:result=refit(context,context.vector,context.nuisance,max_evaluations=1000,max_seconds=120,fixed_c=context.fixed_c)
        v,n=result['vector'],result['nuisance'];diag=result['diagnostics']
        assert diag['evaluations']<=1000
        assert diag.get('orbit_projection_calls',0)<=200
        assert context.model.score is context.full_model.score
        assert original.model.score.relative_sigma_s==2.
        mask=challenge_mask(context)
        baseline=(original.vector,original.nuisance)
        r=dict(source_id=sid,relative_sigma_s=width,common_sigma_s=3.,arm=arm,method=method,
            mode='full',vector=v,nuisance=n,diagnostics=diag,audit=endpoint_status(context,v,n),
            full_scan=measure(context,v,n,original=baseline),
            challenge=measure(context,v,n,original=baseline,mask=mask),
            outside=measure(context,v,n,original=baseline,mask=~mask),source=context.source,
            budget=dict(full_objectives=1000,wall_seconds=120,extra_orbit_projection_cap=200),
            prior_control=dict(original_relative_sigma_s=2.,common_sigma_s=3.,
                unchanged='Observed rows, selected bank/order, causal TLE snapshot, other priors, '
                'position/timing/calibration/nuisance bounds and original warm seed; c=0 sets only c to zero.'),
            code_sha256={name:digest(HERE/name) for name in ['timing_prior.py','run_timing.py']},
            upstream_code_sha256={str(p):digest(p) for p in [MODELS/'common.py',PREVIOUS/'profile_search.py']},
            elapsed_including_preparation_seconds=time.monotonic()-begun,
            sensitivity_qualification='Full-data warm-start development prior sensitivity, not validation. '
            'Objectives differ across priors; compare frequency NLL, coverage, support losses and position separately. '
            'Configured station coordinates never enter a seed, objective or selection.')
        _,_,best,assigned,residual=point_state(context.full_model,v,n)
        path.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(path.with_suffix('.npz'),associated=assigned,residual_hz=residual,
            satellite_number=context.bank.numbers[best],times_s=context.observations.times_s)
        save_json(path,r)
    return dict(task=path.stem,status='complete',source_id=sid,relative_sigma_s=width,
        arm=arm,method=method,associated=r['full_scan']['associated'],challenge=r['challenge']['associated'],
        lost=r['full_scan'].get('lost_associations'),rms=r['full_scan']['associated_rms_hz'],
        relative_rms_s=r['full_scan']['relative_timing_rms_s'],
        configured_reference_km=r['full_scan'].get('configured_reference_distance_km'),
        accepted=r['audit']['accepted'],stationarity=r['audit'].get('stationarity'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',nargs='+',default=['S01','S02','S03','S04','S05'])
    parser.add_argument('--sigmas',nargs='+',type=float,choices=[2.,1.,.5],default=[2.,1.,.5])
    parser.add_argument('--arms',nargs='+',choices=['fitted-c','zero-c'],default=['fitted-c','zero-c'])
    parser.add_argument('--methods',nargs='+',choices=['profile','continuation'],default=['profile','continuation'])
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    tasks=[[(sid,width,arm,method) for width in args.sigmas
            for arm in args.arms for method in args.methods] for sid in args.sources]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run_source,task) for task in tasks]):
            print(json.dumps(future.result()),flush=True)


def run_source(tasks):
    for task in tasks:
        print(json.dumps(run(task)),flush=True)
    return dict(source_id=tasks[0][0],source_batch='complete',records=len(tasks))


if __name__=='__main__':main()
