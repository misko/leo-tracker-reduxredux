"""Report independent pilot-frame diagnostics without changing position inputs."""
import argparse,csv,gzip,hashlib,json,shutil
from pathlib import Path
from collections import Counter
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from analyze_pulse_graph_measurements import centered_metrics
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays
from report_predictive_track_annotation import table
from leo.analysis.research.grouped_prediction import identity_consensus


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();evidence={};hashes={}
    def load(p):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p);evidence[str(p)]=compact_replays(compact_evidence(r));return r
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    roots={'narrow':s/'pulse-iq-refinement-f4b54f0c-v1','wide':s/'pulse-iq-refinement-wide-f4b54f0c-v1'}
    d=load(s/'pulse-graph-partition-f4b54f0c-v1.json');lookup={o['observation_id']:i for i,o in enumerate(d['observations'])};runs={};executions=[];worker_receipts=[]
    for label,root in roots.items():
        plan=load(root/'plan.json');runs[label]=load(root/'result.json');terminal=load(root/'execution.json')
        assert len(terminal)==4 and all(r['status']=='complete' for r in terminal)
        executions.extend(dict(stage=label,**r) for r in terminal)
        assert len(runs[label]['rows'])==71 and {r['point']['observation_id'] for r in runs[label]['rows']}=={r['observation_id'] for r in plan['points']}
        for p,digest in runs[label]['worker_hashes'].items():
            w=load(Path(p));assert hashes[p]==digest;assert w['plan_sha256']==hashes[str(root/'plan.json')];worker_receipts.append(w)
            for source,sdigest in w['source_hashes'].items():
                path=root/'source_snapshot'/Path(source).name if label=='narrow' else Path(source)
                assert hashlib.sha256(path.read_bytes()).hexdigest()==sdigest;hashes[str(path)]=sdigest
    panel=load(roots['narrow']/'panel/manifest.json')
    assert panel['plan_sha256']==hashes[str(roots['narrow']/'plan.json')]
    assert all(w['panel_manifest_sha256']==hashes[str(roots['narrow']/'panel/manifest.json')] for w in worker_receipts)
    for point in panel['points']:
        path=roots['narrow']/'panel'/point['array'];assert hashlib.sha256(path.read_bytes()).hexdigest()==point['array_sha256']
    for key in ('reader','multirate_contract'):
        path=Path(panel[key+'_source']);assert hashlib.sha256(path.read_bytes()).hexdigest()==panel[key+'_source_sha256'];hashes[str(path)]=panel[key+'_source_sha256']
    components=sorted({r['point']['component'] for r in runs['wide']['rows']});metrics=[];points=[];repeatability=[];bounds=[]
    for label,run in runs.items():
        for component in components:
            rows=[r for r in run['rows'] if r['point']['component']==component];tt=np.array([r['point']['time_s'] for r in rows]);ix=[lookup[r['point']['observation_id']] for r in rows]
            track=next(f['original_graph'] for f in d['arms'][0]['fragments'] if f['component']==component);piece=track['pieces'][0]
            derivative=np.polynomial.legendre.legval((tt-piece['reference_time_s'])/piece['time_scale_s'],np.polynomial.legendre.legder(piece['coefficients_hz']))/piece['time_scale_s']
            for arm in d['arms']:
                raw=np.array(arm['residual_without_fragment_constants_hz'])[ix]
                for method in ('original','fixed_epoch','joint_all','joint_odd','joint_even','joint_all_time_adjusted'):
                    selected='joint_all' if method=='joint_all_time_adjusted' else method
                    delta=np.zeros(len(rows)) if method=='original' else np.array([r['methods'][selected]['CFO_hz']-r['point']['CFO_hz'] for r in rows])
                    dt=np.array([r['methods']['joint_all']['effective_time_from_probe_start_s']-.01 for r in rows])
                    if method=='joint_all_time_adjusted':delta-=derivative*dt
                    residual=raw+delta
                    metrics.append(dict(run=label,arm=arm['arm'],component=component,method=method,points=len(rows),**centered_metrics(tt,residual)))
                    if label=='wide':
                        for k,r in enumerate(rows):points.append(dict(arm=arm['arm'],component=component,method=method,observation_id=r['point']['observation_id'],time_s=tt[k],residual_hz=residual[k],
                            effective_time_shift_ms=dt[k]*1000,first_order_time_effect_hz=derivative[k]*dt[k]))
            odd=np.array([r['methods']['joint_odd']['CFO_hz'] for r in rows]);even=np.array([r['methods']['joint_even']['CFO_hz'] for r in rows]);difference=odd-even
            repeatability.append(dict(run=label,component=component,points=len(rows),odd_even_median_abs_hz=float(np.median(abs(difference))),odd_even_RMS_hz=float(np.sqrt(np.mean(difference*difference))),
                odd_complement_improved=sum(r['methods']['joint_odd']['complement_score']>r['methods']['joint_odd']['complement_score_at_original'] for r in rows),
                even_complement_improved=sum(r['methods']['joint_even']['complement_score']>r['methods']['joint_even']['complement_score_at_original'] for r in rows)))
        for method in ('joint_all','joint_odd','joint_even'):
            values=[r['methods'][method] for r in run['rows']]
            bounds.append(dict(run=label,method=method,points=len(values),frequency_boundary=sum(r['frequency_search_boundary'] for r in values),
                epoch_boundary=sum(r['epoch_search_boundary'] for r in values),rate_boundary=sum(r['code_rate_search_boundary'] for r in values),
                epoch_min_samples=min(r['offset_samples'] for r in values),epoch_max_samples=max(r['offset_samples'] for r in values),
                code_rate_min_ppm=min(r['modulation_ppm'] for r in values),code_rate_max_ppm=max(r['modulation_ppm'] for r in values)))
    csvout('measurement_metrics.csv',metrics);csvout('point_residuals.csv',points);csvout('frame_repeatability.csv',repeatability);csvout('fit_bounds.csv',bounds)
    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest();ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger}
    queue=s/'systematic-annotation-v1';attempt=queue/'attempt-32';load(attempt/'protocol.json');load(attempt/'execution.json');batch=[]
    for j in load(attempt/'selected.json'):
        tid=j['track_id'];term=load(attempt/(tid+'-terminal.json'));executions.append(dict(stage='annotation32',**term))
        if term['status']=='complete':
            path=queue/tid/'result.json';r=load(path);load(path.parent/'protocol.json');a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
            byid[tid].update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),annotation_source=str(path),
                partition_policy='distinct timestamps',geometry_only_early_exit=r.get('geometry_only_early_exit',False),distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        else:
            a=dict(status='execution_'+term['status'],norad=None);byid[tid].update(state=a['status'],annotation_execution_source=str(attempt/(tid+'-terminal.json')))
        batch.append(dict(scan=j['label'],track_id=tid,points=j['points'],status=a['status'],norad=a['norad']))
    byid['935edf55ee37a52ae810'].update(raw_pilot_source=str(roots['wide']/'result.json'),raw_pilot_state='late discrepancy persists across disjoint pilot-frame fits; no position inclusion promotion')
    csvout('annotation_ledger.csv',ledger);csvout('annotation_batch.csv',batch);csvout('executions.csv',executions)
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for row,component in enumerate(components):
        for col,arm in enumerate(('c0','fitted_c')):
            for method,color,style in [('original','#999','.-'),('joint_all','#0072b2','.-'),('joint_odd','#d55e00','.'),('joint_even','#009e73','.')]:
                rr=[r for r in points if (r['component'],r['arm'],r['method'])==(component,arm,method)];tt=np.array([r['time_s'] for r in rr]);y=np.array([r['residual_hz'] for r in rr])
                axs[row,col].plot(tt,y-y.mean(),style,c=color,label=method,alpha=.85)
            axs[row,col].axhline(0,c='k',lw=.5);axs[row,col].axvline(182.5,c='#999',ls=':');axs[row,col].set(title=component.split('-')[3]+' / '+arm,xlabel='Time (s)',ylabel='Centered residual to frozen model (Hz)');axs[row,col].grid(alpha=.2);axs[row,col].legend(fontsize=8)
    fig.suptitle('CH5 discrepancy persists after independent pilot CFO/code refinement\nOriginal position, orbit and pulse remain fixed; odd and even frames are fitted separately')
    save(fig,'pilot_residuals.png')
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for component,color in zip(components,['#d55e00','#0072b2'],strict=True):
        rr=[r for r in runs['wide']['rows'] if r['point']['component']==component];tt=np.array([r['point']['time_s'] for r in rr]);name=component.split('-')[3]
        axs[0,0].plot(tt,[r['methods']['joint_all']['CFO_hz']-r['point']['CFO_hz'] for r in rr],'.-',c=color,label=name)
        axs[0,1].plot(tt,[r['methods']['joint_odd']['CFO_hz']-r['methods']['joint_even']['CFO_hz'] for r in rr],'.-',c=color,label=name)
        axs[1,0].plot(tt,[r['methods']['joint_all']['offset_samples'] for r in rr],'.-',c=color,label=name)
        axs[1,1].plot(tt,[r['methods']['joint_all']['modulation_ppm'] for r in rr],'.-',c=color,label=name)
    for ax in axs.flat:ax.grid(alpha=.2);ax.legend(fontsize=8);ax.set_xlabel('Time (s)')
    axs[0,0].set_ylabel('Refined − archived CFO (Hz)');axs[0,1].set_ylabel('Odd − even independently fitted CFO (Hz)')
    axs[1,0].set_ylabel('Timing offset from archived epoch (samples)');axs[1,1].set_ylabel('Local modulation-rate fit (ppm)')
    axs[1,0].axhline(-.75,c='#999',ls='--',label='Old bound')
    fig.suptitle('Both full fragments: bounded ±3-sample timing run\nThese code-rate/timing fits are local waveform parameters, not receiver drift calibration')
    save(fig,'local_measurement_parameters.png')
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    narrow={r['point']['observation_id']:r for r in runs['narrow']['rows']};sensitivity=[]
    for method,color in [('joint_odd','#d55e00'),('joint_even','#009e73')]:
        rows=runs['wide']['rows'];old=np.array([r['methods'][method]['complement_score_at_original'] for r in rows]);new=np.array([r['methods'][method]['complement_score'] for r in rows]);delta=np.array([r['methods'][method]['CFO_hz']-narrow[r['point']['observation_id']]['methods'][method]['CFO_hz'] for r in rows])
        axs[0].scatter(old,new,c=color,s=16,label=method,alpha=.7);axs[1].hist(delta,bins=15,alpha=.5,color=color,label=method)
        sensitivity.append(dict(method=method,complement_improves_over_original=int((new>old).sum()),points=len(rows),wide_minus_narrow_CFO_RMS_hz=float(np.sqrt(np.mean(delta*delta))),maximum_abs_wide_minus_narrow_hz=float(abs(delta).max())))
    lim=axs[0].get_xlim();axs[0].plot(lim,lim,'k--');axs[0].set(xlabel='Complement score at archived parameters',ylabel='Complement score after subset fit')
    axs[1].set(xlabel='Wider − narrow timing-range CFO (Hz)',ylabel='Points')
    for ax in axs:ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle('Cross-frame signal support and timing-bound sensitivity\nScores are local pilot likelihood fractions, not calibrated association probabilities')
    save(fig,'cross_frame_validation.png');csvout('timing_range_sensitivity.csv',sensitivity)
    summary=dict(annotations_completed=sum(bool(r['annotation_source']) for r in ledger),inventory_total=len(ledger),annotation_batch=dict(Counter(r['status'] for r in batch)),
        historical_phase_audits=sum(bool(r.get('phase_audit_source')) for r in ledger),points_refined=71,raw_windows_verified=panel['raw_windows_read'],
        wide_boundary_count=sum(r['frequency_boundary']+r['epoch_boundary']+r['rate_boundary'] for r in bounds if r['run']=='wide'),
        maximum_first_order_time_effect_hz=max(abs(r['first_order_time_effect_hz']) for r in points),
        production_changed=False,new_position_fits=0,new_accepted_points=0)
    write(out/'summary.json',summary)
    (out/'source_snapshot').mkdir();shutil.copytree(roots['narrow']/'source_snapshot',out/'source_snapshot/narrow')
    for name in ('report_pulse_iq_refinement.py','refine_pulse_iq_panel.py','export_pulse_iq_panel.py','fast_local_pilot_refinement.py','local_pilot_refinement.py'):
        path=Path(__file__).with_name(name);hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (Path(__file__).with_name('probe_native_code_carrier.py'),Path(__file__).parents[1]/'src/leo/analysis/starlink/templates.py'):
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    display=[dict(arm=r['arm'],track=r['component'].split('-')[3],method=r['method'],RMS_hz=round(r['centered_RMS_hz'],2),late_shift_hz=round(r['late_minus_early_hz'],2)) for r in metrics if r['run']=='wide' and r['method'] in ('original','joint_all','joint_odd','joint_even')]
    text=f'''# CH5 raw-IQ pilot refinement: repeatable discrepancy remains

This follows the [graph/native provenance investigation](../{args.previous.name}/README.md) on AUTO-f4b54f0c, recording `fast8-auto-20261026-021217-3c1e1fc4-1-upper`. All **71 original observations** from the 41-point RX1 CH5 T003 and retained 30-point T004 were remeasured from existing IQ. Independent pilot fits reduce residual scatter but preserve T003's late discrepancy: approximately **−126 Hz** in both disjoint frame subsets. This is evidence against a simple interpolator error or random measurement noise being the main cause. It does **not** establish which remaining satellite, transmitter, receiver, propagation or recording-time effect is responsible. No position fit or production inclusion changed.

## Measurement authority and bounded replay

The original native products identify each IQ window by digest, receiver, hardware sample counter and archived peak. The deployed immutable multirate reader verified **{panel['raw_windows_read']} windows across three selected recording segments**, including complete chunk hashes. It exported the 71 requested receiver windows. Each local array was hashed again before fitting. The older research checkout's reader supports only the older 2.5 MS/s contract; it was not changed to reinterpret these 10 MS/s recordings. The deployed reader and V2 contract source hashes are retained. Raw recordings are read-only; no new RF was collected.

The measurement-only plan contains canonical CFO, epoch, receiver/visit and raw-IQ authorities. It contains no GPS, orbit, TLE, satellite identity, pulse amplitude or residual target. Selection is both complete original fragments; no late points are removed. Four worker processes, each capped at 900 s, complete both runs. The [execution table](executions.csv) records every terminal status. The IQ arrays remain local replay prerequisites, not published payloads.

## What the pilot model fits

Use the existing known-pilot variable-projection model with a separate complex gain and DC term per frame. It fits CFO, fractional epoch adjustment and modulation-rate adjustment. The initial peak and epoch come from the archived GLRT; this is a local peak refinement, **not an independent blind acquisition**. The frequency scout is ±600 Hz in 100 Hz steps; local CFO bounds are ±800 Hz and code-rate bounds ±40 ppm, with one selected start and 16 optimization iterations. These engineering search bounds are not calibrated physical priors.

Run all-frame, odd-frame and even-frame fits. The odd/even scouts, gradients, coefficients and code adjustments each use only their named subset. Evaluate each subset's fitted parameters on its complementary frames without refitting. The subsets share the full-window archived nomination, waveform model and recording, so they are not fully independent measurements or a scanwide association-validation split. The ongoing annotation workflow continues to use random scanwide 12 s blocks with 2 s guards.

The initial ±0.75-sample epoch range often reached its negative bound. Preserve that complete run, then change **only** the epoch bound to ±3 samples (±300 ns at 10 MS/s), keeping the same observations and search iteration budget. All **213** joint fits in the wider run (71 × three frame subsets) finish inside all three bounds. The full-frame epoch adjustments range from about −1.66 to −0.05 samples. Removing the bound changes the CFO little: odd/even wide-versus-narrow RMS differences are below 1.2 Hz. Thus the initial timing-bound issue was real, but does not explain the large frequency discrepancy.

![Refinement and frame agreement](figures/local_measurement_parameters.png)

The local waveform score improves on complementary frames in **69/71 odd-trained** and **62/71 even-trained** cases relative to archived parameters. All decreases are retained in the evidence. Positive score differences do not prove absolute CFO accuracy. Code-rate estimates here are local waveform fits, not new receiver drift estimates.

![Cross-frame scores and timing-bound sensitivity](figures/cross_frame_validation.png)

## Residual evidence, with c arms kept separate

Keep the original pulse-control position, receiver calibration and causal orbit model frozen. That control excludes T003 and includes the retained T004 in calibration. Add the measurement change to the original residual, then profile one constant per displayed fragment. No slope or step is removed. Both c=0 and fitted-c use exactly the same refined observations; there is no new c fit or location search in this diagnostic. The 182.5 s split is the previously identified descriptive discrepancy, not a validation holdout.

{table(display,['arm','track','method','RMS_hz','late_shift_hz'])}

![Original and refined residuals in both c arms](figures/pilot_residuals.png)

For c=0, T003 RMS falls from ~85 to ~79 Hz, but the late shift remains ~126 Hz. T004 RMS falls from ~56 to ~46 Hz. Odd/even estimates have median absolute differences of **13.2 Hz for T003** and **13.4 Hz for T004**, considerably smaller than the persistent T003 shift. Shared nomination/model errors could still affect both; this is evidence of repeatability within this local pilot model, not proof that every selected point or satellite label is correct.

The frequency factor uses the 20 ms probe midpoint. The model-derived effective times of the all-frame estimates are around 9–12 ms after probe start. A first-order diagnostic using each original graph polynomial's local derivative changes predicted CFO by at most **{summary['maximum_first_order_time_effect_hz']:.2f} Hz**. Its complete residual metrics are included as `joint_all_time_adjusted`; it cannot explain a ~126 Hz shift. This is a local centroid-sensitivity calculation, not validation of the recording's absolute hardware/UTC timing or a production timestamp correction.

## Interpretation and next action

Three explanations have now been tested: multi-piece joining (not how T003 was constructed), deterministic CFO interpolation bias (small contribution), and local carrier/code/timing refinement (scatter improves, late discrepancy persists). This makes relaxing residual gates or applying a target-only correction unjustified. The record still supports 59467 conditionally, while useful position information remains unproven. Another satellite or peak outside this local search is not excluded by this measurement experiment.

The next model-level test should compare the **combined 71-point evidence** with independent same-satellite and other-family receiver/band witnesses. Ask whether a frequency correction learned from other curves predicts this curve under scanwide grouped validation. If the discrepancy follows only one carrier/beam, represent that uncertainty without allowing it to freely pull position; if it follows receiver/time across unrelated satellites, test a shared instrument correction. Require matched c arms and separate frequency-score versus position-error reporting. Preserve the entire curve and do not choose bounds, weight or truncation using GPS. Continue through other inventory cases instead of treating this one unresolved discrepancy as a reason to stop the systematic work.

No new position-error gain is claimed. The prior controlled results remain original **0.499 / 0.572 km**, pulse + CH2 **0.451 / 0.518 km**, and pulse + CH2 + CH5 **0.524 / 0.588 km** (c=0 / fitted-c). The last result is why a supported identity and passing residual gates alone are insufficient for promotion.

## Systematic progress and reproduction

Attempt 32 states: `{summary['annotation_batch']}`. The cumulative ledger now records **{summary['annotations_completed']} / {summary['inventory_total']} completed assessments**, with {summary['historical_phase_audits']} historical separate phase audits. Assessments include negative, ambiguous and insufficient-partition outcomes; they are not accepted-GLRT coverage. Timeouts retain their claims and terminal receipts. No production acceptance count increases in this report.

Run `refine_pulse_iq_panel.py prepare`, then `export_pulse_iq_panel.py` with the recorded immutable deployed reader on PYTHONPATH. Run the research fitter with `PYTHONPATH=src:tools`, BLAS/OMP threads 1. The wider run reuses the exact hashed panel and verifies every point's measurement authority. `report_pulse_iq_refinement.py` builds this report. [Sources](sources.json), [compact evidence](evidence.json.gz), [metrics](measurement_metrics.csv), [point residuals](point_residuals.csv), [bounds](fit_bounds.csv), [frame repeatability](frame_repeatability.csv), [ledger](annotation_ledger.csv) and [batch](annotation_batch.csv) preserve all outcomes. The narrow-run source snapshot preserves its exact implementation before the bound parameter was added.

**Eight component-owned tests pass:** synthetic recovery on both sample rates, independently fitted frame carriers/code/rate, immunity to changing omitted frames, unchanged default all-frame behavior, subset analytic gradients versus finite differences/reference scores, recovery beyond the old timing bound, and rejecting reused panels with altered measurement authority. Synthetic tests do not qualify every real multipath or transmitter waveform. Public contracts, original measurements, golden fixtures and production policy are unchanged.
'''
    (out/'README.md').write_text(text);print(summary,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
