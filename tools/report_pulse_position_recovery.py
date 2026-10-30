"""Publish matched pulse position trials, negative joint result and inventory."""
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
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from leo.analysis.research.grouped_prediction import identity_consensus


def run(args):
    s=args.study;out=args.output;out.mkdir(exist_ok=False,parents=True);(out/'figures').mkdir()
    hashes={};evidence={};executions=[]
    def load(p):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p);evidence[str(p)]=compact_replays(compact_evidence(r));return r
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger};batch=[]
    queue=s/'systematic-annotation-v1';attempt=queue/'attempt-30';load(attempt/'protocol.json')
    for j in load(attempt/'selected.json'):
        tid=j['track_id'];term=load(attempt/(tid+'-terminal.json'));executions.append(dict(stage='annotation30',**term))
        if term['status']=='complete':
            path=queue/tid/'result.json';r=load(path);load(path.parent/'protocol.json');a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
            byid[tid].update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),annotation_source=str(path),
                partition_policy='distinct timestamps',geometry_only_early_exit=r.get('geometry_only_early_exit',False),distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        else:
            a=dict(status='execution_'+term['status'],norad=None)
            byid[tid].update(state=a['status'],annotation_execution_source=str(attempt/(tid+'-terminal.json')))
        batch.append(dict(scan=j['label'],track_id=tid,status=a['status'],norad=a['norad']))
    csvout('annotation_batch.csv',batch)
    inv=load(s/'all-large-track-recovery/8aeb63e8498b0c15/inventory.json');denominator=inv['summary'][0]['total_GLRT']
    records={};trials=[];failures=[];sources=[('nominal','shared-pulse-inclusion-f4b54f0c-v1'),
        ('boundary','shared-pulse-boundaries-f4b54f0c-v1'),('joint','pulse-joint-inclusion-f4b54f0c-v1')]
    for stage,folder in sources:
        root=s/folder;load(root/'protocol.json')
        for terminal in sorted(root.glob('*-terminal.json')):
            term=load(terminal);assert term['status']=='complete';executions.append(dict(stage=stage,**term))
        for path in sorted(root.glob('*/result.json')):
            r=load(path);pr=load(path.parent/'protocol.json');records[(stage,path.parent.name)]=r
            for role in ('control','addition'):load(path.parent/(role+'.json'))
            for v in r['rows']:
                slacks={k:z for audit in v['exact_replays'] for k,z in audit['all_gate_slacks'].items()}
                for k,z in slacks.items():
                    if z<0:failures.append(dict(stage=stage,case=path.parent.name,role=v['role'],arm=v['arm'],gate=k,slack=z))
                trials.append(dict(stage=stage,case=path.parent.name,method=r['method'],role=v['role'],arm=v['arm'],
                    error_km=error(v),RF_qualified=v['evidence_qualified'],associated_proposed=len(v['proposed_associated_ids']),
                    percent_proposed=100*len(v['proposed_associated_ids'])/denominator,added=v['added_points'],lost=v['lost_points'],
                    owner_changes=len(v['incumbent_owner_changes']),event_amplitude_hz=v['event_amplitudes_hz'][0] if v['event_amplitudes_hz'] else None,
                    target_RMS_hz=v['exact_target']['RMS_hz'],objective=v['negative_twice_elbo'],minimum_gate_slack=min(slacks.values()),
                    phase_gap_s=v['final_phase_change_s'],start_s=r['events'][0]['time_s'] if r['events'] else None,end_s=r['events'][0]['end_s'] if r['events'] else None))
    csvout('all_position_trials.csv',trials);csvout('failed_gates.csv',failures)
    audit=load(s/'shared-pulse-replay-f4b54f0c-v1.json');scope=[];new=[]
    for r in audit['rows']:
        assert abs(r['objective_difference'])<=1e-5 and r['owners_replay_identically']
        if r['scope'] is not None:scope.append(dict(batch=Path(r['batch']).name,method=r['method'],role=r['role'],arm=r['arm'],
            event_amplitude_conditional_sigma_hz=r['event_amplitude_sigma_hz'],**r['scope']))
        for c in r['new_curves']:
            new.append(dict(batch=Path(r['batch']).name,method=r['method'],role=r['role'],arm=r['arm'],track_id=c['track_id'],
                component=c['component'],norad=c['norad'],new_points=c['new_points'],RMS_hz=c['RMS_hz'],**c['noise']))
    csvout('scope_identifiability.csv',scope);csvout('new_curve_diagnostics.csv',new)
    root=s/'pulse-incidental-annotation-f4b54f0c-v1';load(root/'protocol.json');term=load(root/'terminal.json');assert term['status']=='complete';executions.append(dict(stage='incidental identity',**term))
    r=load(root/'annotation/result.json');load(root/'annotation/protocol.json');vote=identity_consensus(r['folds'],score_name='conditional_target')
    write(out/'incidental_identity.json',vote);csvout('incidental_identity_votes.csv',vote['votes'])
    byid[r['track_id']].update(predictive_recheck_source=str(root/'annotation/result.json'),predictive_recheck_state=vote['status'],predictive_recheck_minimum_margin=vote['minimum_margin'])
    for tid in ('d07341fb93af4b6eca09','935edf55ee37a52ae810'):
        byid[tid].update(pulse_research_source=str(s/'pulse-joint-inclusion-f4b54f0c-v1/family_hz/result.json'),
            pulse_research_status='RF_qualified_research_candidate; joint position regression; not promoted')
    csvout('annotation_ledger.csv',ledger);csvout('executions.csv',executions)
    def find(stage,case,role,arm):return next(r for r in trials if (r['stage'],r['case'],r['role'],r['arm'])==(stage,case,role,arm))
    key=[('nominal','null','control','Original'),('nominal','null','addition','No pulse + CH2'),
        ('nominal','family_hz','control','Pulse; no new likelihood'),('nominal','family_hz','addition','Pulse + CH2'),
        ('joint','null','addition','No pulse + CH2/CH5'),('joint','family_hz','addition','Pulse + CH2/CH5')]
    comparison=[]
    for stage,case,role,label in key:
        a,b=[find(stage,case,role,arm) for arm in ('c0','fitted_c')]
        comparison.append(dict(variant=label,c0_error_km=a['error_km'],fitted_c_error_km=b['error_km'],
            proposed_associated=b['associated_proposed'],proposed_percent=b['percent_proposed'],paired_RF_qualified=a['RF_qualified'] and b['RF_qualified']))
    csvout('comparison.csv',comparison)
    fig,axs=plt.subplots(1,2,figsize=(14,6),layout='constrained');x=np.arange(len(comparison))
    for arm,offset,color in [('c0',-.18,'#0072b2'),('fitted_c',.18,'#d55e00')]:
        rr=[find(a,b,c,arm) for a,b,c,d in key]
        axs[0].barh(x+offset,[r['error_km'] for r in rr],.34,color=color,label=arm)
    labels=[r['variant']+(' [REJECTED]' if not r['paired_RF_qualified'] else '') for r in comparison]
    axs[0].set(yticks=x,yticklabels=labels,xlabel='Evaluation position error (km)');axs[0].invert_yaxis();axs[0].legend();axs[0].grid(axis='x',alpha=.2)
    for arm,color in [('c0','#0072b2'),('fitted_c','#d55e00')]:
        for a,b,c,label in key:
            r=find(a,b,c,arm);axs[1].scatter(r['percent_proposed'],r['error_km'],c=color,marker='o' if r['RF_qualified'] else 'x')
            if arm=='fitted_c':axs[1].annotate(label,(r['percent_proposed'],r['error_km']),xytext=(5,3),textcoords='offset points',fontsize=7)
    axs[1].set(xlabel='Proposed associated GLRT (%)',ylabel='Evaluation position error (km)',xlim=(76.5,80.5));axs[1].grid(alpha=.2)
    fig.suptitle('AUTO-f4b54f0c: increased association does not guarantee better position\nAll are research proposals; production policy is unchanged. Crosses fail RF checks.')
    save(fig,'position_and_coverage.png')
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    boundary=[r for r in trials if r['stage']=='boundary' and r['method']=='family_hz' and r['role']=='addition']
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        rr=[r for r in boundary if r['arm']==arm];xx=np.arange(len(rr))
        ax.bar(xx,[r['error_km'] for r in rr],color='#0072b2');ax.axhline(find('nominal','null','control',arm)['error_km'],color='black',ls='--',label='Original')
        ax.axhline(find('nominal','family_hz','addition',arm)['error_km'],color='#d55e00',label='Nominal pulse')
        ax.set(xticks=xx,xticklabels=[f"{r['start_s']}–{r['end_s']} s" for r in rr],ylabel='Position error (km)',title=arm);ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('All ±0.5 s boundary corners: CH2 inclusion preserves all gates and old owners\nReceiver and family scopes give identical results. Boundary uncertainty is not marginalized.')
    save(fig,'boundary_sensitivity.png')
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for col,arm in enumerate(('c0','fitted_c')):
        before=next(v for v in records[('joint','null')]['rows'] if v['role']=='control' and v['arm']==arm)
        after=next(v for v in audit['rows'] if v['batch'].endswith('pulse-joint-inclusion-f4b54f0c-v1') and v['method']=='family_hz' and v['role']=='control' and v['arm']==arm)
        for row,(b,c) in enumerate(zip([before['exact_target']]+before['extra_target_predictions'],sorted(after['new_curves'],key=lambda v:v['component']),strict=True)):
            t=np.array(c['times_s']);axs[row,col].plot(t,b['residual_hz'],'.-',color='#999999',label='No pulse');axs[row,col].plot(t,c['residual_hz'],'.-',color='#0072b2',label='Pulse model')
            axs[row,col].axvspan(160,165,color='orange',alpha=.15);axs[row,col].axhline(0,color='black',lw=.5)
            axs[row,col].set(title=arm+' / '+c['component'].split('-')[2],xlabel='Time (s)',ylabel='Exact-model residual (Hz)');axs[row,col].legend(fontsize=8);axs[row,col].grid(alpha=.2)
    fig.suptitle('Both new curves excluded from control position/calibration\nThe pulse explains CH2; CH5 retains a later shift. Each displayed curve constant is profiled.')
    save(fig,'new_curve_residuals.png')
    late=[];fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        v=next(r for r in records[('nominal','family_hz')]['rows'] if r['role']=='control' and r['arm']==arm)
        probe=next(r for r in audit['rows'] if r['batch'].endswith('shared-pulse-inclusion-f4b54f0c-v1') and r['method']=='family_hz' and r['role']=='control' and r['arm']==arm)
        target=next(c for c in probe['new_curves'] if '-CH5-' in c['component']);t=np.array(target['times_s']);y=np.array(target['innovations_hz']);splits=np.arange(4,len(y)-3)
        means=np.cumsum(y)[splits-1]/splits-(y.sum()-np.cumsum(y)[splits-1])/(len(y)-splits)
        z=abs(means)/(max(np.std(y,ddof=1),75)*np.sqrt(1/splits+1/(len(y)-splits)));k=int(splits[np.argmax(z)])
        mask=(t>=175)&(t<=200);ax.plot(t[mask],np.array(target['residual_hz'])[mask],'k.-',label='New CH5 T003')
        late.append(dict(arm=arm,component=target['component'],norad=59467,kind='target',before_points=k,after_points=len(y)-k,
            before_mean_hz=float(y[:k].mean()),after_mean_hz=float(y[k:].mean()),step_z=float(z.max()),bracket_start_s=t[k-1],bracket_end_s=t[k]))
        for family in v['exact_replays']:
            for w in family['family_witnesses']:
                u=np.array(w['times_s']);r=np.array(w['residual_hz']);left=(u>=175)&(u<182.5);right=(u>=182.5)&(u<=200)
                if left.sum()<3 or right.sum()<3:continue
                late.append(dict(arm=arm,component=w['component'],norad=family['norad'],kind='witness',before_points=int(left.sum()),after_points=int(right.sum()),
                    before_mean_hz=float(r[left].mean()),after_mean_hz=float(r[right].mean()),step_z=None,bracket_start_s=182.5,bracket_end_s=182.5))
                m=left|right;ax.plot(u[m],r[m],'.',label=f"{family['norad']} {w['component'].split('-')[2]} {w['component'].split('-')[3]}")
        ax.axvspan(t[k-1],t[k],color='orange',alpha=.2);ax.set(title=arm,xlabel='Time (s)',ylabel='Residual (Hz)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('CH5 late shift: no coherent second receiver/family correction established\nWitness windows 175–182.5 / 182.5–200 s; target uses its largest-step partition. Descriptive only.')
    save(fig,'ch5_remaining_shift.png');csvout('late_shift_witnesses.csv',late)
    summary=dict(annotations_completed=sum(bool(r['annotation_source']) for r in ledger),inventory_total=len(ledger),annotation_batch=dict(Counter(r['status'] for r in batch)),
        cumulative_phase_audited=sum(bool(r.get('phase_audit_source')) for r in ledger),pulse_RF_candidate_points=83,production_accepted_new_points=0,
        production_changed=False,retained_policy_changed=False)
    write(out/'summary.json',summary)
    for name in ('test_shared_pulse_inclusion.py','audit_shared_pulse_inclusion.py','report_pulse_position_recovery.py','ds23_frequency_events.py','audit_explicit_phase_endpoint.py'):
        p=Path(__file__).parent/name;hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    text=f'''# Shared pulse recovery propagated to position

The [previous diagnostic](../{args.previous.name}/README.md) identified a shared 160–165 s frequency excursion in AUTO-f4b54f0c (`fast8-auto-20261026-021217-3c1e1fc4-1-upper`). This iteration propagates it through the full shared calibration/position model. It recovers a **42-point CH2 curve** with an improvement in position error, supports an additional **41-point CH5 curve's identity** through a fresh causal search, and shows that adding both curves to the likelihood **does not improve localization**. No production policy or ALGO version is promoted.

## Controlled position comparison

All trials use the original observations, aliases, causal catalogue, noise policy, family powers and physical priors. All searches start at the center of the same 25 × 25 km regional box and use five phase rounds with 48 position steps per round. Both c arms are always run. The event has one Gaussian amplitude coordinate with a fixed zero-mean 150 Hz prior; its amplitude uncertainty is propagated jointly with existing coefficient covariance. Boundaries come from the previous target-excluded c0 witness diagnostic and are frozen at 160 and 165 s. The new curves remain excluded from receiver/event calibration normal equations; as predictive likelihoods they can affect position, which in turn changes calibration. This is a selected-case hypothesis, not an independently validated event detector.

{table(comparison,['variant','c0_error_km','fitted_c_error_km','proposed_associated','proposed_percent','paired_RF_qualified'])}

There are **4,031 total GLRT points**. Original association is 3,098 / 76.85%; the pulse model proposes 3,181 / 78.91%. The same 83 points are already recovered through post-fit extension in the pulse control, so adding CH2 or CH2+CH5 to the likelihood does not increase that count again. It changes how the recovered evidence constrains position. Rejected no-pulse rows are attempted fits, not usable solutions. “RF qualified” means every current gate and owner-preservation check passes; it does not prove truth or a localization improvement.

The pulse model itself changes fitted-c error from 0.572 to 0.530 km. Letting CH2 constrain position changes its **matched pulse control** from 0.530 to 0.518 km (c=0: 0.460 to 0.451 km). Do not attribute the entire baseline-to-target improvement to 42 new points. Adding both curves gives 0.588 km (c=0: 0.524 km), worse than both the pulse control and the original. Without the pulse, the two-curve fit is rejected and reaches 0.729 km / 0.665 km.

![Position and proposed association](figures/position_and_coverage.png)

## Receiver versus satellite scope is not identifiable here

All four combinations—receiver/satellite scope and additive-Hz/fractional-frequency scaling—were tested, with matched control and CH2 addition for each. Full results, objectives, residual RMS and gate margins are in [all_position_trials.csv](all_position_trials.csv). Compare objective values only between models with the same likelihood observations; controls and additions have different observation counts.

Receiver and satellite designs are **exactly equal on every observation used by the nominal likelihood**, not merely statistically similar. The control has 16 event-active observations and the two-column scope design has rank one. Their maximum elementwise difference is zero in all replayed variants. This scan cannot identify which physical system produced the pulse. Additive-Hz and fractional scaling have slightly different scores but nearly identical positions (~0.518 km fitted c). There is no evidence here to claim a transmitter fault or an RX1 fault specifically. A common upstream measurement artifact also remains possible.

The additive pulse amplitude is about 190.4–190.8 Hz, with conditional posterior SD ~23.3 Hz at the control endpoint. This SD conditions on fitted position, Gamma noise precisions and fixed event boundaries; it is not full uncertainty over event existence, origin or timing. [Scope receipts](scope_identifiability.csv) retain exact design equality and conditional amplitude SD for every fit.

## Boundary sensitivity and exact replay

All four ±0.5 s boundary corners were tested for **both** additive-Hz scopes, without selecting the best according to GPS. Every trial preserves all existing owners, all exact-orbit gates and the same 83 proposed new points. CH2 addition fitted-c errors range from about 0.503 to 0.546 km; c=0 from 0.436 to 0.478 km. This is sensitivity evidence, not marginalization of timing uncertainty and not independent validation on another recording.

![Boundary sensitivity](figures/boundary_sensitivity.png)

All 60 endpoints across nominal, boundary and two-curve experiments were independently rebuilt from saved references. Objectives and complete proposed owner maps replay identically. Event-aware graph extension applies the family contribution at each track's RF, including the event end; exact-orbit checks replace only the orbit and preserve the pulse. A zero-amplitude event reproduces the no-event objective and residual at the same endpoint. Every active family's orbit is substituted exactly, one at a time, for gate verification. No original point is reassigned or lost in the pulse proposals. Raw phase gaps are required to be ≤0.01 s; no clipped convergence flags are substituted.

## The second curve: correct-looking identity, incomplete residual model

The newly proposed curves are RX1 CH2 T002 (42 points) and RX1 CH5 T003 (41 points), both assigned to **59467**. CH5 was rerun through the causal predictive identity search without adding the pulse model. It selects 59467 in all three distinct scanwide block partitions and both c arms, with minimum competitor margin **{vote['minimum_margin']:.2f}**. The held-block design remains 12-second random blocks plus 2-second guards; incumbent graph/identities remain conditioning assumptions. The margin is a conditional score, not a calibrated identity probability, and the shortlist is not an exhaustive evidence integral over all catalogue identities.

The pulse control predicts CH2 at ~54 Hz RMS and CH5 at ~84–85 Hz RMS. CH2 has comfortable residual margins. CH5 passes the step gate narrowly: c=0 step z **3.99335** versus a threshold of 4, and fitted-c z **3.92540**. Its index-based lag-one residual correlation is about 0.54. A gate pass is not proof of white noise.

![Both new curve residuals](figures/new_curve_residuals.png)

CH5's largest remaining step divides the curve between **181.63 and 183.41 seconds**: the c=0 innovation means are about +29.6 and −100.1 Hz, with 32 and 9 points. An already retained same-satellite CH5 curve (T004) changes by only about −16.5 Hz across nearby descriptive windows. Another satellite's CH2 curve shifts ~−87 Hz, but that satellite's CH8 curve shifts only ~−7 Hz. These are limited descriptive witnesses with unequal sampling, not a corroborated second shared step. They do not justify blindly adding another receiver or satellite correction.

![Remaining CH5 shift and witnesses](figures/ch5_remaining_shift.png)

This explains why the extra CH5 curve must not be declared useful for positioning just because its identity and current gates pass. The next check is its native GLRT peak/graph-piece provenance, especially the late portion and its overlap with CH5 T004. Candidate explanations include a track join or peak-selection error, an inadequately modeled frequency effect, or overconfident weighting of a residual discrepancy. None is established yet. Keep the whole curve and its evidence in the inventory; do not truncate it or adjust its weight using GPS improvement.

## Systematic annotation status and decision

Attempt 30 states: `{summary['annotation_batch']}`. Completed inventory assessments now total **{summary['annotations_completed']} / {summary['inventory_total']}**, with **{summary['cumulative_phase_audited']}** historical separate phase audits. One case hits the 600 s cap; its claim and terminal receipt are preserved for diagnosis rather than silently retried. Counts include ambiguous, unstable and insufficient-partition outcomes, not just accepted satellite associations. The CH5 predictive recheck and both pulse research candidates are recorded in the cumulative [ledger](annotation_ledger.csv) without replacing older evidence.

The systematic workflow gains a new candidate mechanism: a target-excluded, multiply witnessed transient can explain strong curves rejected by a smooth model, and its uncertainty can be carried through position inference. The full result also reinforces a required distinction: **annotation, residual-model qualification, and useful position information are separate claims**. At present CH2 is a promising research recovery; CH5 needs further diagnosis, and the event's physical scope remains unidentified. No dataset-wide improvement or production acceptance is claimed.

GPS **37.849061591561885, −122.48574968092912** is used only for evaluation. The regional box is centered at **37.906, −122.545**. All TLE evidence is causal. No RF collection occurs.

## Reproduction and validation

`test_shared_pulse_inclusion.py run` produces all four scope/scaling combinations and a null control. `--boundary-sensitivity` produces all additive-Hz boundary corners. `one --extra-validation ...` verifies the second curve's supported identity/alias before joint inclusion. `audit_shared_pulse_inclusion.py` reconstructs all endpoints and records scope identifiability and exact new-curve residuals. `report_pulse_position_recovery.py` produces this report. Source hashes are in [sources.json](sources.json), compact raw scientific receipts in [evidence.json.gz](evidence.json.gz), and terminal statuses in [executions.csv](executions.csv).

**29 targeted tests pass**, including pulse onset/offset, receiver versus family scope, RF scaling, original step semantics, exact-orbit replay preserving a family event, phase convergence checks, ownership loss/relabel guards, and existing covariance/receiver-ramp/block validation tests. These tests and selected-case results do not replace independent false-recovery controls or validation across unused scans before promotion.
'''
    (out/'README.md').write_text(text);print(summary)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
