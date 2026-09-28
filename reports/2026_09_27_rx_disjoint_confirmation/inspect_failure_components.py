"""Fixed saved-candidate component audit; no new association or model selection."""
from dataclasses import replace
from pathlib import Path
import argparse
import json
import math
import pickle
import time
import numpy as np
import run_disjoint as runner
import reception_endpoints
from robust_core import robust_location

HERE=Path(__file__).resolve().parent
base=runner.base


def run(sid):
    start=time.monotonic();target=HERE/f'failure-components-{sid}.json'
    if target.exists():raise FileExistsError(target)
    diagnostic=json.loads((HERE/'regression-diagnostic.json').read_text())
    selected=diagnostic['results'][sid]['X_to_Y']['worst_five'][:2]
    if diagnostic['results'][sid]['X_to_Y']['gain']>=0:raise ValueError('not a regression')
    saved_path=HERE/f'disjoint-{sid}.json';saved=json.loads(saved_path.read_text())
    saved_rows={r['track_id']:r for r in saved['records'] if r['direction']=='X_to_Y'}
    contract=json.loads((HERE/'contract.json').read_text())
    for path,expected in contract['files'].items():
        if base.digest(Path(path).read_bytes())!=expected:raise ValueError('contract changed')
    joined,receipt,cal,csha,det,dsha,ratio,rsha=base._accepted_sources(contract['calibration_sessions'])
    coeff=cal['descriptive_full_six'];schema=base.adapter.fit_schema(joined)
    sigma=float(det['full']['models']['mixture']['sigma_selection']['sigma'])
    tau=float(ratio['full']['models']['mixture']['tau_selection']['tau'])
    entry=next(r for r in json.loads((HERE/'inventory.json').read_text()) if r['session_id']==sid)
    raw=pickle.loads(Path(entry['cache_file']).read_bytes())
    prepared=base.prepare_adaptive_tle_position_inputs(sid,inputs=base.frequency_helpers.CachedInput(raw),archive=base.TleArchiveReader(Path('/var/lib/leo/tle')))
    prepared,topology=base.filter_prepared(prepared,base.resolve(raw))
    ids={r['track_id'] for r in selected}
    prepared=replace(prepared,tracks=tuple(t for t in prepared.tracks if t.track_id in ids))
    if len(prepared.tracks)!=2:raise ValueError('track mismatch')
    complementary=replace(prepared,tracks=tuple(replace(t,training_mask=~np.asarray(t.training_mask,bool)) for t in prepared.tracks))
    bias=json.loads((base.DIRECTION/'pairing_summary.json').read_text())['calibration_fit']['bias_hz']
    endpoints=reception_endpoints.build(raw,prepared,bias_hz=bias)+reception_endpoints.build(raw,complementary,bias_hz=bias)
    endpoints={(r['track_id'],r['observation_id']):r for r in endpoints}
    manifest=json.loads((HERE/'manifest.json').read_text());pose=next(r['pose']['pose_authority'] for r in manifest['sessions'] if r['capture']['session_id']==sid)
    point=base.frequency_helpers.point(pose['latitude_deg'],pose['longitude_deg'])
    banks,_=base.build_prediction_banks(prepared.catalogue,prepared.candidate_indices,prepared.start_utc_ns,prepared.tracks,taus_s=np.array([0.]))
    blocks={}
    for b in base.RegionalTrackPredictionEvaluator(banks,lambda e,n:point,taus_s=np.array([0.]))(0,0):blocks.setdefault(b.track_id,[]).append(b)
    axis=np.array([-np.sin(np.deg2rad(pose['longitude_deg'])),np.cos(np.deg2rad(pose['longitude_deg'])),0.])
    parameters=saved['frequency_parameters'];output=[]
    for bank in banks:
        track=bank.source;r=saved_rows[track.track_id];cids=r['candidate_ids']
        train=np.array([oid in set(r['training_observation_ids']) for oid in track.observation_ids]);held=~train
        bid={int(c):i for i,c in enumerate(bank.candidate_ids)}
        positions=bank.position_km[[bid[c] for c in cids],0,:,:];delta=positions-point.ecef_km
        east=np.sum(delta/np.linalg.norm(delta,axis=-1,keepdims=True)*axis,axis=-1)
        reception=[]
        for n in np.flatnonzero(train):
            oid=track.observation_ids[n];e=endpoints[track.track_id,oid]
            reception.append(base.adapter.JoinedRow(sid,track.track_id,oid,e['receiver_id'],f"{e['channel']}:{e['edge']}",str(e['sample_rate_hz']),float(e['anchor_margin']),e['matched'],float(e['log_margin_ratio_rx1_rx0'] or 0.),east[:,n]))
        j=base.adapter.JoinedTrack(sid,track.track_id,tuple(cids),np.asarray(r['training_log_weights']),tuple(reception))
        tensors,layout,names=base.adapter.build_arm((j,),schema,'mixture',base.mixture_core);tensor=tensors[0]
        theta=base.detection_runner.frozen_theta(coeff['models']['mixture'],layout)
        dd,rr=base.directional_design(j,tensor,schema,'normal');pd,pr=layout.detection_size,layout.ratio_size
        logits=np.einsum('knp,p->kn',dd,theta[:pd]);matched=np.asarray(tensor.matched,bool)
        detection=base.detection_core.candidate_detection_loglik(logits,matched,sigma,quadrature_order=64)
        means=np.einsum('knp,p->kn',rr,theta[pd:pd+pr]);observed=np.asarray(tensor.log_ratio,float)
        ratio_ll=base.ratio_core.candidate_ratio_loglik(observed[None,matched]-means[:,matched],math.exp(2*float(theta[-1])),tau)
        if not np.allclose(detection+ratio_ll,r['controls']['normal']['reception_ll'],rtol=0,atol=1e-9):raise ValueError('reception decomposition parity')
        chunks=blocks[track.track_id];pid=np.concatenate([b.candidate_ids for b in chunks]);pred=np.concatenate([b.predictions_hz[:,0,:] for b in chunks])
        index={int(c):i for i,c in enumerate(pid)};res=np.asarray(track.measured_hz)[None,:]-pred[[index[c] for c in cids]]
        frequency=[]
        for k,cid in enumerate(cids):
            cfo=r['profiled_cfo_hz'][k]
            refit=robust_location(res[k,held],scale_hz=parameters['scale_hz'],degrees_of_freedom=parameters['degrees_of_freedom'])
            residual=res[k]-cfo
            held_ll=base.student_t_logpdf(residual[held],scale_hz=parameters['scale_hz'],degrees_of_freedom=parameters['degrees_of_freedom']).sum()
            if abs(held_ll-r['held_frequency_ll'][k])>1e-7:raise ValueError('frequency parity')
            slope={}
            for label,mask in [('X',train),('Y',held)]:
                t=np.asarray(track.times_s)[mask];t=t-t.mean()
                slope[label]=float(t@residual[mask]/(t@t)) if t@t>0 else None
            frequency.append({'candidate_id':cid,'conditioning_cfo_hz':cfo,'held_refit_cfo_hz':refit,'cfo_difference_hz':refit-cfo,
                'held_fixed_rms_hz':float(np.sqrt(np.mean(residual[held]**2))),
                'held_refit_rms_hz':float(np.sqrt(np.mean((res[k,held]-refit)**2))),
                'residual_slope_hz_per_s':slope})
        output.append({'track_id':track.track_id,'candidate_ids':cids,'conditioning_count':int(train.sum()),'held_count':int(held.sum()),
            'matched_count':int(matched.sum()),'receiver_counts':{rx:sum(row.receiver_id==rx for row in reception) for rx in ('rx0','rx1')},
            'detection_ll':detection.tolist(),'ratio_ll':ratio_ll.tolist(),'combined_reception_ll':(detection+ratio_ll).tolist(),
            'frequency':frequency,'physical_pair_keys':[endpoints[track.track_id,oid]['physical_pair_key'] for oid in r['training_observation_ids']],
            'conditioning_time_range_s':[float(np.min(np.asarray(track.times_s)[train])),float(np.max(np.asarray(track.times_s)[train]))]})
    result={'scope':'Posthoc fixed-candidate decomposition; held CFO refits and slopes are diagnostics, not deployable fits or physical satellite truth.',
        'session_id':sid,'source_sha256':base.digest(saved_path.read_bytes()),'contract_sha256':base.digest((HERE/'contract.json').read_bytes()),
        'code_sha256':base.digest(Path(__file__).read_bytes()),'tracks':output,'elapsed_s':time.monotonic()-start}
    with target.open('x') as stream:json.dump(base.json_value(result),stream,indent=2,allow_nan=False);stream.write('\n')
    print('COMPONENTS_DONE',sid,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--session-id',required=True,choices=['scan-fw-127d8fc36e804ae2','scan-fw-8f4f960d9db67798'])
    run(parser.parse_args().session_id)
