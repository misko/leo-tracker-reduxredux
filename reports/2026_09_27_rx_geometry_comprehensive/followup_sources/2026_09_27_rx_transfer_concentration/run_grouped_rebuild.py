"""Bounded development replay with newly fitted grouped-partition identities/CFOs."""
from dataclasses import replace, asdict
from collections import defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import pickle
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'2026_09_27_roof_balanced_confirmation'
sys.path.insert(0,str(OLD))
import run_association_transfer as base
import reception_endpoints
from grouped_split import randomized_groups
from conservative import blend, lse


def run(index):
    start=time.monotonic()
    fixed=json.loads((base.LOCATION/'topology_frequency_fixedpoint.json').read_text())
    sessions=sorted(fixed['final_tracks']);sid=sessions[index]
    target=HERE/f'grouped-rebuild-{sid}.json'
    if target.exists():raise FileExistsError(target)
    joined,receipt,cal,csha,det,dsha,ratio,rsha=base._accepted_sources(sessions)
    coeff,dfold,rfold,sigma,tau=base._fold_models(sid,sessions,cal,det,ratio)
    schema=base.adapter.fit_schema(tuple(t for t in joined if t.session_id!=sid))
    if coeff['feature_schema']!=base.json_value(asdict(schema)):raise ValueError('schema changed')
    inventory=json.loads((base.DIRECTION/'evaluation_inventory.json').read_text())
    entry=next(r for r in inventory if r['session_id']==sid)
    payload=Path(entry['cache_file']).read_bytes()
    if base.digest(payload)!=entry['cache_sha256']:raise ValueError('cache changed')
    raw=pickle.loads(payload)
    prepared=base.prepare_adaptive_tle_position_inputs(sid,inputs=base.frequency_helpers.CachedInput(raw),
        archive=base.TleArchiveReader(Path('/var/lib/leo/tle')))
    source=fixed['source_digests'][sid]
    for key in ('input_manifest_sha256','analysis_manifest_sha256','evidence_sha256','snapshot_digest'):
        if getattr(prepared,key)!=source[key]:raise ValueError('input binding changed')
    links=base.resolve(raw)
    if base.digest(json.dumps(links,sort_keys=True,separators=(',',':'),allow_nan=False).encode())!=source['source_links_sha256']:
        raise ValueError('source links changed')
    prepared,topology=base.filter_prepared(prepared,links)
    if topology['removed_track_ids']!=source['removed_track_ids']:raise ValueError('topology changed')
    # Reception extraction is position/identity independent. Explicitly request
    # all observations, not the obsolete interleaved reserve mask.
    complementary_prepared=replace(prepared,tracks=tuple(replace(t,training_mask=~np.asarray(t.training_mask,bool)) for t in prepared.tracks))
    pairing_path=base.DIRECTION/'pairing_summary.json'
    pairing=json.loads(pairing_path.read_text())
    bias=float(pairing['calibration_fit']['bias_hz'])
    endpoints=(reception_endpoints.build(raw,prepared,bias_hz=bias)+
               reception_endpoints.build(raw,complementary_prepared,bias_hz=bias))
    endpoint={(r['track_id'],r['observation_id']):r for r in endpoints}
    if len(endpoint)!=len(endpoints):raise ValueError('duplicate endpoint')
    provenance=base.provenance_rows(raw)
    rows=[]
    for track in prepared.tracks:
        for oid in track.observation_ids:
            e=endpoint[track.track_id,oid]
            rows.append({'track_id':track.track_id,'observation_id':oid,
                         **provenance[track.track_id,oid],'physical_pair_key':e['physical_pair_key']})
    split=randomized_groups(rows,sid)
    labels={(o['track_id'],o['observation_id']):('X' if g['partition']=='train' else 'Y')
            for g in split['groups'] for o in g['observations']}
    manifest=json.loads((base.DIRECTION/'evaluation_manifest.json').read_text())
    pose=next(r['pose']['pose_authority'] for r in manifest['sessions'] if r['pose']['session_id']==sid)
    point=base.frequency_helpers.point(pose['latitude_deg'],pose['longitude_deg'])
    banks,bank_receipt=base.build_prediction_banks(prepared.catalogue,prepared.candidate_indices,prepared.start_utc_ns,prepared.tracks,taus_s=np.array([0.]))
    predictions=defaultdict(list)
    for block in base.RegionalTrackPredictionEvaluator(banks,lambda e,n:point,taus_s=np.array([0.]))(0,0):
        predictions[block.track_id].append(block)
    bank_lookup={b.source.track_id:b for b in banks}
    east_axis=np.array([-np.sin(np.deg2rad(pose['longitude_deg'])),np.cos(np.deg2rad(pose['longitude_deg'])),0.])
    parameters=fixed['frozen_final_parameters'];results=[];unsupported=[]
    for track in prepared.tracks:
        tid=track.track_id
        x=np.array([labels[tid,oid]=='X' for oid in track.observation_ids])
        if min(x.sum(),(~x).sum())<3:
            unsupported.append({'track_id':tid,'X_count':int(x.sum()),'Y_count':int((~x).sum())});continue
        chunks=predictions[tid];pred=np.concatenate([b.predictions_hz[:,0,:] for b in chunks])
        ids=np.concatenate([b.candidate_ids for b in chunks]);visible=np.concatenate([np.asarray(b.visible).reshape(-1) for b in chunks])
        bank=bank_lookup[tid];lookup={int(cid):i for i,cid in enumerate(bank.candidate_ids)}
        for direction,train in [('X_to_Y',x),('Y_to_X',~x)]:
            shortlist=base.train_shortlist(pred,track.measured_hz,train,visible,scale_hz=parameters['scale_hz'],df=parameters['degrees_of_freedom'])
            chosen=np.asarray(shortlist['candidate_indices'],int);cids=ids[chosen].astype(int).tolist()
            positions=bank.position_km[[lookup[c] for c in cids],0,:,:]
            delta=positions-point.ecef_km;east=np.sum(delta/np.linalg.norm(delta,axis=-1,keepdims=True)*east_axis,axis=-1)
            reception=[]
            for n in np.flatnonzero(train):
                oid=track.observation_ids[n];r=endpoint[tid,oid]
                reception.append(base.adapter.JoinedRow(sid,tid,oid,r['receiver_id'],f"{r['channel']}:{r['edge']}",str(r['sample_rate_hz']),float(r['anchor_margin']),bool(r['matched']),float(r['log_margin_ratio_rx1_rx0'] or 0.),east[:,n]))
            j=base.adapter.JoinedTrack(sid,tid,tuple(cids),np.asarray(shortlist['log_weights']),tuple(reception))
            tensors,layout,names=base.adapter.build_arm((j,),schema,'mixture',base.mixture_core)
            theta=base.detection_runner.frozen_theta(coeff['models']['mixture'],layout)
            residual=np.asarray(track.measured_hz)[None,:]-pred[chosen]-np.asarray(shortlist['profiled_cfo_hz'])[:,None]
            fb=base.student_t_logpdf(residual[:,~train],scale_hz=parameters['scale_hz'],degrees_of_freedom=parameters['degrees_of_freedom']).sum(axis=1)
            p=shortlist['log_weights'];uniform=[-np.log(len(p))]*len(p)
            baseline=blend(p,uniform,.5);count=int((~train).sum())
            nll=-lse([a+b for a,b in zip(baseline,fb)])/count
            controls={}
            for mode in ('normal','reversed','null'):
                ra,check=base.reception_loglik(j,tensors[0],schema,theta,layout,list(range(len(reception))),sigma,tau,mode)
                q=np.asarray(p)+ra;q=q-lse(q)
                mixed=blend(q.tolist(),uniform,.5)
                score=-lse([a+b for a,b in zip(mixed,fb)])/count
                controls[mode]={'nll':score,'gain':nll-score,'reception_ll':ra.tolist(),'posterior_log_weights':q.tolist(),'quadrature':check}
            if abs(controls['null']['gain'])>1e-10:raise ValueError('null failed')
            results.append({'session_id':sid,'track_id':tid,'direction':direction,'candidate_ids':cids,
                'training_observation_ids':[oid for oid,t in zip(track.observation_ids,train) if t],
                'held_observation_ids':[oid for oid,t in zip(track.observation_ids,train) if not t],
                'profiled_cfo_hz':shortlist['profiled_cfo_hz'],'training_log_weights':p,
                'held_frequency_ll':fb.tolist(),'held_count':count,'baseline_nll':nll,
                'weight_seconds':len(np.unique(np.floor(track.times_s))),'controls':controls})
    summary={}
    for direction in ('X_to_Y','Y_to_X'):
        rr=[r for r in results if r['direction']==direction];w=sum(r['weight_seconds'] for r in rr)
        summary[direction]={mode:sum(r['weight_seconds']*r['controls'][mode]['gain'] for r in rr)/w for mode in ('normal','reversed','null')}
    output={'session_id':sid,'finished':True,'scope':'Conditional development replay: global frequency parameters and pairing calibration include this session; RX coefficients exclude it. Not independent validation or geography.',
        'split':split,'unsupported':unsupported,'records':results,'summary':summary,'elapsed_s':time.monotonic()-start,
        'cache_sha256':entry['cache_sha256'],'frequency_parameters':parameters,'topology':topology,
        'calibration_sha256':csha,'detection_sha256':dsha,'ratio_sha256':rsha,'pairing_sha256':base.digest(pairing_path.read_bytes()),
        'code_hashes':{name:base.digest((HERE/name).read_bytes()) for name in ('run_grouped_rebuild.py','grouped_split.py','conservative.py')},
        'dependency_hashes':base.source_hashes(),'prediction_receipt':asdict(bank_receipt)}
    with target.open('x') as stream:json.dump(base.json_value(output),stream,indent=2,allow_nan=False);stream.write('\n')
    print('DONE',sid,len(results)//2,len(unsupported),summary,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--session-index',type=int,required=True,choices=range(6))
    run(parser.parse_args().session_index)
