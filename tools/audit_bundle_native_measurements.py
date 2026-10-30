"""Frozen native-point, fragment and timing audit; no measurement correction."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from evaluate_ds22_merged_tracks import winners,digest
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from residual_witness_prediction import time_pairs
from leo.analysis.starlink.fast_scan_scores import FRAME_RATE_HZ,OFDM_SYMBOL_DURATION_S


def pilot_time_support(epoch,rate,window_samples):
    """Uniform-frame centroid and rigorous sample-support bounds, not IQ weights."""
    if not np.isfinite([epoch,rate,window_samples]).all() or epoch<0 or rate<=0 or window_samples<=0:raise ValueError('finite nonnegative epoch and positive sample geometry required')
    starts=[];k=0;last=int(round(66*OFDM_SYMBOL_DURATION_S*rate))
    while epoch+round(k*rate/FRAME_RATE_HZ)+last<=window_samples:
        starts.append(epoch+round(k*rate/FRAME_RATE_HZ));k+=1
    if not starts:raise ValueError('no complete pilot frame')
    lo=(np.array(starts)+round(2*OFDM_SYMBOL_DURATION_S*rate))/rate
    hi=(np.array(starts)+last-1)/rate
    return dict(frames=len(starts),uniform_centroid_s=float(np.mean((lo+hi)/2)),
        support_start_s=float(lo.min()),support_end_s=float(hi.max()),probe_midpoint_s=window_samples/rate/2,
        unknown_IQ_weights=True)


def metrics(times,residual):
    r=np.asarray(residual);return dict(points=len(r),RMS_hz=float(np.sqrt(np.mean(r*r))),mean_hz=float(np.mean(r)),
        noise={k:v[0].item() for k,v in batch_noise_screen(r[None],times).items()})


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);pr=read(args.trial/'protocol.json');ann=read(args.validation/'protocol.json')
    target=ann['target'];inv=read(args.inventory);root=Path(inv['job']['root'])/inv['job']['case']
    document=read(root/'tracking.json');raw=read(root/'observations.json');tracks=read(root/'tracks.json')
    replay,_=winners(document)
    if replay!=raw:raise ValueError('native GLRT observation authority failed replay')
    byid={o['observation_id']:o for o in raw};source=document['source'];native={}
    for probe in source['probes']:
        oid=digest(f"{source['session_id']}:{probe['receiver_id']}:{probe['valid_start_counter']}".encode())
        eligible=[c for c in probe['candidates'] if c['passed_fractional_margin_gate']]
        if eligible:native[oid]=(probe,max(eligible,key=lambda c:(c['fractional_margin'],-c['candidate_rank'])))
    saved=read(args.trial/'target_0.json');original_byid={};rows=[]
    for member_index,m in enumerate(target['members']):
        track=tracks[m['track_index']]
        if len(track['pieces'])!=1:raise ValueError('this diagnostic requires original single-piece fragments')
        piece=track['pieces'][0];t=np.asarray(track['times']);coef=np.asarray(piece['coefficients_hz']);z=(t-piece['reference_time_s'])/piece['time_scale_s']
        y=np.asarray(track['values']);prediction=np.polynomial.legendre.legval(z,coef);rate=np.polynomial.legendre.legval(z,np.polynomial.legendre.legder(coef))/piece['time_scale_s']
        for k,oid in enumerate(track['observation_ids']):
            o=byid[oid];probe,c=native[oid]
            if o['time_s']!=t[k] or o['measured_cfo_hz']!=c['fractional_tracking_cfo_hz']:raise ValueError('native frequency or time changed')
            native_lift=(y[k]-o['measured_cfo_hz'])/PERIOD
            if abs(native_lift-round(native_lift))>1e-8:raise ValueError('graph changed native CFO beyond integer alias')
            support=pilot_time_support(c['integer_epoch_sample']+c['fractional_epoch_offset_samples'],source['sample_rate_hz'],round(source['probe_ms']*.001*source['sample_rate_hz']))
            row=dict(observation_id=oid,member=member_index,component=track['key'],time_s=t[k],native_CFO_hz=o['measured_cfo_hz'],
                aligned_CFO_hz=y[k]+m['alias_lift']*PERIOD,native_alias=int(round(native_lift)),bundle_alias=m['alias_lift'],
                original_polynomial_residual_hz=y[k]-prediction[k],original_polynomial_rate_hz_s=rate[k],
                candidate_rank=c['candidate_rank'],fractional_epoch_samples=c['fractional_epoch_offset_samples'],fractional_margin=c['fractional_margin'],
                visit_index=probe['visit_index'],pilot_support=support,
                uniform_timing_shift_hz=rate[k]*(support['uniform_centroid_s']-support['probe_midpoint_s']),
                maximum_support_timing_shift_hz=abs(rate[k])*max(abs(support['support_start_s']-support['probe_midpoint_s']),abs(support['support_end_s']-support['probe_midpoint_s'])))
            rows.append(row);original_byid[oid]=row
    rows.sort(key=lambda r:r['time_s']);ordered_ids=[r['observation_id'] for r in rows]
    if ordered_ids!=target['observation_ids']:raise ValueError('union identity order differs')
    member=np.array([r['member'] for r in rows]);times=np.array([r['time_s'] for r in rows]);arms=[]
    for arm,v in saved['arms'].items():
        diag=v['target_diagnostics'][0]
        np.testing.assert_array_equal(times,diag['times_s']);residual=np.array(diag['residual_hz']);member_rows=[]
        for k in range(len(target['members'])):
            select=member==k;member_rows.append(dict(member=k,original_polynomial=metrics(times[select],np.array([r['original_polynomial_residual_hz'] for r in rows])[select]),
                orbital_same_bundle_bias=metrics(times[select],residual[select]),times_s=times[select],residual_hz=residual[select]))
        pairs=time_pairs(times[member==0],times[member==1],1.5);r0=residual[member==0];r1=residual[member==1]
        paired=dict(points=len(pairs),tolerance_s=1.5,correlation=float(np.corrcoef(r0[pairs[:,0]],r1[pairs[:,1]])[0,1]) if len(pairs)>3 else None,
            difference_RMS_hz=float(np.sqrt(np.mean((r0[pairs[:,0]]-r1[pairs[:,1]])**2))) if len(pairs) else None)
        arms.append(dict(arm=arm,pooled=metrics(times,residual),members=member_rows,near_time_fragment_comparison=paired))
    paths=[args.inventory,args.validation/'protocol.json',args.trial/'target_0.json',root/'tracking.json',root/'observations.json',root/'tracks.json']
    write(args.output/'result.json',dict(job=inv['job'],target=target,observations=rows,arms=arms,native_replay_exact=True,
        all_graph_values_native_plus_integer_alias=True,source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        maximum_uniform_timing_shift_hz=max(abs(r['uniform_timing_shift_hz']) for r in rows),
        maximum_support_timing_shift_hz=max(r['maximum_support_timing_shift_hz'] for r in rows),
        timing_derivative_source='original graph polynomial; first-order sensitivity only',unknown_IQ_frame_weights=True,
        no_absolute_clock_validation=True,no_new_measurement_or_position=True,no_acceptance_authorized=True))
    print('native replay and fragment audit complete',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('inventory','validation','trial','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
