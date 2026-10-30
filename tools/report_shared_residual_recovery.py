"""Publish witness tests, shared-family recovery and all transfer failures."""
import argparse,csv,gzip,hashlib,json
from collections import Counter
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
from residual_witness_prediction import predict,time_pairs
from leo.analysis.research.grouped_prediction import identity_consensus
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir()
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
    q=s/'systematic-annotation-v1';attempt=q/'attempt-28';load(attempt/'protocol.json')
    for j in load(attempt/'selected.json'):
        tid=j['track_id'];term=load(attempt/(tid+'-terminal.json'));executions.append(dict(stage='annotation28',**term));assert term['status']=='complete'
        path=q/tid/'result.json';r=load(path);load(path.parent/'protocol.json');a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
        byid[tid].update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),annotation_source=str(path),
            partition_policy='distinct timestamps',geometry_only_early_exit=r.get('geometry_only_early_exit',False),distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        batch.append(dict(scan=j['label'],track_id=tid,status=a['status'],norad=a['norad']))
    csvout('annotation_batch.csv',batch)
    diagnostic=load(s/'shared-control-witness-e565210d-v1.json');load(s/'shared-residual-witness-e565210d-v1.json')
    assert diagnostic['target_excluded_from_position']
    coherence=[];full=[]
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for col,v in enumerate(diagnostic['results']):
        target=v['target'];tt=np.array(target['times_s']);raw=np.array(target['residual_hz'])
        axs[0,col].plot(tt,raw,'k.-',label='Target RX1 CH1',lw=2)
        for w in v['all_active_curves']:
            if w['component']==target['component']:continue
            pairs=time_pairs(tt,w['times_s'],1.)
            if len(pairs)>=8:
                a=raw[pairs[:,0]];b=np.array(w['residual_hz'])[pairs[:,1]]
                coherence.append(dict(arm=v['arm'],norad=w['norad'],receiver=w['receiver'],channel=w['channel'],component=w['component'],
                    matched_pairs=len(pairs),correlation=float(np.corrcoef(a,b)[0,1]),same_family=w['norad']==target['norad']))
            if w['norad']==target['norad']:
                t=np.array(w['times_s']);mask=(t>=tt.min())&(t<=tt.max())
                if mask.sum()<4:continue
                axs[0,col].plot(t[mask],np.array(w['residual_hz'])[mask],'.-',ms=3,alpha=.65,label=f"RX{w['receiver']} CH{w['channel']} {w['component'].split('-')[3]}")
        for relation,color in [('same_receiver','#d55e00'),('same_satellite','#009e73')]:
            prediction=predict(target,v['all_active_curves'],width_s=6.,relation=relation,minimum_families=1 if relation=='same_satellite' else 2)
            residual=raw-prediction['prediction_hz'];screen={k:val[0].item() for k,val in batch_noise_screen(residual[None],tt).items()}
            full.append(dict(arm=v['arm'],relation=relation,baseline_RMS_hz=float(np.sqrt(np.mean(raw**2))),
                corrected_RMS_hz=float(np.sqrt(np.mean(residual**2))),covered_points=int(prediction['qualified'].sum()),**screen))
            axs[1,col].plot(tt,prediction['prediction_hz'],color=color,label=relation.replace('_',' '))
        axs[1,col].plot(tt,raw,'k.',label='Target residual');axs[0,col].set(title=v['arm'],ylabel='Same-family residual (Hz)')
        axs[1,col].set(xlabel='Time (s)',ylabel='Predicted residual (Hz)')
        for ax in axs[:,col]:ax.axhline(0,color='gray',lw=.5);ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('AUTO-e565210d: target excluded from position/calibration\nFull-fit witness diagnostic; kernel width 6 s, no target-driven amplitude or time shift.')
    save(fig,'residual_witnesses.png');csvout('coherence_pairs.csv',coherence);csvout('full_fit_prediction.csv',full)
    fig,axs=plt.subplots(1,2,figsize=(13,9),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        rr=sorted([r for r in coherence if r['arm']==arm],key=lambda r:(r['receiver'],r['norad'],r['component']))
        ax.barh(range(len(rr)),[r['correlation'] for r in rr],color=['black' if r['same_family'] else '#0072b2' if r['receiver']==1 else '#999999' for r in rr])
        ax.set_yticks(range(len(rr)),[f"{r['norad']} RX{r['receiver']} CH{r['channel']} {r['component'].split('-')[3]} (n={r['matched_pairs']})" for r in rr],fontsize=7)
        ax.invert_yaxis();ax.set(xlim=(-1,1),xlabel='Matched-time residual correlation',title=arm);ax.axvline(0,color='gray',lw=.5);ax.grid(axis='x',alpha=.2)
    fig.suptitle('All witnesses with ≥8 one-to-one pairs within 1 s\nBlack: same satellite; blue: other satellites RX1; gray: other satellites RX2. Descriptive, not independent confidence.')
    save(fig,'coherence_all_witnesses.png')
    held=[];primary=[];pool={};root=s/'receiver-residual-validation-e565210d-v1';protocol=load(root/'protocol.json')
    for seed in protocol['seeds']:
        terminal=load(root/(str(seed)+'-terminal.json'));assert terminal['status']=='complete';executions.append(dict(stage='held residual validation',**terminal))
        load(root/str(seed)/'protocol.json');r=load(root/str(seed)/'result.json')
        for v in r['results']:
            for row in v['rows']:
                rr={k:val for k,val in row.items() if k not in ('held_residual_hz','held_prediction_hz','held_distinct_families','witness_families')}
                rr.update(seed=seed,arm=v['arm'],phase_gap_s=v['training']['final_phase_change_s']);held.append(rr)
                if row['width_s']==6 and row['scaling']=='hz':
                    primary.append(rr);key=(v['arm'],row['relation']);pair=pool.setdefault(key,([],[]))
                    pair[0].extend(v['baseline_held_residual_hz']);pair[1].extend(row['held_residual_hz'])
    pooled=[dict(arm=a,relation=relation,baseline_RMS_hz=float(np.sqrt(np.mean(np.square(old)))),corrected_RMS_hz=float(np.sqrt(np.mean(np.square(new)))),fold_observations=len(old))
            for (a,relation),(old,new) in pool.items()]
    csvout('all_held_predictions.csv',held);csvout('primary_held_predictions.csv',primary);csvout('pooled_held_predictions.csv',pooled)
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        seeds=protocol['seeds'];x=np.arange(3)
        get=lambda relation:[next(r for r in primary if r['seed']==seed and r['arm']==arm and r['relation']==relation) for seed in seeds]
        base=get('same_receiver');ax.bar(x-.25,[r['baseline_held_RMS_hz'] for r in base],.25,color='gray',label='No correction')
        ax.bar(x,[r['held_RMS_hz'] for r in base],.25,color='#d55e00',label='Other satellites, same RX')
        sat=get('same_satellite');ax.bar(x+.25,[r['held_RMS_hz'] for r in sat],.25,color='#009e73',label='Same satellite, other curves')
        ax.set(xticks=x,xticklabels=[f"{seed}\nn={r['held_points']}" for seed,r in zip(seeds,base,strict=True)],ylabel='Held-point RMS (Hz)',title=arm);ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Random 12 s blocks + 2 s guards: refit position and curved calibration\nFixed graph/identities; 150 Hz noise/unit powers; target constant fitted on training points only.')
    save(fig,'held_block_prediction.png')
    trials=[];gates=[];models={};records=[('default','shared-predictive-transfer-e565210d-v1'),
        ('marginal_satellite','shared-satellite-refresh-e565210d-v1'),('conditional_satellite','conditional-satellite-refresh-e565210d-v1')]
    inv=load(s/'all-large-track-recovery/20eb5612efe80bc0/inventory.json')
    for mode,name in records:
        root=s/name;load(root/'protocol.json');term=load(root/'inclusion-terminal.json');executions.append(dict(stage=mode,**term))
        folder=root/'inclusion';pr=load(folder/'protocol.json');c=load(folder/'control.json');t=load(folder/'target_0.json');audit=load(folder/'exact_owner_replay.json');models[mode]=t
        target=pr['targets'][0]
        for arm,v in t['arms'].items():
            a=next(r for r in audit['rows'] if r['role']=='target_0' and r['arm']==arm);exact=next(r for r in a['exact_family_replays'] if r['norad']==target['norad'])
            prefix=target['component']+'/linear/';slacks={k[len(prefix):]:val for k,val in exact['all_gate_slacks'].items() if k.startswith(prefix)}
            threshold=4/np.sqrt(target['points']);d=v['target_diagnostics'][0]
            total=next(r['total_GLRT'] for r in inv['summary'] if r['arm']==arm)
            trials.append(dict(mode=mode,arm=arm,control_error_km=error(c['arms'][arm]),error_km=error(v),
                paired_gates=t['paired_valid'],replay_verified=audit['all_verified'],added_points=v['added_points'],lost_points=v['lost_points'],
                control_percent=100*len(c['arms'][arm]['proposed_associated_ids'])/total,target_percent=100*len(v['proposed_associated_ids'])/total,
                RMS_hz=d['RMS_hz'],absolute_lag1=(1-slacks['lag1'])*threshold,lag1_limit=threshold,
                receiver_update_change=a['receiver_coefficient_change'],owner_changes=len(a['incumbent_ownership_changes'])))
            gates.extend(dict(mode=mode,arm=arm,gate=k,slack=val) for k,val in slacks.items())
    csvout('shared_family_trials.csv',trials);csvout('shared_family_gates.csv',gates)
    byid['8c2ef4f04618dc6c227f'].update(predictive_research_inclusion='conditional_shared_RF_verified_candidate',
        predictive_inclusion_source=str(s/'conditional-satellite-refresh-e565210d-v1/inclusion'))
    fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for col,arm in enumerate(('c0','fitted_c')):
        for mode,color in [('default','#777777'),('marginal_satellite','#d55e00'),('conditional_satellite','#009e73')]:
            d=models[mode]['arms'][arm]['target_diagnostics'][0];tt=d['times_s']
            if mode=='default':axs[0,col].scatter(tt,np.array(d['CFO_hz'])/1000,s=12,color='black',label='GLRT')
            axs[0,col].plot(tt,(np.array(d['predicted_CFO_hz'])+d['bias_hz'])/1000,color=color)
            axs[1,col].plot(tt,d['residual_hz'],'.-',color=color,ms=3,label=mode)
        axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Profile residual (Hz)')
        for ax in axs[:,col]:ax.grid(alpha=.2)
        axs[1,col].axhline(0,color='black',lw=.5);axs[1,col].legend(fontsize=8)
    fig.suptitle('63381 recovery: shared physical parameters and existing constants\nConditional variant passes, but only narrowly clears lag-one correlation; no new track slope or kernel added.')
    save(fig,'shared_family_recovery.png')
    # Four newly selected recordings; preserve all identity and inclusion failures.
    cohort=[];cohort_trials=[];failures=[];owners=[];gallery=[]
    root=s/'graph-predictive-transfer25-v1';load(root/'protocol.json');conditional=s/'shared-conditional-transfer25-v1';load(conditional/'protocol.json')
    for result in load(root/'execution.json'):
        j=result['job'];tid=j['track_id'];path=root/tid/'annotation';r=load(path/'result.json');load(path/'protocol.json')
        a=identity_consensus(r['folds'],score_name='conditional_target');load(root/(tid+'-terminal.json'))
        for stage in result['stages']:executions.append(dict(scan=j['label'],**stage))
        cohort.append(dict(scan=j['label'],track_id=tid,status=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),initial_trial=result['status']))
        byid[tid].update(predictive_recheck_source=str(path/'result.json'),predictive_recheck_state=a['status'],predictive_recheck_minimum_margin=a.get('minimum_margin'),
            predictive_research_inclusion=result['status'])
        if result['status']!='inclusion_rejected':continue
        term=load(conditional/(tid+'-terminal.json'))
        for stage in term['stages']:executions.append(dict(scan=j['label'],group='conditional',**stage))
        fig,axs=plt.subplots(2,2,figsize=(12,6),layout='constrained')
        for mode,folder in [('default',root/tid/'inclusion'),('conditional',conditional/tid/'inclusion')]:
            pr=load(folder/'protocol.json');c=load(folder/'control.json');t=load(folder/'target_0.json');audit=load(folder/'exact_owner_replay.json')
            for col,(arm,v) in enumerate(t['arms'].items()):
                a=next(r for r in audit['rows'] if r['role']=='target_0' and r['arm']==arm)
                cohort_trials.append(dict(scan=j['label'],mode=mode,arm=arm,control_error_km=error(c['arms'][arm]),error_km=error(v),
                    paired_gates=t['paired_valid'],exact_owner_verified=audit['all_verified'],added_proposed_points=v['added_points'],lost_points=v['lost_points'],
                    owner_map_changes=len(a['incumbent_ownership_changes'])))
                exact=next(r for r in a['exact_family_replays'] if r['norad']==pr['targets'][0]['norad'])
                failures.extend(dict(scan=j['label'],mode=mode,arm=arm,gate=k,slack=z) for k,z in exact['all_gate_slacks'].items() if z<0)
                owners.extend(dict(scan=j['label'],mode=mode,arm=arm,before=before,after=after,count=count)
                    for (before,after),count in Counter((o['before'],o['after']) for o in a['incumbent_ownership_changes']).items())
                d=v['target_diagnostics'][0];tt=d['times_s'];color='#777777' if mode=='default' else '#d55e00'
                if mode=='default':axs[0,col].scatter(tt,np.array(d['CFO_hz'])/1000,s=12,color='black')
                axs[0,col].plot(tt,(np.array(d['predicted_CFO_hz'])+d['bias_hz'])/1000,color=color)
                axs[1,col].plot(tt,d['residual_hz'],'.-',color=color,label=mode,ms=3)
                axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Residual (Hz)')
        for ax in axs.ravel():ax.grid(alpha=.2)
        for ax in axs[1]:ax.axhline(0,color='black',lw=.5);ax.legend()
        fig.suptitle(j['label']+' — both variants REJECTED; proposed points are not accepted coverage')
        name=tid+'.png';save(fig,name);gallery.append(f"![{j['label']} rejected](figures/{name})")
    csvout('transfer_cohort.csv',cohort);csvout('transfer_trials.csv',cohort_trials);csvout('transfer_failures.csv',failures);csvout('owner_map_changes.csv',owners)
    csvout('annotation_ledger.csv',ledger);csvout('executions.csv',executions)
    summary=dict(annotations_completed=sum(bool(r['annotation_source']) for r in ledger),inventory_total=len(ledger),
        annotation_batch=dict(Counter(r['status'] for r in batch)),cumulative_phase_audited=sum(bool(r.get('phase_audit_source')) for r in ledger),
        new_cohort_cases=len(cohort),new_cohort_inclusions_qualified=0,shared_family_research_candidates=1,
        production_changed=False,retained_policy_changed=False)
    write(out/'summary.json',summary);write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    display=[r for r in primary if r['relation'] in ('same_receiver','same_satellite')]
    (out/'README.md').write_text(f'''# Shared-family recovery: a valid candidate, a falsified receiver hypothesis, and transfer limits

The AUTO-e565210d **42-point RX1 CH1 curve assigned to NORAD 63381** can pass the unchanged physical/residual gates under the existing **conditional shared satellite/fragment posterior** variant. Exact replay verifies unchanged incumbent owners and zero direct receiver-coordinate update. Fitted-c error is **0.918 km**, versus **0.920 km** for that variant's matched no-addition control. This is a recovery candidate with a very small position benefit, not a new localization breakthrough or production promotion.

The evidence did not support a generic receiver correction. Other-satellite RX1 residual prediction worsened four of six random-block fold/arm comparisons, whereas other curves of 63381 improved all six, two only slightly. The conditional physical update narrowly clears the correlation threshold, so robustness and uncertainty calibration remain necessary.

## Source and residual context

The target remains excluded from the diagnostic control's position likelihood and receiver calibration. We replay the frozen control objective and evaluate exact satellite geometry for its active curved and predictive witnesses. Residual comparison is conditional on the frozen graph and incumbent identities. We do not claim these full-fit residual correlations are independent statistical confidence.

![Witness residual context](figures/residual_witnesses.png)

Nearest-time matching uses one-to-one pairs within **1 s**, never reusing observations; every witness with at least eight pairs is displayed below. Two same-satellite RX1 CH2 curves correlate strongly with the target (~0.84–0.85 in the initial endpoint diagnostic). Several different satellites on RX1 also correlate, while RX2 witnesses are generally weaker. Those selective correlations motivated a receiver hypothesis; they did not establish it. Some same-family witnesses have little correlation, and overlaps differ substantially.

![All matched correlations](figures/coherence_all_witnesses.png)

The target's sample intervals range from ~0.354 to 9.920 s. Lag-one correlation is therefore an observation-index statistic, not a fixed time-lag measurement. We preserve the existing gate and separately test a time-aware predictor rather than changing its threshold to pass this curve.

## Target-excluded prediction: the receiver hypothesis does not transfer

The diagnostic predictor uses Gaussian time weights of width 6 s, truncated at ±18 s, no fitted amplitude or time shift, and equal votes across satellite families. Receiver variants exclude **every observation from 63381**, not just this curve, and require at least two other families at each query time. The same-family comparison excludes the target curve but uses its other family observations. Insufficient support produces a recorded zero correction. Hz scaling is primary; fractional RF scaling and widths 3/12 s are predeclared sensitivities, not selected according to error.

{table(full,['arm','relation','baseline_RMS_hz','corrected_RMS_hz','covered_points','noise_screen_pass'])}

Full-fit same-family residual subtraction passes the target screen, but that is only a diagnostic. To test prediction, we reuse the three original randomized **scan-wide 12 s blocks with 2 s guards**. Every held observation across all receivers/channels is removed before refitting the curved calibration. Fixed 150 Hz noise and unit family powers prevent reuse of full-data noise/weight learning. Old predictive observations are excluded from this particular training model. Witness residuals use training observations only. The target fits only one regularized constant using its training points; held target values never set it. Each c arm receives the same masks and budget.

{table(display,['seed','arm','relation','held_points','held_supported_points','baseline_held_RMS_hz','held_RMS_hz'])}

![Random-block prediction](figures/held_block_prediction.png)

{table(pooled,['arm','relation','baseline_RMS_hz','corrected_RMS_hz','fold_observations'])}

Pooling here is descriptive: held blocks overlap across seeds, so the 32 fold-observations per arm are not 32 independent new observations. The same-family comparator improves pooled RMS from **127.3 to 113.4 Hz** (c=0) and **130.6 to 116.6 Hz** (fitted c). The primary receiver predictor worsens both. Training models are refit on less data under a different fixed-noise policy, so their held RMS is not directly comparable to the ~62 Hz full-data fit. These tests do not optimize position using the kernel and do not establish a satellite-clock, TLE or hardware origin uniquely.

## Physical inclusion alternatives, with matched controls

No kernel correction is added to the production or position model. We test two existing physical posterior alternatives against the default shared predictor:

- **Marginal satellite projection:** expose posterior means for the requested shared satellite phase/orbital coordinates while preserving the marginal predictive likelihood and receiver-coordinate means in each update.
- **Conditional satellite/fragment update:** condition all unselected coefficient coordinates at their fitted means, then update the satellite phase, supported physical orbital modes and existing fragment constants. This changes the predictive likelihood and uncertainty; it is not merely a display of the same marginal posterior. It adds no per-track slope, polynomial or new satellite identity.

Each variant refits its own no-addition control and addition from the regional center with the same observations, five phase rounds, 48-step budget, priors and c ablation. Individual posterior updates hold receiver coordinates fixed; the repeated position/phase solve can still change them indirectly. A zero receiver-coordinate delta in the audit is not a claim that the entire fitted receiver solution is globally identical across variants.

{table(trials,['mode','arm','control_error_km','error_km','paired_gates','replay_verified','added_points','lost_points','control_percent','target_percent','absolute_lag1'])}

![Physical shared-family recovery](figures/shared_family_recovery.png)

The unchanged lag-one limit is **4/√42 = 0.61721**. Default prediction fails at ~0.646/0.652; marginal projection gets closer but still fails at ~0.624/0.622. Conditional prediction passes at ~0.613/0.611. These are **narrow margins**, not evidence that all residual structure has been eliminated. Its RMS is ~59.4/59.3 Hz. All prior points retain their owners, phase relinearization converges, and exact per-family replay preserves every gate.

Most of the apparent position change versus the old ~1.002 km fitted-c control comes from changing the predictive model itself: its conditional control is already ~0.920 km. Adding this curve improves that matched control by only **2.4 m** (about **3.5 m** in c=0). Do not attribute the entire cross-model difference to the recovered points. Conditioning away uncertainty needs separate validation; a passing residual threshold alone does not warrant a new ALGO release.

## Four new recordings test the workflow's limits

Selection was frozen to the first four supported attempt-25 annotations in original queue order, one per recording, without GPS ranking or requiring an earlier successful inclusion. Fresh predictive nomination uses the same causal catalogue, distinct grouped holdouts and unchanged identity margin. Both existing-family and absent-family routing are supported, but the two qualifying identities in this cohort use active shared families.

{table(cohort,['scan','status','norad','minimum_margin','initial_trial'])}

AUTO-69e994bf and AUTO-f08da5cb have **unstable identities**, with minimum margins ~0.59 and ~0.16. They receive no position inclusion. The two supported cases fail default shared prediction; applying the same conditional alternative to **both** also fails. No case is selected according to GPS benefit.

{table(cohort_trials,['scan','mode','arm','control_error_km','error_km','paired_gates','exact_owner_verified','added_proposed_points','lost_points','owner_map_changes'])}

AUTO-2ae9ee49 / NORAD 58639 fails the new RX1 CH6 residual slope and, in c=0, an old RX1 CH1 curve's slope. The conditional variant additionally fails that old curve in fitted c. It loses 25 associated points and produces **169 missing owner-map entries**, all previously assigned to 58639. This is not 169 reassignments to another satellite: 144 remain in the calibration mask but no longer receive an owner from the gate-qualified extension map. The inconsistent proposal is rejected.

AUTO-f4b54f0c / NORAD 59467 retains old owners but the RX1 CH2 target fails step and lag-one gates in both variants. Its 42 proposed points are not accepted recovery. The full gate names and normalized failure margins are retained in [transfer_failures.csv](transfer_failures.csv).

{chr(10).join(gallery)}

## Inventory, limitations and next actions

All 32 annotation jobs in attempt 28 complete, bringing assessed original inventory entries to **{summary['annotations_completed']} / {summary['inventory_total']}**. New states: `{summary['annotation_batch']}`. There are still **{summary['cumulative_phase_audited']}** historical phase-audited entries. Assessed count includes unsupported/ambiguous/geometry-limited cases; it is not accepted GLRT coverage. The ledger preserves original annotation sources, alternate predictive outcomes and research-inclusion status without changing retained policy.

The systematic workflow now has evidence for distinct failure classes: identity instability; unsupported new-family certainty; shared-family residual structure; and an addition that destabilizes old observations. No single correction fixes all four. In particular, the orbital-uncertainty result from the prior iteration is not a universal cure for active shared-family residuals.

Next, test the conditional recovery's narrow margin under frozen grouped perturbations before promotion. For the broader failures, inspect same-family cross-band slope witnesses on AUTO-2ae9ee49 and the step structure on AUTO-f4b54f0c, rather than loosening gates or repeatedly optimizing the resolved 63381 example. Any time-dependent shared-family model should carry its predictive uncertainty and be validated against withheld curves/blocks; the diagnostic kernel alone does not authorize one. Continue the remaining inventory in bounded batches.

All position searches start in the **25 × 25 km** box centered at **37.906, −122.545**. The evaluation site **37.849061591561885, −122.48574968092912** is used only for error reporting. All TLE evidence is causal. No RF collection, production deployment or new ALGO promotion occurs in this iteration.

## Reproduction and verification

`diagnose_graph_residual_witnesses.py --shared-family --control` constructs target-excluded exact residual context. `validate_receiver_residual_prediction.py` performs the grouped training-only experiment. `test_predictive_graph_transfer.py` handles the frozen new cohort; `include_predictive_annotations.py` runs the existing marginal/conditional alternatives. `audit_shared_predictive_inclusion.py` reconstructs them and replaces each active family's orbit with exact geometry for gate checks. Report generation: `report_shared_residual_recovery.py`.

**18 targeted tests pass**, covering witness family exclusion/balancing, one-to-one time matching, RF scaling, training-only target constants, phase convergence/domain checks, shared posterior invariants, routing, ownership and conditional Gaussian updates. Full source paths/hashes remain recorded; repetitive owner maps, gate maps, observation IDs and optimizer histories are compacted by counts/hashes while failures and numerical summaries remain visible.

[Summary](summary.json), [ledger](annotation_ledger.csv), [new annotations](annotation_batch.csv), [coherence pairs](coherence_pairs.csv), [full-fit diagnostic](full_fit_prediction.csv), [all held sensitivities](all_held_predictions.csv), [primary held comparisons](primary_held_predictions.csv), [pooled results](pooled_held_predictions.csv), [shared-family trials](shared_family_trials.csv), [gate margins](shared_family_gates.csv), [new cohort](transfer_cohort.csv), [transfer trials](transfer_trials.csv), [failures](transfer_failures.csv), [owner-map changes](owner_map_changes.csv), [executions](executions.csv), [source hashes](sources.json), [compact evidence](evidence.json.gz), [previous iteration](../2026_10_30_predictive_covariance_transfer/README.md).
''')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('study','previous','output'):p.add_argument('--'+key,type=Path,required=True)
    run(p.parse_args())
