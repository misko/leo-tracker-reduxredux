"""Report complete-target IQ refinement, fresh identity, and rejected model fits."""
import argparse,csv,gzip,hashlib,json,shutil
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays
from annotation_partition_plan import require_distinct_annotation
from leo.analysis.research.grouped_prediction import replay_split


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();s=args.study;hashes={};evidence={}
    def load(path):
        d=read(path);hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();evidence[str(path)]=compact_replays(compact_evidence(d));return d
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    root=s/'60342-native-iq-refinement-v1';plan=load(root/'plan.json');panel=load(root/'panel/manifest.json');local=load(root/'result.json');terminal=load(root/'execution.json')
    assert len(terminal)==4 and all(r['status']=='complete' for r in terminal)
    assert panel['raw_authority_matches_tracking'] and panel['plan_sha256']==hashes[str(root/'plan.json')]
    for name,digest in local['worker_hashes'].items():
        w=load(Path(name));assert hashes[name]==digest
        assert w['panel_manifest_sha256']==hashes[str(root/'panel/manifest.json')]
    for p in panel['points']:
        if hashlib.sha256((root/'panel'/p['array']).read_bytes()).hexdigest()!=p['array_sha256']:raise ValueError('IQ panel changed')
    native=load(s/'omitted-60342-native-measurements-v1/result.json');oldroot=s/'omitted-predictive-distinct-inclusion-v3/c2d4137494f1b3e28340/trial';newroot=s/'60342-refined-inclusion-v1'
    old=load(oldroot/'new_family.json');oldcontrol=load(oldroot/'control.json');new=load(newroot/'new_family.json');newcontrol=load(newroot/'control.json');pr=load(newroot/'protocol.json');audit=load(newroot/'exact_owner_replay.json')
    for name,digest in audit['source_hashes'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('exact replay source changed')
    ann=load(s/'60342-refined-annotation-v1/result.json');annpr=load(s/'60342-refined-annotation-v1/protocol.json');require_distinct_annotation(ann,annpr)
    times=np.array([r['point']['time_s'] for r in local['rows']]);ids=[r['point']['observation_id'] for r in local['rows']]
    if ids!=[r['observation_id'] for r in native['points']] or set(ids)!={r['observation_id'] for r in plan['points']}:raise ValueError('point order or scope changed')
    signatures=[]
    for fold in ann['folds']:
        train,held=replay_split(times,fold['split']);signatures.append(tuple(np.flatnonzero(held)))
    assert len(set(signatures))==3
    methods=('fixed_epoch','joint_all','joint_odd','joint_even');rows=[];stats=[];cross=[]
    for r,n in zip(local['rows'],native['points'],strict=True):
        m=r['methods'];row=dict(observation_id=r['point']['observation_id'],time_s=r['point']['time_s'],archived_CFO_hz=r['point']['CFO_hz'],native_polynomial_residual_hz=n['original_polynomial_residual_hz'])
        for method in methods:row[method+'_delta_hz']=m[method]['CFO_hz']-r['point']['CFO_hz']
        row.update(odd_even_difference_hz=m['joint_odd']['CFO_hz']-m['joint_even']['CFO_hz'],offset_samples=m['joint_all']['offset_samples'],modulation_ppm=m['joint_all']['modulation_ppm'])
        rows.append(row)
    for method in ('archived',*methods):
        delta=np.zeros(len(rows)) if method=='archived' else np.array([r[method+'_delta_hz'] for r in rows])
        for arm in ('c0','fitted_c'):
            residual=np.array(native['arms'][arm]['residual_hz'])+delta
            stats.append(dict(method=method,arm=arm,points=len(rows),RMS_hz=float(np.sqrt(np.mean(residual**2))),mean_hz=float(residual.mean()),centered_scatter_hz=float(np.std(residual)),
                correction_RMS_hz=float(np.sqrt(np.mean(delta**2))),search_boundary_points=0 if method=='archived' else sum(any(v for k,v in r['methods'][method].items() if k.endswith('_search_boundary')) for r in local['rows'])))
    for method in ('joint_odd','joint_even'):
        delta=np.array([r['methods'][method]['complement_score']-r['methods'][method]['complement_score_at_original'] for r in local['rows']])
        cross.append(dict(method=method,points=len(rows),complement_score_improved=int((delta>0).sum()),mean_complement_gain=float(delta.mean())))
    trials=[]
    for label,control,addition in [('archived',oldcontrol,old),('refined',newcontrol,new)]:
        for arm,z in addition['arms'].items():
            d=z['family']['diagnostics'][0];before=set(control['arms'][arm]['proposed_associated_ids']);after=set(z['proposed_associated_ids'])
            assert after-before==set(ids) and not before-after
            trials.append(dict(variant=label,arm=arm,control_error_km=error(control['arms'][arm]),addition_error_km=error(z),RMS_hz=d['profile_RMS_hz'],
                paired_valid=addition['paired_valid'],lag1=d['noise']['lag1_acf'],lag1_limit=4/np.sqrt(len(ids)),slope_z=d['noise']['slope_z'],step_z=d['noise']['maximum_step_z'],
                mean_z=d['noise']['mean_z'],quadratic_BIC_gain=d['noise']['quadratic_bic_gain'],objective=z['negative_twice_elbo']))
    for arm in ('c0','fitted_c'):
        if abs(oldcontrol['arms'][arm]['negative_twice_elbo']-newcontrol['arms'][arm]['negative_twice_elbo'])>1e-5:raise ValueError('refinement changed control objective')
    fig,axs=plt.subplots(2,2,figsize=(14,8),layout='constrained')
    for col,arm in enumerate(('c0','fitted_c')):
        base=np.array(native['arms'][arm]['residual_hz'])
        for method in ('archived','joint_all','joint_odd','joint_even'):
            delta=0 if method=='archived' else np.array([r[method+'_delta_hz'] for r in rows]);axs[0,col].plot(times,base+delta,'.-',lw=.7,label=method)
        axs[0,col].set(title=arm+' / original orbit, receiver and bias held fixed',ylabel='Residual (Hz)')
        for label,doc in [('archived',old),('refined',new)]:
            d=doc['arms'][arm]['family']['diagnostics'][0];axs[1,col].plot(times,np.array(d['raw_residual_hz'])-d['profile_bias_hz'],'.-',label=label)
        axs[1,col].set(title=arm+' / after separate complete position fits',ylabel='Residual (Hz)')
    for ax in axs.flat:ax.axhline(0,c='k',lw=.5);ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    save(fig,'residual_comparison.png')
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for method in ('joint_all','joint_odd','joint_even'):axs[0,0].plot(times,[r[method+'_delta_hz'] for r in rows],'.-',lw=.7,label=method)
    axs[0,0].set(ylabel='Refined − archived CFO (Hz)');axs[0,1].plot(times,[r['odd_even_difference_hz'] for r in rows],'.-');axs[0,1].set(ylabel='Odd − even CFO (Hz)')
    axs[1,0].plot(times,[r['offset_samples'] for r in rows],'.-');axs[1,0].set(ylabel='Epoch adjustment (samples)')
    for method in ('joint_odd','joint_even'):axs[1,1].plot(times,[r['methods'][method]['complement_score']-r['methods'][method]['complement_score_at_original'] for r in local['rows']],'.-',label=method)
    axs[1,1].axhline(0,c='k',lw=.5);axs[1,1].set(ylabel='Complementary-frame score gain')
    for ax in axs.flat:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2)
    axs[0,0].legend(fontsize=7);axs[1,1].legend(fontsize=7);save(fig,'measurement_validation.png')
    jointroot=s/'reconciled-role-v06-joint-v1';jexec=load(jointroot/'execution.json');jp=jointroot/'0a6c35197cfa7afb-69713/trial'
    jc=load(jp/'control.json');jv=load(jp/'new_family.json');ja=load(jp/'exact_owner_replay.json');common=load(jp/'common_residual_audit.json');joint=[]
    fig,axs=plt.subplots(1,2,figsize=(13,4),layout='constrained')
    for ax,(arm,z) in zip(axs,jv['arms'].items(),strict=True):
        for d in z['family']['diagnostics']:
            n=d['noise'];joint.append(dict(arm=arm,component=d['component'],points=len(d['times_s']),RMS_hz=d['profile_RMS_hz'],lag1=n['lag1_acf'],lag1_limit=4/np.sqrt(len(d['times_s'])),noise_pass=n['noise_screen_pass'],control_error_km=error(jc['arms'][arm]),joint_error_km=error(z)))
            ax.plot(d['times_s'],np.array(d['raw_residual_hz'])-d['profile_bias_hz'],'.-',lw=.7,label=d['component'].split('-RF')[0])
        ax.set(title=arm,xlabel='Scan time (s)',ylabel='Joint-family residual (Hz)');ax.legend(fontsize=7);ax.grid(alpha=.2);ax.axhline(0,c='k',lw=.5)
    save(fig,'v06_joint_residuals.png')
    csvout('measurement_points.csv',rows);csvout('fixed_prediction_metrics.csv',stats);csvout('cross_frame_validation.csv',cross);csvout('position_trials.csv',trials);csvout('v06_joint.csv',joint)
    previous=args.previous
    ledger=list(csv.DictReader((previous/'annotation_ledger.csv').open()))
    for r in ledger:
        if r['track_id']=='c2d4137494f1b3e28340':
            r['prior_predictive_research_inclusion']=r['predictive_research_inclusion']
            r['predictive_research_inclusion']='withheld_after_native_IQ_residual_review'
            r['refined_measurement_inclusion_source']=str(newroot)
            r['refined_measurement_annotation_source']=str(s/'60342-refined-annotation-v1/result.json')
        if r['track_id'] in ('16384d9912f2166bc0b0','9a908edd303d290b19b1'):
            r['same_family_joint_source']=str(jp)
            r['same_family_joint_status']=jexec[0]['status']
            r['same_family_joint_norad']='69713'
    csvout('annotation_ledger.csv',ledger)
    shutil.copyfile(previous/'remaining_role_candidates.json',out/'remaining_role_candidates.json')
    write(out/'summary.json',dict(points_refined=len(rows),raw_windows_verified=panel['raw_windows_read'],fresh_identity=ann['annotation'],
        refined_position_qualified=new['paired_valid'] and audit['all_verified'],v06_joint_status=jexec[0]['status'],
        odd_even_RMS_hz=float(np.sqrt(np.mean([r['odd_even_difference_hz']**2 for r in rows]))),new_accepted_points=0,production_changed=False,full_goal_complete=False))
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    strong=sorted(rows,key=lambda r:abs(r['joint_all_delta_hz']),reverse=True)[:3]
    (out/'README.md').write_text(f'''# Native IQ refinement resolves frequency excursions, but reveals residual model structure

The complete 34-point AUTO-c1258263 / RX2 CH4 / 60342 target was remeasured from its existing 2.5 MS/s fast recording. The local pilot fit corrects the three largest frequency excursions without using GPS, TLEs or orbital predictions. Fresh randomized identity validation still selects 60342. The refined full-position trial reduces error relative to the earlier raw-target inclusion, but fails residual correlation checks and remains rejected. No new accepted association points or production change are claimed.

## Raw authority and estimator

All **{panel['raw_windows_read']} source windows** were consumed through the verified ShortWindowReader, completing chunk and window hash checks. Their combined raw authority matches the archived GLRT source. All 34 target observations are exported, including quiet points; no point is selected or removed by residual. The estimator fits carrier frequency, sub-sample epoch and local code rate, with separate complex gains and DC per pilot frame. Search bounds remain ±800 Hz, ±0.75 samples and ±40 ppm, with one start and 16 optimizer iterations. Timing/code-rate variables describe the local waveform; they are not new satellite parameters or LNB drift calibration.

Odd and even pilot frames are independently fitted and scored on their complementary frames. They still share the original full-window detection/epoch nomination, so this is conditional cross-frame evidence, not fully independent acquisition. All four worker processes completed. IQ payloads remain local; compact evidence and hashes are published.

{table(strong,['time_s','joint_all_delta_hz','joint_odd_delta_hz','joint_even_delta_hz','odd_even_difference_hz'])}

![Measurement changes and cross-frame evidence](figures/measurement_validation.png)

All joint fits stay inside their frequency, epoch and code-rate search bounds. Odd/even CFO disagreement is about **17.7 Hz RMS** across all 34 observations and approximately 6–10 Hz at the three largest corrected excursions. Both complementary-frame scores improve at each of those three points. Across the complete curve, improvement is less uniform: only **10/34 odd fits** and **18/34 even fits** improve their complementary scores over the archived parameters. This supports the large corrections but does not establish a universal gain from re-estimating every already-good point.

## Frequency agreement and fresh annotation

The following metrics hold the old orbit, receiver correction, position and track bias fixed; no new curve is fit to produce this comparison.

{table([r for r in stats if r['arm']=='fitted_c'],['method','points','RMS_hz','mean_hz','centered_scatter_hz','search_boundary_points'])}

The full joint estimator reduces fixed-prediction RMS from about 105 to 27 Hz and centered scatter to about 12.5 Hz. The CFO-only fixed-epoch fit is less effective and reaches its search boundary at four points. The full refined measurements are independently renominated and validated with the same three distinct randomized 12-second block holdouts and 2-second guards. **60342 remains supported** in both c arms and every holdout. Observation IDs, timestamps, alias lifts and noise weights are unchanged. The refined target never enters receiver calibration; exact replay reconstructs the same measurement refinement from hashed worker outputs.

## Position result: improvement is not acceptance

{table(trials,['variant','arm','control_error_km','addition_error_km','RMS_hz','paired_valid','lag1','lag1_limit'])}

![Fixed-prediction and full-fit residuals](figures/residual_comparison.png)

The fitted-c addition improves from **0.937 to 0.538 km** after remeasurement; c=0 improves from **0.876 to 0.480 km**. Both remain worse than their matched no-target controls. Control objectives replay within 1e-5, confirming that only target measurements changed. Better radio measurements have exposed a remaining smooth model discrepancy: residual lag-one correlation is about **0.875 and 0.822**, above the unchanged limit **0.686**. The refined target fails both nominal and continuously refined exact-orbit checks. The earlier noisy raw-target pass must not be treated as sufficient evidence for promotion.

We keep the refined trial rejected. Adding arbitrary polynomial corrections, discarding inconvenient points or relaxing correlation thresholds would not explain this discrepancy. The next model test should measure shared receiver uncertainty using other satellites and compare it with family-specific orbital uncertainty, while retaining independent prediction checks.

## V06: independently supported identities are not enough to unite two curves

The next inventory batch independently nominates 69713 for V06 RX2 CH2 (83 points) and RX2 CH5 (85 points). A joint trial uses one phase/orbit correction, separate existing track biases and receiver uncertainty integrated once, with matched Powell controls and both c arms. It remains **{jexec[0]['status']}**; the common-residual audit also fails. This trial does not authorize combining the curves or counting 168 recovered points.

{table(joint,['arm','component','points','RMS_hz','lag1','lag1_limit','noise_pass','control_error_km','joint_error_km'])}

![V06 joint residuals](figures/v06_joint_residuals.png)

## Inventory progress and evidence

The [second predictive-role batch](../2026_10_30_predictive_role_reassessment_batch2/README.md) assesses 16 more large curves: six supported identities, three ambiguous, four unstable and three prediction mismatches. It runs all six supported position cases and retains every rejection. The individual V06 CH2 curve (83 points) passes RF checks but worsens location error; its separate status does not make the rejected joint fit acceptable. **953 older-role candidates remain**. The whole inventory goal is still open. The [updated ledger](annotation_ledger.csv) preserves the historical trials, marks 60342 withheld after the native-IQ review, and records the rejected V06 joint trial. No joint recovery or production acceptance is claimed.

[Per-point measurements](measurement_points.csv), [cross-frame evidence](cross_frame_validation.csv), [position results](position_trials.csv), [joint-family metrics](v06_joint.csv), source hashes and compressed scientific evidence accompany this report. Raw recordings and persisted GLRT contracts are unchanged. No future TLE, new RF acquisition or GPS-based model selection is used.
''')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','output','previous'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
