"""Bounded recorded-IQ identity diagnostic, independent of orbital/GPS fits.

Prepare selects the disputed simultaneous window by categorical association
disagreement and native GLRT margins. Export uses the public verified reader
and writes only stdout; it never modifies any recording.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

from run_algo01_ds23_sample import ROOT, DATASET, read, write, sha
from probe_algo03_frame_peak_recovery import SOURCE

OUT=ROOT/'reports/2026_10_20_ds23_0268_shared_waveform'
PRIOR=ROOT/'reports/2026_10_20_ds23_0268_visibility_reentry'
CASE='DS23-0268'


def prepare():
    from leo.analysis.glrt_frequency_input import frequency_evidence
    OUT.mkdir(exist_ok=True)
    document=read(SOURCE/CASE/'tracking.json')
    evidence,_,_=frequency_evidence(document)
    lookup={'sha256:'+hashlib.sha256(identity.encode()).hexdigest():probe
        for identity,probe in zip(evidence.ids,document['source']['probes'],strict=True)}
    tracks={t['key']:t for t in read(SOURCE/CASE/'tracks.json')}
    previous=next(r for r in read(PRIOR/'trial_coverage.json')['rows'] if r['name']=='interior_add_66797')['arms']['c0']
    latest=read(PRIOR/'accepted_identity_split_coverage.json')['selected_split_all_RX1_with_CH2_constrained']['c0']
    def owners(record):
        return {oid:row['norad'] for row in record['accepted_rows']
            for oid in row.get('observation_ids',tracks[row['component']]['observation_ids'])}
    before,after=owners(previous),owners(latest)
    visits={}
    for oid,old_label in before.items():
        p=lookup[oid]
        peak=max((c for c in p['candidates'] if c['passed_fractional_margin_gate']),
                 key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
        visits.setdefault(p['visit_index'],{})[p['receiver_id']]=dict(observation_id=oid,
            old_norad=old_label,new_norad=after.get(oid),peak=peak,probe=p)
    pairs=[]
    for visit,rows in visits.items():
        if set(rows)!={0,1}:continue
        a,b=rows[0],rows[1]
        if (a['old_norad']==b['old_norad'] and a['new_norad']!=b['new_norad'] and
                a['probe']['channel']==b['probe']['channel']):
            pairs.append(dict(visit_index=visit,receivers=rows,
                minimum_margin=min(a['peak']['fractional_margin'],b['peak']['fractional_margin'])))
    if not pairs:raise ValueError('no simultaneous disputed family window')
    chosen=sorted(pairs,key=lambda r:-r['minimum_margin'])[:3]
    write(OUT/'plan.json',dict(case=CASE,pairs=chosen,maximum_raw_windows=7000,maximum_seconds=240,
        existing_IQ_only=True,selection_uses_association_disagreement_and_RF_margin_not_GPS_or_orbit=True,
        expected_known_pilot_correlation_not_identity_proof=True,
        tracking_sha256=sha(SOURCE/CASE/'tracking.json'),source_sha256=sha(Path(__file__))))
    print([(r['visit_index'],r['minimum_margin']) for r in chosen],flush=True)


def export(plan_name='plan.json'):
    from leo.storage.short_window import ShortWindowReader
    if Path(plan_name).name!=plan_name:raise ValueError('local plan filename required')
    plan=read(OUT/plan_name)
    member=next(r for r in read(DATASET/'manifest.json')['members'] if r['dataset_label']==CASE)
    required={r['visit_index'] for r in plan['pairs']}
    arrays={}
    receipts=[]
    visited=0
    started=time.monotonic()
    for authority in member['raw_recording']['segments']:
        path=Path(authority['path'])
        if 'sha256:'+sha(path)!=authority['sha256']:raise ValueError('raw manifest changed')
        reader=ShortWindowReader(path.parent)
        receipts.append(dict(path=str(path),sha256=sha(path)))
        for window in reader.windows():
            visited+=1
            visit=window.index.acquisition['global_visit']
            if visit in required:
                pair=next(r for r in plan['pairs'] if r['visit_index']==visit)
                for row in pair['receivers'].values():
                    if row['probe']['valid_start_counter']!=window.index.acquisition['sample_start']:
                        raise ValueError('raw/public sample counters differ')
                arrays[f'window_{visit:06d}']=np.array(window.samples,copy=True)
                pair['receiver_ids']=reader.manifest.receiver_ids
                pair['raw_window_sha256']=window.index.iq_sha256
                required.remove(visit)
            if not required:break
            if visited>=plan['maximum_raw_windows'] or time.monotonic()-started>plan['maximum_seconds']:
                raise RuntimeError('bounded recorded-IQ export incomplete')
        if not required:break
    if required:raise ValueError('disputed windows absent from recording')
    document=read(SOURCE/CASE/'tracking.json')
    metadata=dict(case=CASE,pairs=plan['pairs'],sample_rate_hz=document['source']['sample_rate_hz'],
        raw_windows_read=visited,seconds=time.monotonic()-started,manifests=receipts,
        plan_sha256=sha(OUT/plan_name),existing_recording_read_only=True)
    arrays['metadata_json']=np.array(json.dumps(metadata))
    np.savez_compressed(sys.stdout.buffer,**arrays)


def score_pair(samples, pair, fs):
    from ds23_shared_waveform import frame_positions, remove_pilot, coherence, derangements, carrier_spectrum
    from local_pilot_refinement import pilot_wave
    from probe_native_code_carrier import interpolate_periodic

    ids=list(pair['receiver_ids'])
    records=[pair['receivers'][str(rx)] for rx in (0,1)]
    vectors=[samples[:,ids.index(rx),0].astype(float)+1j*samples[:,ids.index(rx),1].astype(float) for rx in (0,1)]
    epochs=[r['peak']['integer_epoch_sample']+r['peak']['fractional_epoch_offset_samples'] for r in records]
    frequencies=[r['peak']['fractional_tracking_cfo_hz'] for r in records]
    positions=[frame_positions(len(y),fs,e) for y,e in zip(vectors,epochs,strict=True)]
    frames=min(map(len,positions))
    positions=[p[:frames] for p in positions]
    orders=derangements(frames)
    def sampled(y,pos):
        n=np.arange(len(y))
        return np.interp(pos,n,y.real)+1j*np.interp(pos,n,y.imag)
    template=[interpolate_periodic(pilot_wave(fs,r['probe']['edge']),(pos-e)*32)
              for r,pos,e in zip(records,positions,epochs,strict=True)]
    first=sampled(vectors[0],positions[0])*np.exp(-2j*np.pi*frequencies[0]*positions[0]/fs)
    residual,meta=remove_pilot(first,template[0])
    before=(first-first.mean(axis=1,keepdims=True))/meta['gain'][:,None]
    null_best=np.zeros(len(orders))
    best=None
    best_arrays=None
    trials=[]
    for delay in (-.25,0.,.25):
        pos=positions[1]+delay
        y=sampled(vectors[1],pos)
        for alias in range(-3,4):
            for correction in (-500.,-250.,0.,250.,500.):
                frequency=frequencies[1]+alias/4.4e-6+correction
                second=y*np.exp(-2j*np.pi*frequency*pos/fs)
                other,second_meta=remove_pilot(second,template[1])
                minimum_pilot=float(min(np.median(meta['pilot_energy_fraction']),np.median(second_meta['pilot_energy_fraction'])))
                if minimum_pilot<.02:continue
                actual,null=coherence(residual,other,orders)
                null_best=np.maximum(null_best,null)
                raw=(second-second.mean(axis=1,keepdims=True))/second_meta['gain'][:,None]
                raw_score,_=coherence(before,raw,orders)
                row=dict(delay_samples=delay,relative_alias=alias,residual_frequency_correction_hz=correction,
                    residual_coherence=actual,known_pilot_inclusive_coherence=raw_score,
                    median_pilot_fraction_RX1=float(np.median(meta['pilot_energy_fraction'])),
                    median_pilot_fraction_RX2=float(np.median(second_meta['pilot_energy_fraction'])))
                trials.append(row)
                if best is None or actual>best['residual_coherence']:
                    best=row
                    best_arrays=(other.copy(),second_meta['gain'].copy())
    if best is None:raise ValueError('no candidate retains supported known-pilot signal')
    # Restore the fitted frame phases, so a residual shared waveform can
    # independently measure relative carrier frequency across the whole probe.
    # Frame-normalized coherence above alone has no such carrier information.
    other,gain=best_arrays
    a=residual*meta['gain'][:,None]
    b=other*gain[:,None]
    carrier=carrier_spectrum(a,b,positions[0]/fs)
    relative=frequencies[1]+best['relative_alias']/4.4e-6+best['residual_frequency_correction_hz']-frequencies[0]+carrier['additional_frequency_hz']
    return dict(visit_index=pair['visit_index'],frames=frames,samples_per_frame=residual.shape[1],
        best=best,shuffled_frame_search_maxima=null_best,
        whole_probe_carrier=dict(carrier,relative_CFO_hz=float(relative),
            relative_CFO_mod_alias_hz=float((relative+1/4.4e-6/2)%(1/4.4e-6)-1/4.4e-6/2),
            empirical_stability_not_calibrated_uncertainty=True,
            scalar_carrier_search_does_not_identify_the_dominant_GLRT_peak=True),
        empirical_search_corrected_rank=(1+int(np.sum(null_best>=best['residual_coherence'])))/(1+len(null_best)),
        shuffled_control_median=float(np.median(null_best)),shuffled_control_maximum=float(null_best.max()),
        trials=trials,receiver_labels={str(rx):{k:pair['receivers'][str(rx)][k] for k in ('old_norad','new_norad') if k in pair['receivers'][str(rx)]} for rx in (0,1)},
        empirical_rank_not_a_calibrated_identity_probability=True,
        deterministic_pilot_interframe_affine_and_three_frame_cycle_projected_out=True,
        no_GPS_or_TLE_frequency_prediction_used=True)


def prepare_calibration():
    from leo.analysis.glrt_frequency_input import frequency_evidence
    from localize_merged_track_catalogue import raw_curvature
    from ds23_frame_registration import epoch_pairs

    document=read(SOURCE/CASE/'tracking.json')
    source=document['source']
    evidence,_,_=frequency_evidence(document)
    curved={oid for track in read(SOURCE/CASE/'tracks.json')
        if raw_curvature(dict(times=np.asarray(track['times']),values=np.asarray(track['values'])))
        for oid in track['observation_ids']}
    observations={r['observation_id']:r for r in read(SOURCE/CASE/'observations.json')}
    visits={}
    for identity,probe in zip(evidence.ids,source['probes'],strict=True):
        oid='sha256:'+hashlib.sha256(identity.encode()).hexdigest()
        if oid not in curved:continue
        passing=[c for c in probe['candidates'] if c['passed_fractional_margin_gate']]
        if not passing:continue
        peak=max(passing,key=lambda c:c['fractional_margin'])
        visits.setdefault(probe['visit_index'],{})[probe['receiver_id']]=dict(
            observation_id=oid,probe=probe,peak=peak,time_s=observations[oid]['time_s'])
    eligible=[]
    for visit,rx in visits.items():
        if set(rx)!={0,1}:continue
        a,b=rx[0],rx[1]
        if min(a['peak']['fractional_margin'],b['peak']['fractional_margin'])<.05:continue
        match=epoch_pairs([a['peak']],[b['peak']],source['sample_rate_hz'])
        if not match:continue
        eligible.append(dict(visit_index=visit,receivers=rx,band=int(a['probe']['channel']>4),
            time_s=a['time_s'],minimum_margin=match[0]['minimum_margin']))
    selected=[]
    for band in (0,1):
        for start in np.arange(0.,300.,37.5):
            pool=[r for r in eligible if r['band']==band and start<=r['time_s']<start+37.5]
            if pool:selected.append(max(pool,key=lambda r:r['minimum_margin']))
    disputed=read(OUT/'plan.json')['pairs']
    selected.extend(p for p in disputed if p['visit_index'] not in {r['visit_index'] for r in selected})
    write(OUT/'calibration_plan.json',dict(case=CASE,pairs=selected,maximum_raw_windows=7000,maximum_seconds=240,
        eligible_curved_pairs_by_band={str(b):sum(r['band']==b for r in eligible) for b in (0,1)},
        selection='highest minimum RF margin in each fixed 37.5s band bin; both graph curves active; plus disputed window',
        no_satellite_GPS_or_orbit_used_for_additional_pair_selection=True,
        no_linear_track_calibration=True,calibration_not_yet_applied=True,
        tracking_sha256=sha(SOURCE/CASE/'tracking.json'),source_sha256=sha(Path(__file__))))
    print('Selected curved-supported windows',[(r['visit_index'],r.get('time_s')) for r in selected],flush=True)


def analyze_calibration():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    path=OUT/'curved_pair_IQ.npz'
    result_path=OUT/'curved_pair_waveform_analysis.json'
    if result_path.exists():raise FileExistsError('preserve residual carrier diagnostic')
    rows=[]
    with np.load(path,allow_pickle=False) as z:
        metadata=json.loads(str(z['metadata_json']))
        for pair in metadata['pairs']:
            row=score_pair(z[f"window_{pair['visit_index']:06d}"],pair,metadata['sample_rate_hz'])
            row.update(time_s=pair.get('time_s'),band=pair.get('band'),
                RF_channel=pair['receivers']['0']['probe']['channel'])
            rows.append(row)
            print(pair['visit_index'],row['best']['residual_coherence'],row['shuffled_control_maximum'],
                  row['whole_probe_carrier']['relative_CFO_mod_alias_hz'],flush=True)
    write(result_path,dict(rows=rows,panel_sha256=sha(path),
        plan_sha256=sha(OUT/'calibration_plan.json'),source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'tools/ds23_shared_waveform.py'),
        no_GPS_or_TLE_used=True,no_receiver_calibration_applied=True,
        no_new_RF_or_raw_recording_mutation=True))
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for row in rows:
        t=row['time_s']
        if t is None:continue
        carrier=row['whole_probe_carrier']
        supported=row['best']['residual_coherence']>row['shuffled_control_maximum']
        color='#267b44' if supported else '#9659ad'
        axes[0].scatter(t,carrier['relative_CFO_mod_alias_hz'],color=color)
        axes[1].scatter(t,row['best']['residual_coherence']/max(row['shuffled_control_maximum'],1e-15),color=color)
    axes[0].set(xlabel='Scan time (s)',ylabel='Relative carrier modulo alias (Hz)')
    axes[1].set(xlabel='Scan time (s)',ylabel='Matched residual coherence / strongest shuffled control')
    axes[1].axhline(1,color='gray',ls='--')
    for ax in axes:ax.grid(alpha=.15)
    fig.suptitle('DS23-0268 · independent recorded-waveform carrier diagnostic\nGreen exceeds shuffled controls; carrier precision and dominant-emitter identity remain uncalibrated')
    fig.tight_layout(rect=(0,0,1,.9));fig.savefig(OUT/'curved_pair_relative_carrier.png',dpi=170);plt.close(fig)


def analyze():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    path=OUT/'disputed_IQ.npz'
    with np.load(path,allow_pickle=False) as z:
        metadata=json.loads(str(z['metadata_json']))
        rows=[score_pair(z[f"window_{pair['visit_index']:06d}"],pair,metadata['sample_rate_hz']) for pair in metadata['pairs']]
    # Existing early-scan windows provide separate RF-only controls. Select
    # high-margin simultaneous detections with close and separated epochs;
    # no nominated satellite identity is used to label a control as truth.
    panel=ROOT/'reports/2026_10_20_ds23_0268_longest_unassociated/raw_panel.npz'
    source=read(SOURCE/CASE/'tracking.json')['source']
    probes={(p['visit_index'],p['receiver_id']):p for p in source['probes']}
    with np.load(panel,allow_pickle=False) as z:
        m=json.loads(str(z['metadata_json']))
        candidates=[]
        for key in z.files:
            if not key.startswith('window_'):continue
            visit=int(key.split('_')[1])
            records={}
            for rx in (0,1):
                p=probes[(visit,rx)]
                passing=[c for c in p['candidates'] if c['passed_fractional_margin_gate']]
                if not passing:break
                peak=max(passing,key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
                records[str(rx)]=dict(probe=p,peak=peak)
            if len(records)!=2:continue
            minimum=min(r['peak']['fractional_margin'] for r in records.values())
            if minimum<.05:continue
            epochs=[r['peak']['integer_epoch_sample']+r['peak']['fractional_epoch_offset_samples'] for r in records.values()]
            period=source['sample_rate_hz']/750
            separation=abs((epochs[1]-epochs[0]+period/2)%period-period/2)
            candidates.append(dict(visit_index=visit,receivers=records,receiver_ids=[0,1],
                epoch_separation_samples=separation,minimum_margin=minimum,window_key=key))
        chosen=[]
        for close in (True,False):
            pool=[c for c in candidates if (c['epoch_separation_samples']<=.2 if close else c['epoch_separation_samples']>=2)]
            chosen.extend(dict(c,control_kind='close_epoch' if close else 'separated_epoch')
                for c in sorted(pool,key=lambda c:-c['minimum_margin'])[:2])
        for pair in chosen:
            result=score_pair(z[pair['window_key']],pair,m['sample_rate_hz'])
            result.update(control_kind=pair['control_kind'],epoch_separation_samples=pair['epoch_separation_samples'])
            rows.append(result)
    write(OUT/'waveform_analysis.json',dict(rows=rows,disputed_panel_sha256=sha(path),
        control_panel_sha256=sha(panel),source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'tools/ds23_shared_waveform.py'),
        no_GPS_or_following_TLE_or_new_RF_used=True,no_identity_or_calibration_change_applied=True,
        positive_residual_correlation_not_a_unique_catalogue_ID_and_absence_not_proof_of_different_emitters=True))
    fig,axes=plt.subplots(1,len(rows),figsize=(5*len(rows),4.5),squeeze=False)
    for ax,row in zip(axes[0],rows,strict=True):
        values=row['shuffled_frame_search_maxima']
        ax.hist(values,bins=16,color='#b9bac3',label='Shuffled frames; same search')
        ax.axvline(row['best']['residual_coherence'],color='#9659ad',lw=2,label='Simultaneous frames')
        ax.set_title(str(row['visit_index'])+' · '+row.get('control_kind','disputed pair'))
        ax.set_xlabel('Pilot-removed squared coherence');ax.set_ylabel('Controls');ax.legend(fontsize=7)
    fig.suptitle('DS23-0268 · recorded residual waveform test\nKnown pilot, affine inter-frame distortion and three-frame cycle removed; identical alias/frequency/delay search for controls')
    fig.tight_layout(rect=(0,0,1,.86));fig.savefig(OUT/'residual_waveform_coherence.png',dpi=160);plt.close(fig)
    print([(r['visit_index'],r.get('control_kind','disputed'),r['best']['residual_coherence'],r['shuffled_control_maximum'],r['empirical_search_corrected_rank']) for r in rows],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=('prepare','export','analyze','prepare_calibration','analyze_calibration'),required=True)
    parser.add_argument('--plan',default='plan.json')
    args=parser.parse_args()
    if args.stage=='prepare':prepare()
    elif args.stage=='export':export(args.plan)
    elif args.stage=='analyze':analyze()
    elif args.stage=='prepare_calibration':prepare_calibration()
    else:analyze_calibration()
