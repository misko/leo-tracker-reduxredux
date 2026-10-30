"""Trace one predictive target back to native GLRT candidates and timing support."""
import argparse, hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read, write
from evaluate_ds22_merged_tracks import winners, digest
from audit_bundle_native_measurements import pilot_time_support, physical_residual
from residual_witness_prediction import time_pairs
from leo.analysis.research.retained_track_likelihood import PERIOD


def polynomial_measurements(track):
    if len(track['pieces'])!=1:raise ValueError('single original polynomial piece required')
    p=track['pieces'][0];t=np.asarray(track['times']);coef=np.asarray(p['coefficients_hz'])
    z=(t-p['reference_time_s'])/p['time_scale_s']
    prediction=np.polynomial.legendre.legval(z,coef)
    rate=np.polynomial.legendre.legval(z,np.polynomial.legendre.legder(coef))/p['time_scale_s']
    return np.asarray(track['values'])-prediction,rate


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    pr=read(args.trial/'protocol.json');target=pr['targets'][0]
    if len(pr['targets'])!=1:raise ValueError('single target required')
    ip=args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json';inv=read(ip)
    root=Path(inv['job']['root'])/inv['job']['case'];document=read(root/'tracking.json')
    raw=read(root/'observations.json');tracks=read(root/'tracks.json');track=tracks[target['track_index']]
    if track['observation_ids']!=target['observation_ids']:raise ValueError('target identity or ordering changed')
    replay,_=winners(document)
    if replay!=raw:raise ValueError('native GLRT winners differ from saved observations')
    source=document['source'];byid={r['observation_id']:r for r in raw};probes={}
    for p in source['probes']:
        oid=digest(f"{source['session_id']}:{p['receiver_id']}:{p['valid_start_counter']}".encode())
        probes[oid]=p
    residual,rate=polynomial_measurements(track);times=np.asarray(track['times']);rows=[]
    for k,oid in enumerate(track['observation_ids']):
        o=byid[oid];p=probes[oid];eligible=[c for c in p['candidates'] if c['passed_fractional_margin_gate']]
        c=max(eligible,key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
        if o['time_s']!=times[k] or o['measured_cfo_hz']!=c['fractional_tracking_cfo_hz']:
            raise ValueError('native time or frequency mismatch')
        lift=(track['values'][k]-o['measured_cfo_hz'])/PERIOD
        if abs(lift-round(lift))>1e-8:raise ValueError('non-alias change to native CFO')
        support=pilot_time_support(c['integer_epoch_sample']+c['fractional_epoch_offset_samples'],source['sample_rate_hz'],round(source['probe_ms']*.001*source['sample_rate_hz']))
        rows.append(dict(observation_id=oid,time_s=times[k],native_CFO_hz=o['measured_cfo_hz'],native_alias=int(round(lift)),
            original_polynomial_residual_hz=residual[k],polynomial_rate_hz_s=rate[k],
            candidate_rank=c['candidate_rank'],fractional_margin=c['fractional_margin'],eligible_candidates=len(eligible),
            candidates=p['candidates'],pilot_support=support,
            uniform_timing_shift_hz=rate[k]*(support['uniform_centroid_s']-support['probe_midpoint_s']),
            maximum_support_timing_shift_hz=abs(rate[k])*max(abs(support['support_start_s']-support['probe_midpoint_s']),abs(support['support_end_s']-support['probe_midpoint_s']))))
    saved=read(args.trial/'new_family.json');arms={}
    for arm,v in saved['arms'].items():
        diag=v['family']['diagnostics'][0];np.testing.assert_array_equal(times,diag['times_s'])
        r=physical_residual(diag)
        arms[arm]=dict(residual_hz=r,polynomial_orbital_correlation=float(np.corrcoef(residual,r)[0,1]),
            original_polynomial_RMS_hz=float(np.sqrt(np.mean(residual**2))),orbital_RMS_hz=float(np.sqrt(np.mean(r*r))))
    witnesses=[]
    for i,t in enumerate(tracks):
        if i==target['track_index'] or t['receiver']!=track['receiver'] or len(t['pieces'])!=1:continue
        pairs=time_pairs(times,t['times'],1.5)
        if len(pairs)<6:continue
        wr,_=polynomial_measurements(t);a,b=pairs.T
        witnesses.append(dict(component=t['key'],receiver=t['receiver'],channel=t['channel'],points=len(pairs),
            target_times_s=times[a],witness_times_s=np.asarray(t['times'])[b],
            target_residual_hz=residual[a],witness_residual_hz=wr[b],
            normalized_residual_hz=wr[b]*track['rf_hz']/t['rf_hz'],
            polynomial_residual_correlation=float(np.corrcoef(residual[a],wr[b])[0,1])))
    paths=[ip,args.trial/'protocol.json',args.trial/'new_family.json',*[root/n for n in ('tracks.json','tracking.json','observations.json')]]
    write(args.output/'result.json',dict(job=inv['job'],target=target,points=rows,arms=arms,witnesses=witnesses,
        graph_quality_status=track['quality_status'],graph_diagnostics=track['diagnostics'],
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        native_replay_exact=True,changes_to_fit=False,GPS_used=False,
        timing_caveat='First-order within-pilot support sensitivity from native polynomial; unknown IQ weights, no absolute clock validation',
        witness_caveat='In-sample native polynomial residuals on other tracks, not independent satellite-model validation; polynomial fitting can absorb common smooth errors'))
    fig,axs=plt.subplots(2,2,figsize=(14,8),layout='constrained')
    axs[0,0].plot(times,residual,'.-',label='Original graph polynomial')
    for arm,v in arms.items():axs[0,0].plot(times,v['residual_hz'],'.-',lw=.6,label=arm+' orbit')
    axs[0,0].set(ylabel='Residual (Hz)',title='Excursions before satellite association')
    axs[0,1].plot(times,[r['fractional_margin'] for r in rows],'.-',label='Winning GLRT margin')
    axs[0,1].set(ylabel='Fractional margin',title='Native measurement quality proxy')
    axs[1,0].plot(times,[r['uniform_timing_shift_hz'] for r in rows],'.-',label='Uniform-frame centroid')
    axs[1,0].plot(times,[r['maximum_support_timing_shift_hz'] for r in rows],'.-',label='Maximum within-pilot support')
    axs[1,0].set(ylabel='First-order CFO shift (Hz)',title='Within-probe timing sensitivity')
    axs[1,1].plot(times,residual,'k.-',label='Target RX'+str(track['receiver'])+' CH'+str(track['channel']))
    for w in witnesses:axs[1,1].plot(w['witness_times_s'],w['normalized_residual_hz'],'.-',lw=.6,label=w['component'].split('-RF')[0])
    axs[1,1].set(ylabel='Native polynomial residual, RF-normalized (Hz)',title=f'Same-receiver witnesses ({len(witnesses)})')
    for ax in axs.flat:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2);ax.legend(fontsize=6)
    fig.savefig(args.output/'native_audit.png',dpi=140);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','trial','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
