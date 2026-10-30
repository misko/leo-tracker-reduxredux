"""Publish graph/measurement diagnostics and the next complete annotation batch."""
import argparse,csv,gzip,hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays
from report_predictive_track_annotation import table
from leo.analysis.research.grouped_prediction import identity_consensus


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();s=args.study;hashes={};evidence={}
    def load(p):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p);evidence[str(p)]=compact_replays(compact_evidence(r));return r
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=150);plt.close(fig)
    diagnostic=load(s/'pulse-graph-partition-f4b54f0c-v1.json');result=load(s/'pulse-graph-measurements-f4b54f0c-v1.json')
    for p,digest in result['source_hashes'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest:raise ValueError('changed raw source: '+p)
        hashes[p]=digest
    for p,digest in diagnostic['source_hashes'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest:raise ValueError('changed diagnostic source: '+p)
        hashes[p]=digest
    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger};batch=[];queue=s/'systematic-annotation-v1';attempt=queue/'attempt-31'
    load(attempt/'protocol.json');executions=load(attempt/'execution.json')
    for j in load(attempt/'selected.json'):
        tid=j['track_id'];term=load(attempt/(tid+'-terminal.json'))
        if term['status']=='complete':
            path=queue/tid/'result.json';r=load(path);load(path.parent/'protocol.json');a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
            byid[tid].update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),annotation_source=str(path),
                partition_policy='distinct timestamps',geometry_only_early_exit=r.get('geometry_only_early_exit',False),distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        else:
            a=dict(status='execution_'+term['status'],norad=None);byid[tid].update(state=a['status'],annotation_execution_source=str(attempt/(tid+'-terminal.json')))
        batch.append(dict(scan=j['label'],track_id=tid,points=j['points'],status=a['status'],norad=a['norad']))
    byid['935edf55ee37a52ae810'].update(graph_provenance_source=str(s/'pulse-graph-measurements-f4b54f0c-v1.json'),
        graph_provenance_state='single degree-4 piece; interleaved with retained curve; template bias insufficient; unresolved')
    csvout('annotation_ledger.csv',ledger);csvout('annotation_batch.csv',batch);csvout('executions.csv',executions)
    csvout('measurement_metrics.csv',result['metrics']);folds=[{k:v for k,v in r.items() if k!='fits'} for r in result['polynomial_folds']];csvout('polynomial_folds.csv',folds)
    rows=diagnostic['observations'];t=np.array([r['time_s'] for r in rows]);y=np.array([r['measured_cfo_hz'] for r in rows]);labels=np.array([r['component'] for r in rows])
    fragments=[f for f in diagnostic['arms'][0]['fragments'] if f['shared_family'] or not f['calibration_points']]
    components=[f['component'] for f in fragments];colors=['#d55e00','#0072b2'];union=np.isin(labels,components);delta=np.array(result['correction_hz'])
    provenance=[]
    for f in fragments:
        track=f['original_graph'];use=labels==f['component']
        provenance.append(dict(component=f['component'],points=int(use.sum()),pieces=len(track['pieces']),degrees=[p['degree'] for p in track['pieces']],
            start_s=track['start_s'],end_s=track['end_s'],polynomial_RMS_hz=track['residual_rms_hz'],calibration_points=f['calibration_points'],
            rank0_points=sum(r['winner']['candidate_rank']==0 for r in rows if r['component']==f['component']),
            minimum_margin=min(r['winner']['fractional_margin'] for r in rows if r['component']==f['component'])))
    csvout('graph_provenance.csv',provenance)
    # Render three complete 20-second windows; observations from other curves
    # remain grey. The display uses original canonical CFO, never corrected data.
    fig,axs=plt.subplots(2,3,figsize=(16,8),layout='constrained')
    arm=diagnostic['arms'][0];prediction=np.array(arm['orbit_plus_receiver_CFO_hz']);res=np.array(arm['residual_without_fragment_constants_hz']);common=res[union].mean()
    # Fold prediction to the native alias at each observation.
    native_prediction=y-res+common
    for col,start in enumerate((140,160,180)):
        window=(t>=start)&(t<start+20)
        axs[0,col].scatter(t[window],y[window]/1000,c='#aaa',s=12,label='Other original winners')
        for component,color in zip(components,colors,strict=True):
            use=window&(labels==component);label=component.split('-')[3]
            axs[0,col].scatter(t[use],y[use]/1000,c=color,s=20,label=label)
            axs[1,col].scatter(t[use],res[use]-common,c=color,s=22,label=label)
        use=window&union;order=np.argsort(t[use]);axs[0,col].plot(t[use][order],native_prediction[use][order]/1000,'k--',lw=1,label='59467 + receiver + pulse + common constant')
        axs[0,col].set(xlim=(start,start+20),xlabel='Time (s)',ylabel='Original GLRT CFO (kHz)',title=f'{start}–{start+20} s')
        # A distant third curve is in the data but outside this zoom's CFO range.
        local=y[use]/1000;axs[0,col].set_ylim(local.min()-2,local.max()+2)
        axs[1,col].axhline(0,c='k',lw=.5);axs[1,col].axvspan(160,165,color='gold',alpha=.15)
        axs[1,col].set(xlim=(start,start+20),ylim=(-240,240),xlabel='Time (s)',ylabel='Residual, one common constant (Hz)')
        for ax in axs[:,col]:ax.grid(alpha=.2)
    axs[0,0].legend(fontsize=6);axs[1,0].legend(fontsize=8)
    fig.suptitle('RX1 CH5: T003 (41 points, excluded) and T004 (30 points, retained) interleave\nFrozen c=0 pulse-control prediction; neither a new satellite fit nor two disconnected pieces')
    save(fig,'ch5_20s_context.png')
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for col,arm in enumerate(diagnostic['arms']):
        raw=np.array(arm['residual_without_fragment_constants_hz'])
        for row,(component,color) in enumerate(zip(components,colors,strict=True)):
            use=labels==component;a=raw[use];b=(raw+delta)[use]
            axs[row,col].plot(t[use],a-a.mean(),'.-',c=color,label='Original')
            axs[row,col].plot(t[use],b-b.mean(),'.--',c='#222',label='Template-only correction')
            axs[row,col].axvline(182.5,c='#888',ls=':');axs[row,col].axhline(0,c='k',lw=.5)
            axs[row,col].set(title=f"{arm['arm']} / {component.split('-')[3]}",xlabel='Time (s)',ylabel='Centered residual (Hz)');axs[row,col].grid(alpha=.2);axs[row,col].legend(fontsize=8)
    fig.suptitle('Known interpolator response reduces scatter but leaves the late discrepancy\nNo coefficients fitted to these observations; original position, orbit and pulse stay fixed')
    save(fig,'template_correction_residuals.png')
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained');curve=result['response'];actual=np.array(curve['actual_offset_hz']);reported=np.array(curve['reported_offset_hz'])
    axs[0].plot(actual,reported-actual);axs[0].axhline(0,c='k',lw=.5);axs[0].set(xlabel='True offset from 500 Hz bin (Hz)',ylabel='Predicted estimator bias (Hz)',title='Published-template response: no observed-data fit')
    phase=(y+250)%500-250;raw=np.array(diagnostic['arms'][0]['residual_without_fragment_constants_hz'])
    for component,color in zip(components,colors,strict=True):
        use=labels==component;axs[1].scatter(phase[use],raw[use]-raw[union].mean(),c=color,s=22,label=component.split('-')[3])
    axs[1].plot(reported,reported-actual,'k--',label='Predicted bias');axs[1].set(xlabel='Measured offset from 500 Hz bin (Hz)',ylabel='c=0 residual, common constant (Hz)',title='The deterministic bias is too small to explain the shift');axs[1].legend(fontsize=8)
    for ax in axs:ax.grid(alpha=.2)
    save(fig,'cfo_bin_response.png')
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained');seeds=[r['seed'] for r in result['partition_schedule']['selected']];x=np.arange(len(seeds))
    for grouping,off,color in [('union',-.18,'#009e73'),('original_partition',.18,'#cc79a7')]:
        rr=[next(f for f in folds if f['seed']==seed and f['grouping']==grouping) for seed in seeds]
        axs[0].bar(x+off,[r['held_RMS_hz'] for r in rr],.34,color=color,label=grouping)
        axs[1].bar(x+off,[r['negative_twice_log_density'] for r in rr],.34,color=color,label=grouping)
    for ax in axs:ax.set(xticks=x,xticklabels=[str(v) for v in seeds],xlabel='Random scanwide block seed');ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    axs[0].set_ylabel('Held polynomial prediction RMS (Hz)');axs[1].set_ylabel('Held −2 log density (lower better)')
    fig.suptitle('Merging graph fragments does not consistently improve prediction\nOrders 1–4 chosen from training only; 12 s random blocks / 2 s guards; frozen graph conditioned')
    save(fig,'partition_prediction.png')
    summary=dict(annotations_completed=sum(bool(r['annotation_source']) for r in ledger),inventory_total=len(ledger),
        annotation_batch=dict(Counter(r['status'] for r in batch)),historical_phase_audits=sum(bool(r.get('phase_audit_source')) for r in ledger),
        native_points_replayed=len(result['native_measurements']),native_acquired_equals_fractional=result['native_acquired_equals_fractional'],
        maximum_template_correction_hz=float(abs(delta).max()),production_changed=False,new_position_fits=0,new_accepted_points=0)
    write(out/'summary.json',summary)
    for name in ('diagnose_pulse_graph_partition.py','analyze_pulse_graph_measurements.py','report_pulse_graph_measurements.py','probe_native_fft_bias.py'):
        path=Path(__file__).parent/name;hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    display=[dict(arm=m['arm'],track=m['component'].split('-')[3] if m['component']!='union' else 'union',method=m['method'],RMS_hz=round(m['centered_RMS_hz'],2),late_shift_hz=round(m['late_minus_early_hz'],2)) for m in result['metrics'] if m['component']!='union']
    text=f'''# CH5 graph partition and native CFO investigation

The [preceding position experiment](../{args.previous.name}/README.md) recovered a 42-point CH2 curve after modeling a shared 160–165 s excursion, but adding the overlapping 41-point CH5 curve worsened the position. This iteration traces that CH5 curve to original GLRT candidates and tests two proposed explanations. **It is not a multi-piece join, and a known CFO interpolation bias is too small to explain its remaining discrepancy.** A common polynomial does not consistently predict the two overlapping graph fragments better. The full CH5 curve remains an unresolved, supported satellite-identity candidate; no measurements are discarded and no production recovery is promoted.

## What was traced

The recording is `fast8-auto-20261026-021217-3c1e1fc4-1-upper` (AUTO-f4b54f0c). T003 has 41 points over 141.58–197.59 s, and retained T004 has 30 over 143.71–194.05 s. Each is **one fourth-order polynomial**. Their measurements interleave on RX1 CH5 at the same RF. The nominal satellite is 59467. This excludes a join between separate stored polynomial pieces; it does not prove that every point came from one physical emitter or that the graph partition is unbiased.

{table(provenance,['component','points','pieces','degrees','polynomial_RMS_hz','calibration_points','rank0_points','minimum_margin'])}

All **90 original winning observations** in the lane and target extent ±5 s were replayed against eligible fractional-margin candidates and then against the original archived native GLRT products. Ranking uses maximum fractional margin, with the original rank tie break. No nearest-orbit peak selection was used. All 90 archived fractional CFO values equal their acquired CFO; the recorded fractional residual correction is zero. The analysis release is `{result['analysis_release_id']}`. This establishes archived measurement semantics, **not the exact capture/execution binary identity**. Native products, manifest and original observation authorities are hashed in [sources.json](sources.json).

![Three 20-second GLRT zooms](figures/ch5_20s_context.png)

The dashed prediction uses the previously fitted c=0 receiver/orbit/pulse model and one descriptive common constant for the union. The lower panels preserve the relative offset between fragments. A distant third curve is present in the extracted lane but outside the zoom's CFO range. T003's previously reported satellite identity was supported in three distinct random block partitions and both c arms; that conditional identity evidence is not proof of useful location information.

## Fixed template correction: a limited measurement effect

The native fine-acquisition source samples a 500 Hz frequency grid and interpolates three magnitudes with a parabola. Its true pilot-template response is not parabolic. Reuse the existing deterministic response model from the [earlier clock/measurement study](../2026_10_19_ds23_clock_measurement_controls/README.md): compute the Fourier magnitude of template energy on the alternating pilot symbols, then invert its monotone interpolation response. This predicts the correction without fitting any coefficient to this scan, GPS, satellite identity or residual curve. Apply it to **canonical GLRT CFO before alias lifting**, excluding near-DC and search-boundary cases.

The largest correction here is only **{summary['maximum_template_correction_hz']:.2f} Hz**. At frozen position/calibration it reduces scatter on both fragments, but T003's late mean shift hardly changes. Each table row profiles only a constant; slopes and steps are not removed. The 182.5 s split is the previously identified descriptive discrepancy, not a validation partition or optimized correction boundary.

{table(display,['arm','track','method','RMS_hz','late_shift_hz'])}

![Template bias and observed CFO-bin phase](figures/cfo_bin_response.png)
![Original and template-corrected residuals](figures/template_correction_residuals.png)

This is an exploratory fixed-endpoint measurement diagnostic. The exact executing binary, noise, multipath and peak-switch behavior remain unqualified for this correction. No position optimization used corrected CFO, and the reduction in frequency scatter is **not a claimed position improvement**. The correction cannot account for the roughly 126–130 Hz late T003 discrepancy. Another uncorroborated receiver step or a target-only fitted correction would risk absorbing model error without resolving its source.

## Does one graph curve predict better?

Fit orders 1–4 to the original alias-lifted measurements, selecting order by training BIC with a 40 Hz noise floor. Compare one polynomial for the 71-point union against separate polynomials for the original fragments. Prediction integrates linear-coefficient uncertainty. Use three distinct **random scanwide 12 s block assignments with 2 s training guards**. Geometry alone selects usable seeds; both fragments share the same held blocks. Coefficients, noise and order use training values only. Graph membership and alias lifts were determined earlier using the full dataset, so this is a conditional diagnostic, not blind graph-construction validation. These are polynomial predictions, not orbital fits, and have no learned c coefficient.

{table(folds,['seed','grouping','held_points','held_RMS_hz','negative_twice_log_density','orders'])}

![Conditional partition prediction](figures/partition_prediction.png)

The union has lower held RMS in two partitions, but lower predictive loss in only one. Both models have large errors in some withheld blocks, including extrapolation-sensitive blocks. Thus neither the existing split nor a forced merge is established as the correct physical model. Separate fits can score better despite worse RMS because they express larger uncertainty; this is why both quantities are shown. A fourth-order in-sample fit and residual gates alone do not establish predictive adequacy.

## Position status and next discriminating experiment

No new position fits were run in this iteration. The matched prior experiment remains: original error **0.499 / 0.572 km** (c=0 / fitted-c); pulse + CH2 **0.451 / 0.518 km**; pulse + CH2 + CH5 **0.524 / 0.588 km**. Proposed association with the pulse was **3,181 / 4,031 = 78.91%**; this is a research proposal, not production acceptance. The extra CH5 likelihood caused regression despite residual-gate passage. GPS was used only for those previously reported errors; this iteration does not read GPS or future TLEs.

The next discriminating test is a bounded existing-IQ replay of **both full interleaved fragments**, including early and late points. Independently refine CFO and code timing against known pilots and compare independent frame subsets. No satellite or GPS should enter that measurement fit. If the discrepancy persists across independently supported pilot estimates, investigate physical frequency/beam effects with corroborating curves. If it disappears, propagate the qualified measurement correction and its uncertainty through matched c arms. Do not select a target-only correction, truncate the tail, or merge fragments because GPS error improves. Other inventory cases can advance while this case awaits measurement-level evidence.

## Inventory and reproducibility

Attempt 31 completed: `{summary['annotation_batch']}`. The cumulative ledger now contains **{summary['annotations_completed']} / {summary['inventory_total']} completed assessments**, plus {summary['historical_phase_audits']} historical separate phase audits. These counts include rejected, ambiguous, unstable and insufficient-partition assessments; they are not accepted point coverage. One job reached the 600 s cap; its terminal receipt and claim are preserved. All 32 jobs have terminal receipts.

Reproduce with `diagnose_pulse_graph_partition.py`, then `analyze_pulse_graph_measurements.py`, then `report_pulse_graph_measurements.py`, using `PYTHONPATH=src:tools`, one BLAS thread, and the recorded source paths. [Raw compact evidence](evidence.json.gz), [measurement metrics](measurement_metrics.csv), [polynomial folds](polynomial_folds.csv), [graph provenance](graph_provenance.csv), [batch](annotation_batch.csv), [ledger](annotation_ledger.csv), and [executions](executions.csv) preserve all outcomes. Three component-owned tests cover exact candidate replay, canonical correction boundaries/bin translation and preserving slopes/steps when centering. Production policy, persisted measurement contracts and golden fixtures are unchanged.
'''
    (out/'README.md').write_text(text);print(summary,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
