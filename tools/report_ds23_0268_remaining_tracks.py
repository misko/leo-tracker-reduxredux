"""Report-only GPS evaluation and scientific figures for the remaining tracks."""

import copy
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from investigate_ds23_0268_remaining_tracks import OUT,CASE,ARMS,load,corrected_observation
from probe_algo03_frame_peak_recovery import context,SOURCE
from probe_ds23_frequency_events import parameters,cached
from ds23_frequency_events import make_event_problem,attach_event_predictive,extend_event_associations
from audit_ds23_algo01_coverage import coverage
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import read,write,sha,ROOT
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis


def save(fig,name):
    fig.savefig(OUT/(name+'.png'),dpi=180,bbox_inches='tight');fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight');plt.close(fig)


def kernel_audits():
    scan,base,saved,original,problems=load();old=context(CASE)[4]
    ids={o['observation_id'] for o in read(SOURCE/CASE/'observations.json')};audits=[]
    for path in sorted((OUT/'reentry').glob('fine_kernel*.json')):
        record=read(path);changed=copy.copy(scan)
        changed.rx_basis=[record['basis_scale']*projected_receiver_basis(t['times'],spacing_s=10,width_s=15) for t in scan.tracks]
        labels=sorted({r['candidate_index'] for r in record['node']['seed']['rows']});_,receipts=phase_widths(scan,labels)
        hyper=old['hyperparameters_from_pre_RF_TLE_only'];means=forecast_phase_mean(receipts,hyper['shrinkage'])
        arms={}
        for arm,r in record['arms'].items():
            x=np.asarray(r['endpoint_east_north_km'])
            p=make_event_problem(changed,record['node'],np.asarray(record['mask'],bool),arm,np.asarray(r['phase_reference']),
                np.asarray(saved['powers']),means,hyper,saved['events'])
            attach_event_predictive(p,old['linear_entries'],saved['powers']);cached(p)
            delta=float(p.calculate(x)['negative_twice_elbo']-r['negative_twice_elbo'])
            if abs(delta)>1e-3:raise ValueError('kernel endpoint replay mismatch')
            extended=extend_event_associations(p,x,r['gates']);accepted={r['component']:r for r in extended['tracks']}
            for row in r['gates']['tracks']+r['linear_gates']:
                if row['compatible']:accepted[row['component']]=row
            arms[arm]=dict(error_km=position_error(r['endpoint_latlon']),objective_replay_difference=delta,
                **coverage(list(accepted.values()),scan.tracks,ids),accepted_rows=list(accepted.values()))
        audits.append(dict(name=path.stem,paired_valid=record['paired_valid'],arms=arms))
    write(OUT/'kernel_coverage.json',dict(rows=audits))
    return audits


def tables():
    inventory=read(OUT/'inventory.json');causal=read(OUT/'causal_refined.json');post=read(OUT/'postscan_refined.json')
    rows=[]
    for arm in ARMS:
        for c in causal['arms'][arm]:
            p=next(p for p in post['arms'][arm] if p['component']==c['component'])
            b,f=c['refined'][0]['best'],p['refined'][0]['best']
            rows.append(dict(arm=arm,component=c['component'],points=c['unassociated_points'],
                start_s=c['start_s'],end_s=c['end_s'],nominee=c['nominee'],
                causal_best_norad=b['norad'],causal_rms_hz=b['rms_hz'],causal_phase_s=b['phase_s'],causal_local_pass=b['passing'],
                post_best_norad=f['norad'],post_rms_hz=f['rms_hz'],post_phase_s=f['phase_s'],post_local_pass=f['passing']))
    with (OUT/'curved_candidate_summary.csv').open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return rows


def transfer_figure():
    document=read(OUT/'CH7_independent_receiver_transfer.json');fig,axes=plt.subplots(3,1,figsize=(14,11))
    row=document['arms']['c0'];colors=plt.get_cmap('tab10');families=sorted({t['norad'] for t in row['training']})
    for t in row['training']:
        axes[0].scatter(t['times'],np.asarray(t['residual'])/np.asarray(t['q']),s=10,alpha=.6,
            color=colors(families.index(t['norad'])),label=str(t['norad']))
    handles,labels=axes[0].get_legend_handles_labels();unique=dict(zip(labels,handles));axes[0].legend(unique.values(),unique.keys(),ncol=5,fontsize=9)
    axes[0].set_ylabel('Other-family residual (Hz at 11.5 GHz)');axes[0].set_title('Receiver correction training: ten accepted RX1 curves, five families; exclude CH7 T000')
    for arm,style in (('c0','-'),('fitted_c','--')):
        r=document['arms'][arm];s=next(t for t in r['tests'] if t['model']=='smooth' and t['law']=='RF_scaled')
        axes[1].plot(r['times'],r['baseline_residual_hz'],color='#e08a13',ls=style,lw=.9,
            label=f"{arm}: original own-phase residual {r['baseline_rms_hz']:.1f} Hz RMS")
        axes[1].plot(r['times'],s['residual_hz'],color='#16833f',ls=style,lw=1,
            label=f"{arm}: independent RX correction {s['rms_hz']:.1f} Hz RMS; local gates pass")
        axes[2].plot(r['times'],s['predicted_correction_hz'],color='#16833f',ls=style,label=f'{arm}: transferred RX1 correction')
    axes[1].set_ylabel('CH7 residual (Hz)');axes[1].legend(fontsize=9,ncol=2)
    axes[2].set_ylabel('Correction (Hz)');axes[2].legend(fontsize=9);axes[2].set_xlabel('Time from scan start (s)')
    for a in axes:a.axhline(0,color='black',lw=.6);a.grid(alpha=.18)
    fig.suptitle('A shared smooth receiver discrepancy can explain CH7 without fitting the correction to CH7\n'
        'Conditional diagnostic; leave-one-training-family tests expose dependence on 64908',fontsize=14)
    fig.tight_layout(rect=(0,0,1,.94));save(fig,'CH7_independent_receiver_transfer')


def kernel_figure(audits):
    baseline=read(OUT/'reentry/family_64333.json');fine=read(OUT/'reentry/fine_kernel_CH7.json')
    fig,axes=plt.subplots(2,1,figsize=(13,8),sharex=True)
    for arm,column in (('c0',0),('fitted_c',1)):
        for document,color,label in ((baseline,'#e08a13','Original RX basis + CH7'),(fine,'#16833f','Finer RX basis + CH7')):
            r=next(r for r in document['arms'][arm]['gates']['tracks'] if 'RX1-CH7-T000-' in r['component'])
            # Gate receipts retain statistics; reconstruct fitted residual using saved problem.
            scan,base,saved,coverage,problems=load();changed=copy.copy(scan);node=document['node'];old=context(CASE)[4]
            if document is fine:
                changed.rx_basis=[document['basis_scale']*projected_receiver_basis(t['times'],spacing_s=10,width_s=15) for t in scan.tracks]
            powers,means,hyper=parameters(scan,base,old);record=document['arms'][arm];x=np.asarray(record['endpoint_east_north_km'])
            p=make_event_problem(changed,node,np.asarray(document['mask'],bool),arm,np.asarray(record['phase_reference']),powers,means,hyper,saved['events'])
            attach_event_predictive(p,old['linear_entries'],powers)
            k=next(k for k,r in enumerate(p.rows) if 'RX1-CH7-T000-' in r['component']);t=scan.tracks[p.members[k]]
            residual=p.calculate(x)['conditional_residual_hz'][p.slices[k]]
            axes[column].plot(t['times'],residual,'.-',ms=4,lw=.8,color=color,
                label=f"{label}: RMS {r['conditional_residual_gate']['rms_hz']:.1f} Hz; {'PASS' if r['compatible'] else 'FAIL'}")
        axes[column].set_title(arm);axes[column].set_ylabel('Conditional residual (Hz)');axes[column].axhline(0,color='black',lw=.7);axes[column].grid(alpha=.18);axes[column].legend(fontsize=9)
    axes[-1].set_xlabel('Time from scan start (s)');fig.suptitle('Causal 64333 re-entry: finer shared RX covariance retains all 60 CH7 points\n'
        'Full paired gates pass; all previous position evidence retained; average prior variance matched',fontsize=14)
    fig.tight_layout(rect=(0,0,1,.92));save(fig,'CH7_joint_receiver_kernel_repair')


def report(rows,audits):
    inv=read(OUT/'inventory.json');linear=[r for r in read(OUT/'causal_screen.json')['arms']['c0'] if not r['curved']]
    lines=['# DS23-0268: 53923, CH7 at 150 seconds and remaining unassociated tracks','',
        'All association colors refer to the saved receiver-step + family-reentry model: 2,111/3,165 GLRT points (66.70%). '
        'This investigation preserves the frozen ALGO02 sources and observations. Following TLEs are retrospective diagnostics only.','',
        '## 53923 orbit overlays','',
        'Green points belong to 53923, blue to another accepted satellite, red are unassociated. Black is the current causal '
        'phase/orbit-mode fit; orange is the causal nominal orbit at that phase; purple is the post-scan orbit at the same phase. '
        'Receiver/band calibration is included, every alias branch intersecting the native CFO range is drawn. The residual '
        'is modulo 227272.727 Hz; residual panels clip at ±3 kHz, while CFO panels show all GLRT points. '
        'No per-fragment constant is removed in these all-point overlays.','',
        '![RX1](53923_all_GLRT_RX1_c0.png)','![RX2](53923_all_GLRT_RX2_c0.png)','',
        '[Fitted-c RX1](53923_all_GLRT_RX1_fitted_c.png) · [Fitted-c RX2](53923_all_GLRT_RX2_fitted_c.png)','',
        '## CH7 T000: what fails','',
        'This is an intact single graph piece: 60 points, 120.559–177.344 s. A quartic polynomial gives 152.0 Hz RMS '
        'and lag-1 correlation 0.258, passing the residual screen. The current nominated family is 64333. '
        'At its independently refined phase, causal 64333 gives 193.4/194.1 Hz RMS (c0/fitted-c). Its lag-1 '
        'correlation is about 0.526; the n=60 limit is 4/sqrt(60)=0.5164. The existing shared prediction also has '
        'a mean error because the entire family was removed earlier and its nuisance parameters revert toward their priors.','',
        'The post-scan 64333 orbit gives 197.4/198.6 Hz and still fails. A nearby alternative, 69468, gives '
        '190.6/191.9 Hz with post-scan elements and passes the local screen. Its c0 curve-score advantage over '
        'post-scan 64333 is only about 4.06, before phase priors and catalogue-search multiplicity: this is ambiguity, '
        'not an established new identity. All 1,402 candidates have a post-scan version; there is no fallback or '
        'candidate deletion. Epoch selection is earliest after scan end, earliest collection tie-break, fixed 48-hour window.','',
        '![CH7 orbit and residuals](CH7_150s_orbits_and_residuals.png)','',
        '## Independent receiver test and joint prototype','',
        'Ten accepted curved RX1 controls across five families fit an extra smooth receiver correction without any CH7 '
        'measurements. A 10-second-spaced, 15-second-width Gaussian basis (200 Hz coefficient prior; 300 Hz control-curve '
        'constant prior) predicts a correction of roughly -185 to -38 Hz on the target. The RF-scaled variant reduces '
        'CH7 RMS to 167.6/168.1 Hz; both local screens pass. Additive corrections give 169.1/169.6 Hz. An affine '
        'receiver correction does not help. These are conditional diagnostics, not a full covariance validation.','',
        '**Limitation:** removing 64908 from the extra-correction training loses the all-gate pass; other single-family '
        'removals retain it. Baseline calibration remains frozen in this leave-one-family diagnostic. Thus the evidence '
        'does not yet uniquely distinguish a receiver effect from 64908-specific orbital/calibration tension.','',
        '![Independent transfer](CH7_independent_receiver_transfer.png)','',
        'A full causal joint prototype replaces the original 30-second-spaced, 20-second-width RX basis with a '
        '10-second-spaced, 15-second-width basis. Its amplitude is rescaled so average pointwise prior variance on '
        'the fixed 0–300 s grid equals the original. The exact Gaussian marginal volume penalizes added flexibility. '
        'Original GLRT, graph tracks, causal priors, weights, event time, cold regional start and search budgets are retained. '
        'Both original receiver/band nuisance sets remain; linear tracks never calibrate. This is one-scan development.','',
        '| Prototype | Paired gates | c0 / fitted-c error (km) | Associated GLRT, c0 / fitted-c |','|---|---|---|---|']
    for r in audits:
        a,b=r['arms']['c0'],r['arms']['fitted_c']
        lines.append(f"| {r['name']} | {'PASS' if r['paired_valid'] else 'FAIL'} | {a['error_km']:.3f} / {b['error_km']:.3f} | {a['associated_original_winners']} / {b['associated_original_winners']} |")
    lines += ['', 'Current original-basis receiver-reentry baseline: 5.359/5.485 km, 2,111 associated GLRT in each arm. '
        'The finer-kernel 64333 prototype retains 2,171 (68.59%) in each arm, versus 66.70% before. The alternative '
        '69468 fails even with the finer causal receiver kernel, so its post-TLE local pass does not transfer to '
        'a valid causal shared-parameter solution. Invalid rows are diagnostics, never accepted replacements. '
        'A successful CH7 retention does not solve the roughly 5 km '
        'location error. Geographic reference is read only here for error evaluation; no position is selected using it.','',
        '![Joint causal repair](CH7_joint_receiver_kernel_repair.png)','',
        '## Where the remaining evidence points','',
        f"Unassociated total: {inv['unassociated']}; {inv['outside_graph']} outside graph tracks; 334 in 21 nearly-linear tracks; "
        '338 in eight wholly unassociated curved tracks plus three rejected points in an otherwise accepted curve. '
        f"{sum(bool(r['passing_norads']) for r in linear)}/21 nearly-linear tracks have a local catalogue/phase match, "
        'but an independently fitted phase is not a shared-family validation and linear tracks cannot calibrate.','',
        '| Track | Unassociated points | Causal best / RMS Hz / local pass | Post best / RMS Hz / local pass |',
        '|---|---:|---|---|']
    for r in rows:
        if r['arm']!='c0':continue
        name=r['component'].split('-RF')[0].replace(CASE+'-','')
        lines.append(f"| {name} | {r['points']} | {r['causal_best_norad']} / {r['causal_rms_hz']:.1f} / {r['causal_local_pass']} | {r['post_best_norad']} / {r['post_rms_hz']:.1f} / {r['post_local_pass']} |")
    lines += ['', '![Remaining curved tracks](remaining_curved_track_gallery.png)','',
        'Local candidates are shape probes at the frozen RF position, with a Gaussian 1 kHz fragment constant and an '
        'independent phase searched over ±15 seconds. They do not include a phase prior in the ranking or new candidate '
        'orbit modes. The coarse grid is 0.25 s; the best four candidates are refined over ±0.3 s at 0.01 s resolution. '
        'No supplied evaluation coordinate enters either search. Local passes are not confirmed identities.','',
        'Eight original-basis causal joint re-entry trials were tested: each main family separately, 69468 as CH7 alternative, '
        'and all five locally passing curves together. None passes all original paired gates. 66797 and remapped 63963 '
        'conflict with retained 63901; 59342 and 67953 fail structured-residual gates; the extra 69445 curve conflicts '
        'with the shared family solution; 64333 and 69468 retain CH7 correlation/shape failures. A profile passing at '
        'its own phase can fail when phase/orbit/hardware parameters are shared with other tracks.','',
        'The current extension stage considers only already accepted curved-supported satellite families. Therefore a '
        'removed family such as 66797 or 59342 cannot recover through that stage, and the alternative 63963 nomination '
        'is never tried there. Original mask trimming plus frozen family nominations creates a recovery limitation. '
        'The strictly all-gate acceptance rule also couples useful proposals to marginal failures elsewhere; e.g. '
        '63963 re-entry causes retained 63901 slope statistics of 3.006/3.019 against a limit of 3.','',
        '## Nearly-linear fragments: candidate inventory','',
        'A concrete excluded family is 69238: RX1 CH2 T007, CH3 T006, CH7 T005 and CH8 T004 contain 53 points '
        'at 17–30 s. Independent local probes choose phases around -1.5 s for all four. There is no accepted curved '
        'anchor for that satellite, so the existing extension stage cannot try it. This is useful corroboration, '
        'but it does not authorize using these tracks to recalibrate receiver offsets/drifts. A predictive catalogue '
        'association stage can test such families with radio/position calibration frozen and causal orbit uncertainty '
        'integrated. The candidate lists below are diagnostics, not confirmed associations.','',
        '| Fragment | Points | Time s | Best locally passing candidate, or best failed candidate | RMS Hz | Local pass |',
        '|---|---:|---|---:|---:|---|']
    for r in linear:
        b=r['best_passing'] or r['candidates'][0]
        lines.append(f"| {r['component'].split('-RF')[0].replace(CASE+'-','')} | {r['points']} | {r['start_s']:.1f}–{r['end_s']:.1f} | {b['norad']} | {b['rms_hz']:.1f} | {r['best_passing'] is not None} |")
    lines += ['',
        '## Recommendation','',
        'Retain the intact CH7 curve as evidence. Evaluate the normalized finer receiver covariance on other scans, '
        'with c0/fitted-c and independent-family transfer controls. Keep multiple nearby identities when they are '
        'not distinguishable. Add a bounded catalogue re-nomination/re-entry stage for rejected curved families, then '
        'require joint shared-parameter consistency. Do not weaken noise gates or declare identities from visual '
        'alignment alone. The 379 points outside graph tracks require a separate graph/alternative-peak audit; they '
        'were not proven to be clutter by this study.','',
        '## Reproduction and provenance','',
        'Run with `PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python`: '
        '`tools/investigate_ds23_0268_remaining_tracks.py --stage inventory`, `banks`, `screen`, `refine`, '
        '`reentry`, `alternate`, `transfer`, `kernel`; render `tools/plot_ds23_0268_remaining_tracks.py --stage orbit` '
        'and `screens`; then `tools/report_ds23_0268_remaining_tracks.py`. Export postscan elements first through '
        'the read-only adapter `tools/export_ds23_postscan_tles.py --directory reports/2026_10_19_algo02_ds23_full/DS23-0268`. '
        'Archive reads require the existing archive permissions. No new RF collection or IQ remeasurement occurred.','',
        'Machine-readable receipts: [inventory](inventory.json), [candidate table](curved_candidate_summary.csv), '
        '[causal refined search](causal_refined.json), [post refined search](postscan_refined.json), '
        '[following TLE provenance](postscan_tles.json), [receiver transfer](CH7_independent_receiver_transfer.json), '
        '[kernel coverage](kernel_coverage.json), [re-entry execution](reentry_execution.json).']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n')
    write(OUT/'report_provenance.json',dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in
        (ROOT/'tools/investigate_ds23_0268_remaining_tracks.py',ROOT/'tools/plot_ds23_0268_remaining_tracks.py',
         ROOT/'tools/export_ds23_postscan_tles.py',ROOT/'tools/report_ds23_0268_remaining_tracks.py')},
        future_TLE_diagnostic_separate=True,reference_only_in_reporter=True,original_data_unchanged=True))


if __name__=='__main__':
    rows=tables();audits=kernel_audits();transfer_figure();kernel_figure(audits);report(rows,audits)
