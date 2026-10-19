"""Radio-only curve diagnostics and separately evaluated paired position controls."""

import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from probe_ds23_raw_pilot_refinement import OUT
from probe_ds23_refined_curve_position import proposed_delta
from report_algo01_ds23_sample import position_error
from run_algo01_ds23_sample import read,write,sha

CASES=('DS23-0202','DS23-0274')
METHODS=('archived','fixed_epoch_CFO','joint_CFO_epoch_rate')
COLORS=('0.55','tab:blue','tab:orange')


def polynomial(t,y,degree):
    z=(np.asarray(t)-np.mean(t))/max(1.,float(np.ptp(t)))
    a=np.vander(z,degree+1,increasing=True);q,_=np.linalg.qr(a)
    prediction=q@(q.T@y);residual=y-prediction
    return dict(prediction=prediction,residual=residual,
        RMS_hz=float(np.sqrt(np.mean(residual**2))),
        dof_corrected_sigma_hz=float(np.sqrt(np.sum(residual**2)/max(1,len(y)-degree-1))),
        lag_one_correlation=float(np.corrcoef(residual[:-1],residual[1:])[0,1]),
        half_mean_step_hz=float(np.mean(residual[len(y)//2:])-np.mean(residual[:len(y)//2])))


def choose_degree(t,y,sigma):
    eligible=[d for d in range(5) if len(y)>=4*(d+1)]
    return min(eligible,key=lambda d:np.sum(polynomial(t,y,d)['residual']**2)/sigma**2+(d+1)*np.log(len(y)))


def run():
    all_tracks=[];summaries={};position=[]
    for case in CASES:
        path=OUT/(case+'_tracks.json');d=read(path);lookup={r['point']['observation_id']:r for r in d['rows']}
        sigma=read(OUT.parent/'2026_10_18_algo01_ds23_random20'/case/'radio_noise.json')['constant_radio_sigma_hz']
        fig,axes=plt.subplots(len(d['panel_metadata']['tracks']),2,figsize=(15,3.1*len(d['panel_metadata']['tracks'])),squeeze=False,constrained_layout=True)
        for track,ax in zip(d['panel_metadata']['tracks'],axes,strict=True):
            t=np.array(track['times']);y=np.array(track['values']);rows=[lookup[o] for o in track['observation_ids']]
            degree=choose_degree(t,y,sigma);metrics={};name=track['key'].split('-RF')[0]
            for method,color in zip(METHODS,COLORS,strict=True):
                delta=np.zeros(len(y)) if method=='archived' else np.array([r[method]['CFO_hz']-r['archived_CFO_hz'] for r in rows])
                values=y+delta;fit=polynomial(t,values,degree)
                effective_t=t.copy() if method=='archived' else t+np.array([r[method]['effective_time_from_probe_start_s']-.010 for r in rows])
                adjusted=polynomial(effective_t,values,degree)
                safe_delta=delta if method=='archived' else np.array([proposed_delta(r,method)[0] for r in rows])
                safe=polynomial(t,y+safe_delta,degree)
                metrics[method]=dict(RMS_hz=fit['RMS_hz'],lag_one_correlation=fit['lag_one_correlation'],
                    half_mean_step_hz=fit['half_mean_step_hz'],dof_corrected_sigma_hz=fit['dof_corrected_sigma_hz'],
                    effective_time_adjusted_RMS_hz=adjusted['RMS_hz'],boundary_fallback_RMS_hz=safe['RMS_hz'])
                ax[0].plot(t,values/1000,'.',color=color,ms=3,label=method)
                ax[1].plot(t,fit['residual'],'.-',color=color,ms=3,lw=.65,
                    label=f'{method}: {fit["RMS_hz"]:.1f} Hz')
            record=dict(case=case,track=name,receiver=track['receiver'],channel=track['channel'],
                points=len(y),degree_selected_on_archived_CFO_only=degree,metrics=metrics,
                fixed_frequency_boundary_count=sum(r['fixed_epoch_CFO']['frequency_search_boundary'] for r in rows),
                joint_any_boundary_count=sum(any(r['joint_CFO_epoch_rate'][k] for k in
                    ('frequency_search_boundary','epoch_search_boundary','code_rate_search_boundary')) for r in rows),
                original_observation_ids=track['observation_ids'])
            all_tracks.append(record)
            ax[0].set(title=f'{name} · N={len(y)} · degree {degree}',ylabel='Lifted CFO (kHz)',xlabel='Scan time (s)')
            ax[1].axhline(0,color='k',lw=.5);ax[1].set(title='Same degree; all original points',ylabel='Residual (Hz)',xlabel='Scan time (s)')
            for a in ax:a.grid(alpha=.2);a.legend(fontsize=7)
        fig.suptitle(f'{case}: archived IQ · no orbit, satellite identity or GPS in radio refinement')
        fig.savefig(OUT/(case+'_radio_curves.png'),dpi=150);plt.close(fig)
        replay=read(OUT/(case+'_score_replay.json'))
        summaries[case]=dict(points=len(d['rows']),tracks=len(d['panel_metadata']['tracks']),
            exact_archived_score_replays=replay['matched'],unresolved_score_replays=replay['total']-replay['matched'],
            raw_windows_read=d['panel_metadata']['raw_windows_read'],max_raw_windows=d['panel_metadata']['max_raw_windows'],
            sample_rate_hz=d['panel_metadata']['sample_rate_hz'],
            native_replay_abs_CFO_difference_median_hz=float(np.median([abs(r['replay']['CFO_difference_hz']) for r in d['rows'] if r['replay'] is not None])),
            library_matches_its_build_receipt=True,identity_of_actual_capture_binary_proven=False)
        result=read(OUT/(case+'_position.json'))
        for method in ('incumbent','fixed_epoch_CFO','joint_CFO_epoch_rate'):
            arms=result['incumbent_arms'] if method=='incumbent' else result['results'][method]['reported_arms']
            for arm,v in arms.items():
                position.append(dict(case=case,method=method,arm=arm,error_km=position_error(v['endpoint_latlon']),
                    residual_RMS_hz=v['RMS_hz'],calibration_points=v['active_points'],
                    paired_valid=True if method=='incumbent' else result['results'][method]['paired_valid'],
                    active_calibration_points_changed=0 if method=='incumbent' else result['results'][method]['updates']['active_calibration_points_changed']))
    write(OUT/'summary.json',dict(cases=summaries,tracks=all_tracks,position=position,
        reanalysed_IQ_observations=240,reanalysed_original_graph_curves=7,target_mean_and_median_km=.5,target_met=False,
        development_diagnostics_not_independent_validation=True,full_DS23_not_evaluated=True,
        source_sha256=sha(Path(__file__))))
    flat=[]
    for r in all_tracks:
        for method,m in r['metrics'].items():
            flat.append(dict(case=r['case'],track=r['track'],points=r['points'],degree=r['degree_selected_on_archived_CFO_only'],method=method,**m))
    for name,rows in [('curve_metrics.csv',flat),('position_comparison.csv',position)]:
        with (OUT/name).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    fig,ax=plt.subplots(figsize=(11,4.5),constrained_layout=True)
    for method,offset,color in zip(METHODS,(-.24,0,.24),COLORS,strict=True):
        ax.bar(np.arange(len(all_tracks))+offset,[r['metrics'][method]['RMS_hz'] for r in all_tracks],width=.22,color=color,label=method)
    ax.set_xticks(range(len(all_tracks)),[r['track'].replace('DS23-0','') for r in all_tracks],rotation=25,ha='right',fontsize=8)
    ax.set(ylabel='Polynomial residual RMS (Hz)',title='Radio-only refinement helps RX2 much more than RX1 · degree fixed from archived CFO')
    ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8);fig.savefig(OUT/'radio_RMS_comparison.png',dpi=160);plt.close(fig)
    table=['| Scan / track | Points | Degree | Archived RMS | Fixed epoch RMS | Joint epoch/rate RMS |',
           '|---|---:|---:|---:|---:|---:|']
    for r in all_tracks:
        rms=[r['metrics'][m]['RMS_hz'] for m in METHODS]
        table.append(f'| {r["track"]} | {r["points"]} | {r["degree_selected_on_archived_CFO_only"]} | '+ ' | '.join(f'{v:.2f} Hz' for v in rms)+' |')
    ptable=['| Scan | Method | c=0 error km | Fitted-c error km | Changed calibration points |',
            '|---|---|---:|---:|---:|']
    for case in CASES:
        for method in ('incumbent','fixed_epoch_CFO','joint_CFO_epoch_rate'):
            rr=[r for r in position if r['case']==case and r['method']==method]
            ptable.append(f'| {case} | {method} | {rr[0]["error_km"]:.4f} | {rr[1]["error_km"]:.4f} | {rr[0]["active_calibration_points_changed"]} |')
    body='''# DS23: bounded archived-IQ CFO refinement

Re-analysis of seven complete early graph curves (240 GLRT observations) finds
a substantial estimator-dependent component on RX2: local known-pilot fitting
reduces its polynomial residual RMS from about41–99Hz to9–12Hz. RX1 improves
less. This is radio-only evidence, not proof of the physical cause or of an
unbiased satellite position. Partial position refits with the old uncertainty
law improve scan274 by about20m and leave scan202 essentially unchanged.
The0.5km goal remains unmet; the full413 DS23 recordings are not evaluated.

## Fixed radio-only experiment

Use the existing read-only short-window port and hash-verified declared segment
manifests. Select the largest original active-curvature graph track per RX/band,
12–96 points, all visits below1024, without satellite labels, GPS or position
errors. Export every selected point; no missing-group replacement. Cases202
and274 are development diagnostics selected in earlier failure/receiver studies,
not an untouched validation set. Case202 has three eligible groups;274 has four.
Never publish raw-IQ panel payloads. Their hashes and manifest receipts are in
the full result JSON inside evidence.tar.gz; replay needs authorized local data.

The local model uses the published edge-pilot template, Fourier interpolation,
all complete guarded frames, an independent complex amplitude and DC per frame,
and direct continuous carrier-frequency fitting. The fixed variant retains
the archived epoch and nominal code rate. The joint variant searches epoch
within0.75sample and one code-rate parameter within40ppm. This one parameter
ties frame cadence to intra-frame modulation; it does not distinguish every
physical frame/sample/carrier clock. Unknown channel response, fading,
interference and transmitter clock behavior remain possible model errors.

Carrier search is local and bounded; clipped solutions remain flagged. Joint
epoch/rate boundaries and exact-versus-control margin are recorded. Disjoint
odd/even-frame fits are also retained; their effective times differ, so their
CFO difference cannot be interpreted as independent measurement noise without
accounting for Doppler rate. Three synthetic tests check off-grid CFO under
independent frame phases, distinct code/carrier rates and disjoint-frame timing.
Three further tests check alias-preserving updates, boundary fallbacks, wrong
peak rejection and reconstruction of an unpersisted acquired-CFO residual bin.

## Radio fits, with the original degree fixed

Degrees0–4 are compared using archived-CFO RSS/original-radio-sigma² +
(degree+1)log(N), at least four points per coefficient. The chosen degree and
all original points then remain fixed for every refined curve. Table values
show the raw diagnostic estimates, including flagged boundary solutions;
the CSV additionally reports boundary-fallback RMS and effective-time variants.
A polynomial forces zero fitted mean/trend; this alone does not establish white
noise. Lag-one correlation and half-track mean steps are provided in the CSV.

TABLE

![RMS by curve](radio_RMS_comparison.png)
![Scan202 CFO and residuals](DS23-0202_radio_curves.png)
![Scan274 CFO and residuals](DS23-0274_radio_curves.png)

These are independent radio-model fits to the same stored observations, not
additional independent measurements or extra satellite associations. Values
are updated by canonical observation ID before restoring the original integer
alias lift. The actual repository alias period is1/(4.4microseconds), about
227272.727Hz. No500Hz template correction is applied to a lifted graph CFO.

## Acquisition provenance still matters

The experimental native library exactly matches its own build receipt, but its
CFOs do not exactly reproduce the archived acquisition. Its static500Hz FFT
inverse correction is therefore not qualified for these measurements.
The owned public fractional GLRT64 scorer reproduces archived exact/control
scores for67/74 observations in202 and141/166 in274. A bounded search over
five possible unpersisted acquired-CFO residual bins does not resolve the
remaining7 and25 cases. These remain explicit provenance/configuration
exceptions, not silently declared corrupt or repaired. The tracking contract
does not persist the original acquired CFO. Captured-binary/config identity,
frame support and alternative acquisition aliases need further qualification.

The archived normalized GLRT score uses symbol-correlation coherence, whereas
the local projection score uses raw IQ energy. Different numerical score
scales are not evidence of wrong pilots, nor are they comparable evidences.
More in-sample explained energy does not prove more accurate CFO.

## Partial position intervention: separately measured

PTABLE

Use the same causal catalogue, pre-RF phase-history distribution, physical
orbit modes, radio uncertainty, family powers, fragment constants, active
mask, aliases, labels, timestamps and five-by48 search budget as the incumbent.
Every fit starts at the center of the25×25km box37.906,−122.545. The supplied
GPS enters only this reporting tool. Both c arms use identical changed values.
Boundary estimates revert to original CFO rather than remove observations;
joint control failures also revert. If either arm fails a native gate, report
the original incumbent pair and preserve raw failures. All four new paired
trials pass the final gates. Unrefined points remain exactly unchanged.

Only37 active calibration points change in202: the two selected RX1 curves
are outside the incumbent calibration mask. In274, fixed refinement changes
152 and joint refinement165 active points. These are deliberately partial
interventions, not full-scan re-acquisition. The old radio-noise law has a40Hz
floor and receiver-blind variance learning; it does not give the newly cleaner
RX2 curves their apparent9–12Hz precision. Changing that uncertainty model
requires a separate controlled study. Lower radio RMS alone does not establish
the correct weighting or solve position/phase/receiver degeneracy.

## Next qualification

Keep the completed confidence and simultaneous-family tests as controls.
Pin actual acquisition/config provenance, broaden local CFO searches only by
a fixed RF rule, and calibrate per-receiver/band refined uncertainty through
independent frames or predictive radio fits before changing localization
weights. Test whether the more precise RX2 evidence predicts other receiver
curves and independently improves position, with matched c arms and all scans
retained. Preserve failures and use untouched scans before promoting a default.
Do not force an answer by GPS-favored identities or weaker physical priors.

## Evidence and reproduction

[Summary](summary.json) · [Curve metrics](curve_metrics.csv) ·
[Position comparison](position_comparison.csv) · [Full numerical evidence](evidence.tar.gz) ·
[Inventory](evidence_inventory.json) · [Source snapshots](source_snapshot/) ·
[Earlier weighting, family and secondary-peak study](../2026_10_19_ds23_association_evidence/README.md).

Use repository venv, PYTHONPATH=src:tools, BLAS/OMP threads1. Export using
export_ds23_curved_pilot_panel.py through the authorized recording read port,
redirecting stdout to the local NPZ panel. Run probe_ds23_raw_pilot_refinement.py
with --panel-label tracks; replay_ds23_archived_pilot_scores.py;
probe_ds23_refined_curve_position.py; then this reporter, each with --case for
the two scans where applicable. Existing initial six-point exploratory files
are not mixed into these full-curve results. Raw recording mutation and new RF
collection are absent. Source snapshots and receipt hashes pin these experiments.
'''.replace('PTABLE','\n'.join(ptable)).replace('TABLE','\n'.join(table))
    (OUT/'README.md').write_text(body)
    print('\n'.join(table));print('\n'.join(ptable))


if __name__=='__main__':run()
