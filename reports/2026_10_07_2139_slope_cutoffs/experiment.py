"""Controlled hard-slope tests including the previously omitted anchor basin."""

import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'2026_10_07_slope_priors'
sys.path.insert(0,str(OLD))
import run as common
import polish as old_polish
from leo.analysis.regional_position_score import circular

DEBUG = HERE.parent/'2026_10_07_cone_failure_debug'
ANCHOR = DEBUG/'paired_background/anchor_results.json'
PAIR = DEBUG/'paired_identity/2139.json'
SECONDS = 20.
ITERATIONS = 600


def read(path):
    return json.loads(path.read_text())


def pair_metrics(obj, vector, pairs):
    left,right = pairs.T
    obs = obj.observations
    correction = obj.design@np.asarray(vector)[2:7] + obj.baseline
    residual = circular(obs.measured_hz[right]-obs.measured_hz[left]-correction[right]+correction[left])
    times = (obs.times_s[left]+obs.times_s[right])/2
    design = np.column_stack([*[(obs.channel[left]==c) for c in np.unique(obs.channel[left])],times-times.mean()])
    center = float(np.median(residual))
    residual = center+circular(residual-center)
    beta = np.linalg.lstsq(design,np.full(len(residual),center),rcond=None)[0]
    for _ in range(100):
        weights = np.minimum(1.,100/np.maximum(abs(residual-design@beta),1e-12))
        updated = np.linalg.lstsq(design*np.sqrt(weights[:,None]),residual*np.sqrt(weights),rcond=None)[0]
        if max(abs(updated-beta))<1e-8:
            beta=updated
            break
        beta=updated
    return dict(count=len(pairs),median_absolute_residual_hz=float(np.median(abs(residual))),
                p90_absolute_residual_hz=float(np.quantile(abs(residual),.9)),robust_residual_slope_hz_s=float(beta[-1]))


def freeze_inputs():
    manifest_path = OLD/'inputs/manifest.json'
    case = next(c for c in read(manifest_path)['cases'] if c['case']=='2139')
    anchor = next(c for c in read(ANCHOR)['cases'] if c['case']=='2139')
    pair_doc = read(PAIR)
    original_pairs_path = DEBUG/'identity/paired_topone.json'
    assert hashlib.sha256(original_pairs_path.read_bytes()).hexdigest()==pair_doc['source_hashes'][str(original_pairs_path)]
    pairs = np.asarray(pair_doc['pair_rows'],int)
    expected = np.asarray([[r['row0'],r['row1']] for r in read(original_pairs_path)['cases']['2139']['100ns']['rows']])
    np.testing.assert_array_equal(pairs,expected)
    for key in ['input','analysis']:
        assert anchor[key+'_sha256']==case[key+'_manifest_sha256']
    assert anchor['evidence_sha256']==case['evidence_sha256']
    objectives = {basin:common.load_objective(manifest_path.parent,case,basin,'V16') for basin in case['basins']}
    obj = objectives[anchor['basin']]
    left,right=pairs.T
    assert len(pairs)==236
    assert np.all(obj.observations.receiver[left]==0) and np.all(obj.observations.receiver[right]==1)
    np.testing.assert_array_equal(obj.observations.rf_hz[left],obj.observations.rf_hz[right])
    for row in anchor['runs']+anchor['selections']:
        if row['model']!='independent': continue
        val,_,_=obj.evaluate(np.asarray(row['vector']))
        np.testing.assert_allclose(val,row['objective'],atol=1e-6,rtol=0)
        calculated = pair_metrics(obj,row['vector'],pairs)
        for key,val in row['pair_clock'].items():
            np.testing.assert_allclose(calculated[key],val,atol=1e-6,rtol=0)
    return case,anchor,pairs,objectives


def seed_pool(region, basin, arm, anchor):
    initial=np.asarray(region['initial_vector'],float)
    answer=[('association',initial.copy()),('zero-timing',np.r_[initial[:7],np.zeros(len(initial)-7)])]
    if basin==anchor['basin']:
        init=anchor['initializers'][arm]
        answer.append(('pre-repair-own-state',np.asarray(init['original_vector'],float)))
        for label,row in init['anchors'].items():
            answer.append((label,np.asarray(row['vector'],float)))
    for _,v in answer:
        if arm=='zero-c': v[6]=0.
    return answer


def project(vector,width,prior_radius,center):
    v=old_polish.inside(vector,prior_radius,center)
    if width is not None: v[[3,5]]=np.clip(v[[3,5]],-width,width)
    return v


def choose(rows,arm,basin=None):
    return min((r for r in rows if r['arm']==arm and r['feasible'] and (basin is None or r['basin']==basin)),
               key=lambda r:(r['selection_score'],r['basin'],r['origin']))


def run(option):
    width=common.OPTIONS[option]
    target=HERE/option
    target.mkdir(exist_ok=True)
    if (target/'progress.json').exists() or (target/'results.json').exists(): raise FileExistsError(target)
    case,anchor,pairs,objects=freeze_inputs()
    source_paths=[Path(__file__),HERE/'protocol.txt',OLD/'run.py',OLD/'bounded_fit.py',OLD/'polish.py',
                  OLD/'inputs/manifest.json',ANCHOR,PAIR]
    hashes={str(p):common.digest(p.read_bytes()) for p in source_paths}
    begun=time.monotonic()
    out=dict(status='running',option=option,slope_half_width_hz_s=width,case='2139',session_id=case['session_id'],
             relative_sigma_s=1.,seconds_per_fit=SECONDS,maximum_iterations=ITERATIONS,method='V16',
             source_hashes=hashes,anchor_basin=anchor['basin'],basins=case['basins'],pair_count=len(pairs),
             scope='Three frozen regions, including earlier repaired region; matched widths and arms',
             seeds=[],runs=[],candidates=[],selections=[],regional_selections=[],by_start=[],nested_c_gaps=[])

    def save():
        temporary=target/'progress.tmp'
        temporary.write_text(json.dumps(out,indent=2,default=common.encode,allow_nan=False)+'\n')
        temporary.replace(target/'progress.json')

    def record(vector,basin,arm,origin,**metadata):
        row=common.candidate(objects[basin],case['basins'][basin],vector,option,arm,basin,'V16',origin,
                             case='2139',**metadata)
        row['pair_clock']=pair_metrics(objects[basin],vector,pairs)
        return row

    def fit_one(seed,basin,arm,label,stage):
        obj=objects[basin];region=case['basins'][basin]
        original=np.asarray(seed).copy()
        v=project(original,width,obj.prior.radius_km,region['center_km'])
        metadata=dict(stage=stage,seed_label=label,shared_seed_sha256=common.vector_digest(original),
                      seed_sha256=common.vector_digest(v),fixture_sha256=region['sha256'])
        out['seeds'].append(dict(basin=basin,arm=arm,vector=v,unprojected_vector=original,**metadata))
        first=record(v,basin,arm,'initial:'+stage+':'+label,**metadata)
        if first['feasible']:out['candidates'].append(first)
        started=time.monotonic()
        try:
            fit=common.fit_position(obj,v,rf_arm=arm,maximum_seconds=SECONDS,maximum_iterations=ITERATIONS,
                                    local_center=np.asarray(region['center_km']),local_radius_km=25.,slope_half_width_hz_s=width)
        except (ValueError,TimeoutError,ArithmeticError) as error:
            out['runs'].append(dict(status='failed',option=option,basin=basin,arm=arm,elapsed_s=time.monotonic()-started,
                                    error=f'{type(error).__name__}: {error}',**metadata));save();return
        row=record(fit.vector,basin,arm,'fit:'+stage+':'+label,status='complete',elapsed_s=fit.elapsed_s,
                   evaluations=fit.evaluations,stop_reason=fit.stop_reason,solver_stationarity=fit.stationarity,**metadata)
        np.testing.assert_allclose(row['objective'],fit.objective,atol=1e-6,rtol=0)
        np.testing.assert_allclose(row['stationarity'],fit.stationarity,atol=1e-5,rtol=0)
        out['runs'].append(row)
        if row['feasible']:out['candidates'].append(row)
        save()
        print(option,basin,arm,stage,label,round(row['selection_score'],3),row['converged'],
              round(row['pair_clock']['median_absolute_residual_hz'],2),flush=True)

    # Existing anchor endpoints provide a feasibility-checked floor in every arm/window.
    for old in anchor['runs']:
        if old['model']!='independent':continue
        obj=objects[anchor['basin']]
        audit=common.audit(np.asarray(old['vector']),np.zeros(obj.size),obj,old['arm'],anchor['center'],width)
        if audit['feasible']:
            row=record(old['vector'],anchor['basin'],old['arm'],'archived-independent:'+old['origin'])
            out['candidates'].append(row)
    save()
    for basin,region in case['basins'].items():
        for arm in common.ARMS:
            for label,seed in seed_pool(region,basin,arm,anchor): fit_one(seed,basin,arm,label,'primary')
    for basin in case['basins']:
        for arm in common.ARMS:
            selected=choose(out['candidates'],arm,basin)
            fit_one(selected['vector'],basin,arm,'own-best','continuation')
    for arm in common.ARMS:
        out['selections'].append(choose(out['candidates'],arm))
        for basin in case['basins']:
            out['regional_selections'].append(choose(out['candidates'],arm,basin))
        for label in ['pre-repair-own-state','anchor-rx0','anchor-rx1']:
            pool=[r for r in out['candidates'] if r.get('stage')=='primary' and r.get('seed_label')==label]
            if any(r['arm']==arm for r in pool):out['by_start'].append(choose(pool,arm,anchor['basin']))
    for basin in [None,*case['basins']]:
        z,f=[choose(out['candidates'],arm,basin) for arm in ['zero-c','fitted-c']]
        out['nested_c_gaps'].append(dict(basin=basin,gap=max(0.,f['selection_score']-z['selection_score'])))
    # Reference metadata is consulted only after all score-based selection finishes.
    ref=case['evaluation_reference'];a,b=np.radians([ref['latitude_deg'],ref['longitude_deg']])
    for row in out['candidates']:
        lat,lon=np.radians(common.coordinates(objects[row['basin']].prior,row['vector'][:2]))
        h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
        row['horizontal_error_m']=float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
    out.update(status='complete',elapsed_s=time.monotonic()-begun,fit_elapsed_s=sum(r['elapsed_s'] for r in out['runs']))
    save();(target/'results.json').write_text(json.dumps(out,indent=2,default=common.encode,allow_nan=False)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--option',required=True,choices=common.OPTIONS)
    run(parser.parse_args().option)
