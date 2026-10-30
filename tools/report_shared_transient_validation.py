"""Report grouped shared-family validation, witness failures and transient clue."""
import argparse,csv,gzip,hashlib,json
from pathlib import Path
from collections import Counter
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays
from report_predictive_track_annotation import table
from report_inventory_experiments import error
from leo.analysis.research.grouped_prediction import identity_consensus
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from shared_pulse_witness import fit_pulse,pulse_prediction


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir()
    sources={};evidence={};executions=[]
    def load(p):
        sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p)
        evidence[str(p)]=compact_replays(compact_evidence(r));return r
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    def rms(y):return float(np.sqrt(np.mean(np.square(y))))
    previous=args.previous/'annotation_ledger.csv';sources[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger};batch=[]
    root=s/'systematic-annotation-v1';attempt=root/'attempt-29';load(attempt/'protocol.json')
    for j in load(attempt/'selected.json'):
        tid=j['track_id'];term=load(attempt/(tid+'-terminal.json'));executions.append(dict(stage='annotation29',**term))
        if term['status']=='complete':
            path=root/tid/'result.json';r=load(path);load(path.parent/'protocol.json')
            a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
            byid[tid].update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),annotation_source=str(path),
                partition_policy='distinct timestamps',geometry_only_early_exit=r.get('geometry_only_early_exit',False),distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        else:
            a=dict(status='execution_'+term['status'],norad=None)
            byid[tid].update(state=a['status'],annotation_execution_source=str(attempt/(tid+'-terminal.json')))
        batch.append(dict(scan=j['label'],track_id=tid,status=a['status'],norad=a['norad']))
    csvout('annotation_batch.csv',batch);csvout('annotation_ledger.csv',ledger)
    blocks=[];pool={};blockroot=s/'shared-family-blocks-e565210d-v1';protocol=load(blockroot/'protocol.json')
    for seed in protocol['seeds']:
        term=load(blockroot/(str(seed)+'-terminal.json'));assert term['status']=='complete';executions.append(dict(stage='shared blocks',**term))
        load(blockroot/str(seed)/'protocol.json');r=load(blockroot/str(seed)/'result.json')
        for v in r['rows']:
            target=next(q for q in v['predictions'] if q['kind']=='target')
            old=[x for q in v['predictions'] if q['kind']!='target' for x in q['held_residual_hz']]
            blocks.append(dict(seed=seed,mode=v['mode'],role=v['role'],arm=v['arm'],target_held_points=len(target['held_residual_hz']),
                target_RMS_hz=target['held_RMS_hz'],incumbent_held_points=len(old),incumbent_RMS_hz=rms(old),
                error_km=error(v),phase_gap_s=v['final_phase_change_s'],domains_valid=v['domains_valid'],receiver_delta=v['receiver_delta_at_update']))
            assert v['domains_valid'] and v['final_phase_change_s']<=.01 and v['receiver_delta_at_update']<=1e-10
            pool.setdefault((v['mode'],v['role'],v['arm']),[]).extend(target['held_residual_hz'])
    pooled=[dict(mode=m,role=r,arm=a,target_RMS_hz=rms(y),fold_observations=len(y)) for (m,r,a),y in pool.items()]
    csvout('shared_block_trials.csv',blocks);csvout('shared_block_pooled.csv',pooled)
    fig,axs=plt.subplots(2,2,figsize=(12,9),layout='constrained')
    for col,arm in enumerate(('c0','fitted_c')):
        for mode,color in [('default','#777777'),('conditional','#0072b2')]:
            for role,style in [('control','--'),('addition','-')]:
                rr=[next(r for r in blocks if r['seed']==seed and r['arm']==arm and r['mode']==mode and r['role']==role) for seed in protocol['seeds']]
                axs[0,col].plot(range(3),[r['target_RMS_hz'] for r in rr],style+'o',color=color,label=mode+' '+role)
                axs[1,col].plot(range(3),[r['error_km'] for r in rr],style+'o',color=color,label=mode+' '+role)
        axs[0,col].set(title=arm,ylabel='Held target RMS (Hz)');axs[1,col].set(ylabel='Evaluation position error (km)')
        for ax in axs[:,col]:ax.set_xticks(range(3),protocol['seeds']);ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('63381: same random scanwide blocks, refit position/calibration\nFixed graph and identities; 12 s blocks + 2 s guards; held target constant trained only.')
    save(fig,'shared_blocks.png')
    cases=[('AUTO-2ae9ee49','c8fe032c7e42b4695bb5'),('AUTO-f4b54f0c','d07341fb93af4b6eca09')]
    held=[];wpool={};diagnostics={}
    for label,tid in cases:
        diagnostic=load(s/f'shared-control-witness-{tid}-v1.json');diagnostics[tid]=diagnostic
        assert diagnostic['target_excluded_from_position']
        root=s/f'receiver-residual-validation-{tid}-v1';pr=load(root/'protocol.json')
        for seed in pr['seeds']:
            term=load(root/(str(seed)+'-terminal.json'));assert term['status']=='complete';executions.append(dict(stage='witness blocks',scan=label,**term))
            load(root/str(seed)/'protocol.json');r=load(root/str(seed)/'result.json')
            for a in r['results']:
                assert a['training']['final_phase_change_s']<=.01
                for v in a['rows']:
                    held.append(dict(scan=label,seed=seed,arm=a['arm'],**{k:x for k,x in v.items() if k not in ('held_residual_hz','held_prediction_hz','held_distinct_families','witness_families')}))
                    if v['width_s']==6 and v['scaling']=='hz':
                        b,c=wpool.setdefault((label,a['arm'],v['relation']),([],[]));b.extend(a['baseline_held_residual_hz']);c.extend(v['held_residual_hz'])
        fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
        source=load(s/'graph-predictive-transfer25-v1'/tid/'inclusion'/'target_0.json')
        for col,a in enumerate(diagnostic['results']):
            target=a['target'];t=np.array(target['times_s']);y=np.array(target['residual_hz'])
            original=source['arms'][a['arm']]['target_diagnostics'][0];cfo=np.array(original['CFO_hz'])
            axs[0,col].plot(t,cfo,'.',label='All target GLRT points',color='black')
            axs[0,col].plot(t,cfo-y,label='Exact causal model + target constant',color='#0072b2')
            axs[1,col].plot(t,y,'k.-',lw=2,label='Target')
            for w in a['all_active_curves']:
                u=np.array(w['times_s']);mask=(u>=t.min()-3)&(u<=t.max()+3)
                if w['component']==target['component'] or mask.sum()<8:continue
                same=w['norad']==target['norad']
                axs[1,col].plot(u[mask],np.array(w['residual_hz'])[mask],'.',ms=3,alpha=.65 if same else .35,
                    label=f"{w['norad']} RX{w['receiver']} CH{w['channel']} {w['component'].split('-')[3]}",lw=1 if same else .7)
            axs[0,col].set(title=a['arm'],ylabel='GLRT CFO (Hz)');axs[1,col].set(xlabel='Time (s)',ylabel='Exact-model residual (Hz)')
            for ax in axs[:,col]:ax.grid(alpha=.2);ax.legend(fontsize=6)
            axs[1,col].axhline(0,color='gray',lw=.5)
        fig.suptitle(label+': target excluded from position and receiver calibration\nFull-fit diagnostic; target constant profiled for display. Other curves shown when ≥8 points in window.')
        save(fig,tid+'.png')
    wpooled=[dict(scan=l,arm=a,relation=r,baseline_RMS_hz=rms(b),corrected_RMS_hz=rms(c),fold_observations=len(b)) for (l,a,r),(b,c) in wpool.items()]
    csvout('all_witness_held_predictions.csv',held);csvout('witness_pooled.csv',wpooled)
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,(label,tid) in zip(axs,cases,strict=True):
        rr=[r for r in wpooled if r['scan']==label and r['arm']=='fitted_c']
        ax.bar(range(len(rr)),[r['corrected_RMS_hz'] for r in rr],color=['#d55e00','#e69f00','#777777','#009e73'])
        ax.axhline(rr[0]['baseline_RMS_hz'],ls='--',color='black',label='No correction')
        ax.set(xticks=range(len(rr)),xticklabels=[r['relation'].replace('_','\n') for r in rr],ylabel='Pooled held RMS (Hz)',title=label+' / fitted c');ax.grid(axis='y',alpha=.2);ax.legend()
    fig.suptitle('Training-only witness predictions, fixed 6 s kernel\nSame scanwide held blocks removed from all witnesses. Pooled folds overlap; not independent replications.')
    save(fig,'witness_blocks.png')
    pulse_rows=[];pulse_full=[];diag=diagnostics[cases[1][1]]
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for col,a in enumerate(diag['results']):
        target=a['target'];t=np.array(target['times_s']);raw=np.array(target['residual_hz']);window=(t.min()-3,t.max()+3)
        witnesses=[v for v in a['all_active_curves'] if v['norad']==target['norad'] and v['component']!=target['component']]
        pulse=fit_pulse(witnesses,window);pred=pulse_prediction(t,pulse);residual=raw-pred;residual-=residual.mean()
        screen=lambda y:{k:v[0].item() for k,v in batch_noise_screen(y[None],t).items()}
        row=dict(arm=a['arm'],start_s=pulse['start_s'],end_s=pulse['end_s'],amplitude_hz=pulse['amplitude_hz'],
            target_RMS_before_hz=rms(raw),target_RMS_after_hz=rms(residual),before_pass=screen(raw)['noise_screen_pass'],after_pass=screen(residual)['noise_screen_pass'])
        pulse_rows.append(row);pulse_full.append(dict(arm=a['arm'],pulse=pulse,before_gates=screen(raw),after_gates=screen(residual),target_residual_after_hz=residual.tolist(),
            target_constant_profiled_after_correction=True,source_target_excluded_from_position=True,diagnostic_post_hoc_hypothesis=True,no_accepted_associations=True))
        for w in witnesses:
            u=np.array(w['times_s']);m=(u>=window[0])&(u<=window[1])
            if m.sum()<8:continue
            axs[0,col].plot(u[m],np.array(w['residual_hz'])[m],'.',ms=5,label=f"RX{w['receiver']} CH{w['channel']} {w['component'].split('-')[3]}")
        dense=np.arange(window[0],window[1],.05)
        axs[0,col].plot(dense,pulse_prediction(dense,pulse),'k--',label='Pulse from witnesses only')
        axs[1,col].plot(t,raw,'.-',color='#999999',label='Uncorrected target');axs[1,col].plot(t,residual,'.-',color='#0072b2',label='Target minus witness pulse + constant')
        axs[0,col].set(title=a['arm'],ylabel='Other same-family curves (Hz)');axs[1,col].set(xlabel='Time (s)',ylabel='Target residual (Hz)')
        for ax in axs[:,col]:ax.axvspan(pulse['start_s'],pulse['end_s'],alpha=.12,color='orange');ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('AUTO-f4b54f0c: 160–165 s shared transient\nExploratory event fit excludes target values. Full-data diagnostic, not accepted recovery or held-block validation.')
    save(fig,'shared_pulse.png');csvout('pulse_summary.csv',pulse_rows);write(out/'pulse_diagnostic.json',pulse_full)
    summary=dict(annotations_completed=sum(bool(r['annotation_source']) for r in ledger),inventory_total=len(ledger),annotation_batch=dict(Counter(r['status'] for r in batch)),
        cumulative_phase_audited=sum(bool(r.get('phase_audit_source')) for r in ledger),new_accepted_points=0,production_changed=False,retained_policy_changed=False)
    write(out/'summary.json',summary);csvout('executions.csv',executions)
    for name in ('validate_shared_family_blocks.py','shared_pulse_witness.py','report_shared_transient_validation.py','validate_receiver_residual_prediction.py','diagnose_graph_residual_witnesses.py'):
        p=Path(__file__).parent/name;sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    text=f'''# Shared transient diagnosis and blocked recovery validation

This iteration follows [shared residual recovery](../{args.previous.name}/README.md). It identifies a five-second transient shared by several curves in AUTO-f4b54f0c, tests whether receiver/satellite residual predictions generalize on two failed cases, and stress-tests the narrow 63381 conditional recovery. **No additional GLRT points are accepted, no retained policy changes, and no ALGO promotion is made.** The new pulse result is a diagnostic explanation with promising evidence, not a demonstrated position improvement.

## 63381 recovery: helpful in-sample, modest and mixed out of sample

Three saved random scanwide partitions use 12-second blocks and 2-second guards. All held and guarded values are excluded from curved calibration and predictive training views before fitting. Graph membership, incumbent identities, target identity/alias and physical prior choices stay frozen conditioning assumptions. Both models, both control/addition roles and both c arms use the same 150 Hz fixed noise, unit family powers, regional start, five phase rounds and 48 steps per round. This changes the noise policy from the previous full-data candidate but does so identically across variants.

The conditional model also changes its control because incumbent predictive observations can update the requested satellite and its old fragment constants. Each posterior update holds receiver coordinates fixed; repeated position/phase optimization can still move the overall receiver solution. The new target never enters receiver calibration equations. A new-fragment constant with sigma 300 Hz is estimated from target training values only; the held target residual uses exact orbital geometry. The raw phase gaps are below 0.01 s and all held geometry is within the orbit bank. These checks are numerical validity, not an association acceptance test.

{table(pooled,['mode','role','arm','target_RMS_hz','fold_observations'])}

Conditional inclusion improves its own control in all six target fold/arm RMS comparisons. However, pooled c=0 RMS remains worse than default inclusion (130.43 versus 126.23 Hz), and fitted-c improvement over default is small (130.04 versus 130.71 Hz). The addition's position error improves only in the first partition and worsens in the other two partitions in both models/arms. The complete 24 results, including incumbent held RMS and evaluation error, are in [shared_block_trials.csv](shared_block_trials.csv). Pooled folds overlap and are not independent replications. This does **not** establish a robust localization gain or justify promotion from the previous narrow lag-one pass.

![Shared-family blocked validation](figures/shared_blocks.png)

## Two remaining failures: no universal receiver correction

The target-excluded exact residual diagnostics retain every target point. AUTO-2ae9ee49's CH6 target has a residual slope of about 10.6–10.7 Hz/s, while same-family CH5 is about 11.9 Hz/s. Same-family low-band CH1 is only about 3.3–3.5 Hz/s. This is not a clean single shared satellite slope or a demonstrated band-wide receiver drift. In the target interval there are no qualifying other-family same-band slope witnesses. Some short downward excursions also coincide across CH5/6. Further time-local hardware/transmitter discrimination is needed; adding free per-track slopes would conceal the issue.

![AUTO-2ae9ee49 exact curve context](figures/{cases[0][1]}.png)

AUTO-f4b54f0c's CH2 residual has a brief positive excursion near 160–165 s. CH4 T000 and CH8 T003 assigned to the same satellite, 59467, show the same event. CH4 T001 and CH5 have sparse or absent coverage during the event and cannot serve as contemporaneous negative evidence. RX2 curves from other families do not show a comparably large pulse. This argues against a joining error unique to the target, but simultaneous RX1 receiver and transmitter explanations remain confounded: there is no comparably sampled other-family RX1 witness in that interval.

![AUTO-f4b54f0c exact curve context](figures/{cases[1][1]}.png)

Training-only witness prediction repeats the three existing distinct random partitions for **both** failed cases. The primary rule remains a 6 s Gaussian kernel using other satellites on the same receiver, requiring two families at each time. Same-band, other-receiver and same-satellite variants, widths 3/6/12 s, and Hz/fractional scaling are all retained in [all_witness_held_predictions.csv](all_witness_held_predictions.csv). No variant is selected for production using these results or GPS. These fits use curved observations only; they are different from the shared-family experiment above, which also trains incumbent predictive observations.

{table(wpooled,['scan','arm','relation','baseline_RMS_hz','corrected_RMS_hz','fold_observations'])}

AUTO-2ae9ee49 benefits in pooled RMS from same-RX other-family prediction, but one partition worsens in both c arms. Other-receiver prediction improves all six fold/arms, yet cannot identify a physical origin by itself. AUTO-f4b54f0c becomes worse under the primary same-RX correction and same-satellite 6 s correction. Broad smoothing can miss or blur a short pulse. Same-band sensitivity results improve pooled RMS with limited supported held points; they are not a prevalidated replacement. With no qualified witness at a held time the direct correction is zero, but the training-estimated fragment constant can still change, so zero supported held points need not mean identical held RMS.

![Witness blocked prediction](figures/witness_blocks.png)

## Five-second transient: a target-excluded diagnostic explains the failing gates

After inspecting the residual structure, an **exploratory** pulse model is fitted only to other curves of 59467 in the target time window plus 3 seconds on each side. It has one constant per witness and one shared additive-Hz rectangular pulse. Start/end are searched on a 0.5 s grid, durations 2–12 s; at least two witness curves need at least three points inside and outside, and at least eight points must be inside overall. The fixed amplitude prior is 150 Hz, assumed residual scale 75 Hz, with a three-parameter boundary/amplitude complexity penalty. The search score is not calibrated event confidence; boundary uncertainty and possible correlated channel errors are not integrated.

Both c arms independently select **160.0–165.0 s** from 94 witness observations. CH4 T000 and CH8 T003 provide direct inside/outside support. The target's values do not select boundaries or amplitude. After subtracting that prediction, one constant is profiled on the full target for this descriptive residual check; no target slope or polynomial correction is added.

{table(pulse_rows,['arm','start_s','end_s','amplitude_hz','target_RMS_before_hz','target_RMS_after_hz','before_pass','after_pass'])}

![Witness-selected shared pulse](figures/shared_pulse.png)

The roughly 189–190 Hz pulse reduces target RMS from about 98 to 55 Hz, and the unchanged mean/slope/quadratic/step/lag residual screen passes in both arms. This shows that a shared abrupt frequency feature can explain why the otherwise plausible track fails the smooth model. It does **not** establish the hardware origin, eliminate an upstream shared measurement artifact, validate all existing points after a joint refit, or add 42 accepted points. The target helped motivate the hypothesis, the witnesses were fitted on the full scan, and a target constant was profiled on all target points. Therefore this is not an independent holdout result. There is no new position estimate from this pulse diagnostic.

## Inventory and next experiment

Attempt 29 states: `{summary['annotation_batch']}`. Completed assessment coverage is **{summary['annotations_completed']} / {summary['inventory_total']}** original large-track entries; **{summary['cumulative_phase_audited']}** historical entries have separate phase audits. These counts include rejected/ambiguous/insufficient-partition outcomes and do not represent accepted coverage. [Annotation ledger](annotation_ledger.csv) preserves prior receipts and inclusion states. Execution receipts, including any bounded timeout, are in [executions.csv](executions.csv).

The next useful experiment is a shared transient model that carries event uncertainty, tests both RX-scoped and family-scoped explanations, and preserves all incumbent owners and gates under matched c arms. It should be nominated from witnesses excluding the target and tested on other curves/scans, including no-event controls. Scanwide block withholding can remove the entire event from all witnesses, so it tests temporal prediction, not merely contemporaneous correction. A new validation design must declare that distinction explicitly rather than quietly allowing held-time witness information into the existing test. Smooth causal orbital uncertainty remains appropriate for slow family mismatch; it cannot by itself explain an abrupt five-second pulse. Keep completing the remaining inventory in bounded batches instead of forcing these two cases through looser gates.

All position searches use the **25 × 25 km** region centered at **37.906, −122.545**. GPS **37.849061591561885, −122.48574968092912** is used solely for error reporting. Causal TLEs only; no new RF collection or production changes.

## Reproduction

`validate_shared_family_blocks.py run` consumes the saved 63381 inclusion and its predictive annotation partitions. `validate_receiver_residual_prediction.py run` consumes each failed case's predictive annotation. `diagnose_graph_residual_witnesses.py --shared-family --control` supplies the exact target-excluded context. `shared_pulse_witness.py` supplies the exploratory witness-only pulse fit. `report_shared_transient_validation.py` generates this report, CSVs and figures. Inputs and tool hashes are in [sources.json](sources.json), with compact scientific receipts in [evidence.json.gz](evidence.json.gz). Tests cover withheld-value isolation, disjoint partitions, training-only predictive views, conditional Gaussian updates, and independently offset witness curves recovering a common event.
'''
    (out/'README.md').write_text(text);print(summary)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
