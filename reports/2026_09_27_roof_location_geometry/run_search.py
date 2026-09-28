"""Bounded independent-prior geographic search, with no truth input to search.

Research orchestration only. All source-store interactions use public ports;
cached TrackingInput objects are local, digest-verified analysis artifacts.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import pickle
import sys
import time

import numpy as np

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_27_roof_direction_subset'
sys.path.insert(0,str(SOURCE))
import model_eval
from location_core import train_shortlist,doppler_heldout_score,reception_geometry_score
from leo.analysis.adaptive_tle_prediction import ReceiverPoint,RegionalTrackPredictionEvaluator,build_prediction_banks
from leo.analysis.adaptive_tle_position import AdaptivePointScore,adaptive_best_first_search
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km

PRIORS={'sacramento':(38.5816,-121.4944,250.),'reno':(39.5296,-119.8138,500.)}
LEVELS=(100.,50.,25.,12.5,6.25,3.125,1.5625)
ARMS=('D','D_plus_geometry')


def digest(data):return 'sha256:'+hashlib.sha256(data).hexdigest()


def atomic(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');tmp.replace(path)


def coordinates(latitude,longitude,east,north):
    angle=np.hypot(east,north)/6371.0088;bearing=np.arctan2(east,north)
    lat0,lon0=np.deg2rad([latitude,longitude])
    lat=np.arcsin(np.sin(lat0)*np.cos(angle)+np.cos(lat0)*np.sin(angle)*np.cos(bearing))
    lon=lon0+np.arctan2(np.sin(bearing)*np.sin(angle)*np.cos(lat0),np.cos(angle)-np.sin(lat0)*np.sin(lat))
    return float(np.rad2deg(lat)),float((np.rad2deg(lon)+180)%360-180)


def point(latitude,longitude):
    lat,lon=np.deg2rad([latitude,longitude])
    return ReceiverPoint(geodetic_to_ecef_km(latitude,longitude,0),np.array([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)]))


class CachedInput:
    def __init__(self,raw):self.raw=raw
    def load(self,sid):
        if sid!=self.raw.session_id:raise KeyError(sid)
        return self.raw


def frozen_models_and_endpoints():
    payload=(SOURCE/'model_rows.json').read_bytes(); original=json.loads(payload)
    cal=[r for r in original if r['split']=='cal']
    d=model_eval.fit_detection_models(cal)['M1'];c=model_eval.fit_continuous_models(cal)['M1']
    prior=json.loads((SOURCE/'results.json').read_text())
    for key,fit in [('detection',d),('continuous',c)]:
        if not np.array_equal(fit.coefficients,prior[key]['models']['M1']['coefficients']):
            raise ValueError('reception calibration changed from frozen feasibility model')
    matched=[r for r in cal if r['matched']]
    residual=np.asarray([r['log_margin_ratio_rx1_rx0'] for r in matched])-model_eval.predict(c,matched)
    weights=np.asarray(model_eval.track_weights(matched))
    ratio_variance=float(np.sum(weights*residual**2)/weights.sum())
    if ratio_variance<=0:raise ValueError('invalid calibration ratio variance')
    # Strip every truth-derived direction/candidate field before search input.
    allowed=('session_id','track_id','observation_id','receiver_id','channel','edge','sample_rate_hz','anchor_margin','matched','log_margin_ratio_rx1_rx0')
    endpoints=defaultdict(list)
    for r in original:
        if r['split']!='holdout':continue
        clean={k:r[k] for k in allowed};clean.update(split='holdout',east=0.,up=0.)
        endpoints[r['session_id']].append(clean)
    calibration=dict(detection=asdict(d),ratio=asdict(c),ratio_variance=ratio_variance,
        calibration_sessions=sorted({r['session_id'] for r in cal}),
        source_model_rows_sha256=digest(payload),
        source_results_sha256=digest((SOURCE/'results.json').read_bytes()))
    return d,c,ratio_variance,endpoints,json.loads(json.dumps(calibration))


def reception_inputs(prepared,rows,dmodel,cmodel):
    grouped=defaultdict(list)
    d0=model_eval.predict(dmodel,rows);c0=model_eval.predict(cmodel,rows)
    ds=dmodel.coefficients[dmodel.feature_names.index('signed_east')]/dmodel.scales[dmodel.numeric_names.index('signed_east')]
    cs=cmodel.coefficients[cmodel.feature_names.index('east')]/cmodel.scales[cmodel.numeric_names.index('east')]
    tracks={t.track_id:t for t in prepared.tracks}
    lookup={tid:{oid:i for i,oid in enumerate(t.observation_ids)} for tid,t in tracks.items()}
    for r,pred,mean in zip(rows,d0,c0,strict=True):
        tid=r['track_id'];i=lookup[tid][r['observation_id']]
        if tracks[tid].training_mask[i]:raise ValueError('reception observation overlaps Doppler fit')
        grouped[tid].append(dict(observation_index=i,matched=r['matched'],
            detection_logit_east0=float(np.log(pred)-np.log1p(-pred)),
            detection_east_slope=float(ds*(1 if r['receiver_id']=='rx0' else -1)),
            ratio_mean_east0=float(mean),ratio_east_slope=float(cs),
            log_margin_ratio_rx1_rx0=r['log_margin_ratio_rx1_rx0']))
    if set(grouped)!=set(tracks):raise ValueError('reception endpoint does not cover every track')
    for tid,t in tracks.items():
        if {r['observation_index'] for r in grouped[tid]}!=set(np.flatnonzero(~t.training_mask)):
            raise ValueError('reception endpoint is incomplete or duplicated')
    return dict(grouped)


class BranchEvaluator:
    def __init__(self,banks,origin,reception,ratio_variance):
        self.banks={b.source.track_id:b for b in banks}
        self.index={tid:{int(cid):i for i,cid in enumerate(b.candidate_ids)} for tid,b in self.banks.items()}
        self.origin=origin;self.reception=reception;self.ratio_variance=ratio_variance
        self.predictions=RegionalTrackPredictionEvaluator(banks,lambda e,n:point(*coordinates(*origin,e,n)),taus_s=np.array([0.]))
        self.cache={};self.started=time.monotonic()

    def evaluate(self,east,north):
        key=(float(east),float(north))
        if key in self.cache:return self.cache[key]
        lat,lon=coordinates(*self.origin,*key);receiver=point(lat,lon).ecef_km
        east_axis=np.array([-np.sin(np.deg2rad(lon)),np.cos(np.deg2rad(lon)),0.])
        blocks=defaultdict(list)
        for b in self.predictions(*key):blocks[b.track_id].append(b)
        totals=defaultdict(float);weight_sum=0;details=[]
        for tid,bank in self.banks.items():
            bb=blocks[tid];t=bank.source
            pred=np.concatenate([b.predictions_hz[:,0,:] for b in bb])
            ids=np.concatenate([b.candidate_ids for b in bb])
            visible=np.concatenate([b.visible for b in bb])
            # Global catalogue ranking at this point, not another prior's shortlist.
            shortlist=train_shortlist(pred,t.measured_hz,t.training_mask,visible)
            ix=np.asarray(shortlist['candidate_indices']);chosen_ids=ids[ix]
            selected_pred=pred[ix]
            short=dict(shortlist,candidate_indices=list(range(len(ix))))
            positions=bank.position_km[[self.index[tid][int(cid)] for cid in chosen_ids],0,:,:]
            delta=positions-receiver;unit=delta/np.linalg.norm(delta,axis=-1,keepdims=True)
            u_east=np.sum(unit*east_axis,axis=-1)
            doppler=doppler_heldout_score(selected_pred,t.measured_hz,t.training_mask,short)
            rx=reception_geometry_score(u_east,short,self.reception[tid],ratio_variance=self.ratio_variance)
            reverse=reception_geometry_score(-u_east,short,self.reception[tid],ratio_variance=self.ratio_variance)
            d=doppler['mean_nll'];r=rx['detection_mean_nll'];c=rx['conditional_ratio_mean_nll']
            values=dict(D=d,D_plus_detection=d+r,D_plus_geometry=d+r+c,
                        D_plus_reversed_geometry=d+reverse['detection_mean_nll']+reverse['conditional_ratio_mean_nll'],
                        detection=r,conditional_ratio=c)
            weight=len(np.unique(np.floor(t.times_s)))
            for name,value in values.items():totals[name]+=weight*value
            weight_sum+=weight
            details.append(dict(track_id=tid,weight_seconds=weight,candidate_ids=chosen_ids.astype(int).tolist(),
                                weights=short['weights'],training_rms_hz=short['training_rms_hz'],
                                map_test_rms_hz=doppler['map_heldout_rms_hz'],scores=values))
        row=dict(east_km=key[0],north_km=key[1],latitude_deg=lat,longitude_deg=lon,
                 scores={k:v/weight_sum for k,v in totals.items()},weight_seconds=weight_sum,tracks=details)
        self.cache[key]=row
        if len(self.cache)%20==0:
            print('POINTS',self.origin,len(self.cache),'seconds',round(time.monotonic()-self.started,1),flush=True)
        return row

    def for_arm(self,arm):
        def evaluate(points):
            result=[]
            for e,n in points:
                r=self.evaluate(e,n);score=r['scores'][arm]
                result.append(AdaptivePointScore(float(e),float(n),score,float(np.sqrt(max(score,0))),0,len(self.banks),len(self.banks),0,()))
            return tuple(result)
        return evaluate


def run_scan(index,budget):
    start=time.monotonic()
    inventory=json.loads((SOURCE/'evaluation_inventory.json').read_text())
    holdout=[x for x in inventory if x['split']=='holdout'];entry=holdout[index];sid=entry['session_id']
    target=HERE/f'search-{sid}.json'
    if target.exists():raise FileExistsError('search output already exists; review before rerunning')
    payload=Path(entry['cache_file']).read_bytes()
    if digest(payload)!=entry['cache_sha256']:raise ValueError('tracking input cache digest mismatch')
    raw=pickle.loads(payload)
    d,c,var,endpoints,cal=frozen_models_and_endpoints()
    frozen=HERE/'calibration.json'
    if frozen.exists() and json.loads(frozen.read_text())!=cal:raise ValueError('frozen calibration changed')
    if not frozen.exists():atomic(frozen,cal)
    p=prepare_adaptive_tle_position_inputs(sid,inputs=CachedInput(raw),archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    reception=reception_inputs(p,endpoints[sid],d,c)
    banks,receipt=build_prediction_banks(p.catalogue,p.candidate_indices,p.start_utc_ns,p.tracks,taus_s=np.array([0.]))
    print('BANK_READY',sid,'seconds',round(time.monotonic()-start,1),flush=True)
    out=dict(session_id=sid,protocol=dict(priors=PRIORS,levels_km=LEVELS,budget_per_arm=budget,arms=ARMS,
        frequency_sigma_hz=100,timing_s=0,top_k=3,track_weight='occupied one-second bins',
        geometry='frozen detection likelihood plus conditional ratio likelihood; unit composite coefficients',
        truth_access='none; final error scoring is a separate script after searches finish',
        candidate_policy='full causal catalogue evaluated independently at every location within each prior; no branch-local shortlist or coordinates shared'),
        evidence_sha256=p.evidence_sha256,snapshot_digest=p.snapshot_digest,input_manifest_sha256=p.input_manifest_sha256,
        analysis_manifest_sha256=p.analysis_manifest_sha256,calibration_sha256=digest(frozen.read_bytes()),
        prediction_receipt=asdict(receipt),tracks=len(p.tracks),branches={})
    for name,(lat,lon,radius) in PRIORS.items():
        evaluator=BranchEvaluator(banks,(lat,lon),reception,var)
        branch=dict(origin=[lat,lon],radius_km=radius,arms={})
        for arm in ARMS:
            result=adaptive_best_first_search(evaluator.for_arm(arm),radius_km=radius,levels_km=LEVELS,budget_points=budget)
            selected=result.global_incumbent
            chosen=evaluator.cache[(selected.east_km,selected.north_km)]
            branch['arms'][arm]=dict(selected=chosen,stop_reason=result.stop_reason,complete=result.complete,
                evaluated_points=len(result.all_evaluations),finest_points=len(result.finest_evaluations),
                selection='global best evaluated objective, not forced finest cell',trace=list(result.trace))
            print('ARM_DONE',sid,name,arm,chosen['latitude_deg'],chosen['longitude_deg'],chosen['scores'],flush=True)
        # Same-prior common inventory removes unequal search coverage as an explanation.
        branch['common_inventory_best']={arm:min(evaluator.cache.values(),key=lambda r:(r['scores'][arm],r['east_km'],r['north_km']))
            for arm in ('D','D_plus_detection','D_plus_geometry','D_plus_reversed_geometry')}
        branch['point_components']=[{k:v for k,v in r.items() if k!='tracks'} for r in evaluator.cache.values()]
        out['branches'][name]=branch;out['elapsed_s']=time.monotonic()-start
        atomic(target,out)
    out['finished']=True;out['elapsed_s']=time.monotonic()-start
    out['code_sha256']={name:digest((HERE/name).read_bytes()) for name in ('run_search.py','location_core.py')}
    atomic(target,out);print('SCAN_DONE',sid,round(out['elapsed_s'],1),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--scan-index',type=int,required=True);parser.add_argument('--budget',type=int,default=160)
    args=parser.parse_args();run_scan(args.scan_index,args.budget)
