"""Report training-derived confidence, constrained graph refits and full inventory."""
import argparse,copy,csv,gzip,hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read
from report_cross_family_prediction import held_metrics
from report_inventory_experiments import error
from prototype_dsx01_continuous_position import latlon
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from leo.analysis.research.grouped_prediction import identity_consensus


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=args.refresh);(out/'figures').mkdir(exist_ok=True)
    evidence={};sources={}
    def load(path):
        path=Path(path);sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();r=read(path);evidence[str(path)]=r;return r
    def csvout(name,rows):
        if not rows:return
        with (out/name).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    old=s/'native-position-cross-family-validation-v1';new=s/'native-training-confidence-validation-v1'
    replay=load(s/'native-training-confidence-replay-v2.json');unit_replay=load(s/'native-position-cross-family-replay-v2.json');protocol=load(new/'protocol.json')
    checks={(policy,r['scan'],r['seed'],r['arm'],r['role']):r for policy,a in [('support',replay),('unit',unit_replay)] for r in a['rows']}
    executions=[];folds=[];comparison=[];weights=[];weight_summary=[];strata=[]
    eligible=lambda r:r['kind']=='curved' and not r['same_family'] and r['train_points']>=4
    for j in protocol['jobs']:
        term=load(new/(j['name']+'-terminal.json'));prior_term=load(old/(j['name']+'-terminal.json'))
        executions.append(dict(scan=j['scan'],seed=j['seed'],unit_status=prior_term['status'],training_support_status=term['status']))
        load(new/j['name']/'protocol.json')
        wp=new/j['name']/'curve_weights.json'
        if wp.exists():
            receipt=load(wp);active=[r for r in receipt['curves'] if r['training_points']]
            weights.extend(dict(scan=j['scan'],seed=j['seed'],**r) for r in receipt['curves'])
            weight_summary.append(dict(scan=j['scan'],seed=j['seed'],active_curves=len(active),
                downweighted_curves=sum(r['training_power']<1 for r in active),
                changed_from_original=sum(r['training_power']!=r['original_full_data_power'] for r in active),
                weighted_points_fraction=sum(r['training_power']*r['training_points'] for r in active)/sum(r['training_points'] for r in active)))
        if term['status']!='complete':continue
        saved=load(new/j['name']/'result.json');prior=load(old/j['name']/'result.json') if prior_term['status']=='complete' else None
        # Preserve archived receipts, but use the independently replayed,
        # unclipped convergence check when qualifying plotted comparisons.
        for policy,record in [('support',saved),('unit',prior)]:
            if record is None:continue
            changed=copy.deepcopy(record)
            for arm,a in changed['arms'].items():
                for role,v in a['variants'].items():v['training_qualified']=checks[policy,j['scan'],j['seed'],arm,role]['raw_training_qualified']
            if policy=='support':saved=changed
            else:prior=changed
        for arm,a in saved['arms'].items():
            b,t=[a['variants'][role] for role in ('control','target')]
            m=held_metrics(b['held_predictions'],t['held_predictions'],eligible)
            native=held_metrics(b['held_predictions'],t['held_predictions'],lambda r:r['kind']=='native')
            folds.append(dict(scan=j['scan'],seed=j['seed'],arm=arm,control_qualified=b['training_qualified'],target_qualified=t['training_qualified'],
                other_points=m['points'],other_control_RMS_hz=m['control_RMS_hz'],other_target_RMS_hz=m['target_RMS_hz'],other_RMS_gain_hz=m['RMS_gain_hz'],
                native_RMS_gain_hz=native['RMS_gain_hz'],control_error_km=error(dict(endpoint_latlon=latlon(b['endpoint_east_north_km']))),
                target_error_km=error(dict(endpoint_latlon=latlon(t['endpoint_east_north_km'])))))
            if prior is None:continue
            for role in ('control','target'):
                u=prior['arms'][arm]['variants'][role];v=a['variants'][role]
                m=held_metrics(u['held_predictions'],v['held_predictions'],eligible)
                comparison.append(dict(scan=j['scan'],seed=j['seed'],arm=arm,role=role,
                    unit_qualified=u['training_qualified'],support_qualified=v['training_qualified'],
                    held_points=m['points'],unit_RMS_hz=m['control_RMS_hz'],support_RMS_hz=m['target_RMS_hz'],support_RMS_gain_hz=m['RMS_gain_hz'],
                    unit_error_km=error(dict(endpoint_latlon=latlon(u['endpoint_east_north_km']))),support_error_km=error(dict(endpoint_latlon=latlon(v['endpoint_east_north_km'])))))
                for family in sorted({r['norad'] for r in u['held_predictions'] if eligible(r)}):
                    mm=held_metrics(u['held_predictions'],v['held_predictions'],lambda r:eligible(r) and r['norad']==family)
                    strata.append(dict(scan=j['scan'],seed=j['seed'],arm=arm,role=role,norad=family,
                        both_qualified=u['training_qualified'] and v['training_qualified'],**mm))
    csvout('validation_executions.csv',executions);csvout('native_addition_held.csv',folds);csvout('weight_policy_comparison.csv',comparison)
    csvout('curve_weights.csv',weights);csvout('weight_summary.csv',weight_summary);csvout('held_family_comparison.csv',strata)
    fig,axs=plt.subplots(1,2,figsize=(13,6),layout='constrained')
    for ax,role in zip(axs,('control','target'),strict=True):
        rr=[r for r in comparison if r['role']==role];yy=np.arange(len(rr));colors=['#0072b2' if r['unit_qualified'] and r['support_qualified'] else '#d55e00' for r in rr]
        ax.barh(yy,[r['support_RMS_gain_hz'] for r in rr],color=colors);ax.axvline(0,c='black',lw=.5)
        ax.set(title='Without native addition' if role=='control' else 'With native addition',yticks=yy,
            yticklabels=[f"{r['scan']} / {r['seed']} / {r['arm']}" for r in rr],xlabel='Unit RMS − support-weighted RMS (Hz)');ax.tick_params(axis='y',labelsize=7);ax.grid(axis='x',alpha=.2)
    fig.suptitle('Training-derived confidence is not uniformly better on other-family held data\nPositive is better; orange means at least one compared endpoint fails training gates')
    fig.savefig(out/'figures/held_weight_comparison.png',dpi=145);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,role in zip(axs,('control','target'),strict=True):
        rr=[r for r in comparison if r['role']==role]
        for scan,color in [('DS24-0093','#0072b2'),('DS24-0063','#d55e00')]:
            good=[r for r in rr if r['scan']==scan and r['unit_qualified'] and r['support_qualified']]
            bad=[r for r in rr if r['scan']==scan and not(r['unit_qualified'] and r['support_qualified'])]
            ax.scatter([r['unit_error_km'] for r in good],[r['support_error_km'] for r in good],color=color,label=scan)
            ax.scatter([r['unit_error_km'] for r in bad],[r['support_error_km'] for r in bad],color=color,marker='x',s=65,label=scan+' / gate failure')
        lim=max([r[k] for r in rr for k in ('unit_error_km','support_error_km')]+[1])*1.05;ax.plot([0,lim],[0,lim],c='grey',ls='--');ax.set(xlim=(0,lim),ylim=(0,lim),title=role,xlabel='Unit-weight error (km)',ylabel='Training-support error (km)');ax.legend(fontsize=7);ax.grid(alpha=.2)
    fig.suptitle('Position error of randomized-block training fits\nThese are sparse training endpoints, not full-scan production performance')
    fig.savefig(out/'figures/training_position_comparison.png',dpi=145);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4),layout='constrained');xx=np.arange(len(weight_summary))
    ax.bar(xx-.17,[r['downweighted_curves'] for r in weight_summary],.34,label='Downweighted versus unit powers',color='#0072b2')
    ax.bar(xx+.17,[r['changed_from_original'] for r in weight_summary],.34,label='Changed versus original stored powers',color='#d55e00')
    ax.set(xticks=xx,xticklabels=[f"{r['scan']}\n{r['seed']}" for r in weight_summary],ylabel='Active curves',title='Relearning on training data usually reproduces the old heuristic');ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
    fig.savefig(out/'figures/weight_changes.png',dpi=145);plt.close(fig)

    graph=[];graph_execution=[];failures=[];gallery=[];audit_rows=[]
    for model,directory in [('unconstrained','graph-inclusion-batch22-v1'),('constrained','graph-inclusion-batch22-constrained-v1')]:
        root=s/directory;pr=load(root/'protocol.json');ga=load(root/'gate_audit.json');oa=load(root/'qualified_owner_audit.json');audit_rows.extend(dict(model=model,**r) for r in oa['rows'])
        owners={(r['track_id'],r['role'],r['arm']):r for r in oa['rows']}
        for r in ga['results']:
            for role,key in [('curved','rows'),('predictive','linear_rows')]:
                for v in r[key]:
                    if not v['compatible']:failures.append(dict(model=model,scan=r['scan'],track_id=r['track_id'],arm=r['arm'],role=role,target=v.get('target',False),component=v['component'],failures=';'.join(v['failures'])))
        for job in pr['jobs']:
            tid=job['track_id'];term=load(root/(tid+'-terminal.json'));graph_execution.append(dict(model=model,scan=job['label'],track_id=tid,status=term['status']))
            if term['status']!='complete':continue
            load(root/tid/'protocol.json');control=load(root/tid/'control.json');target=load(root/tid/'target_0.json')
            fig,axs=plt.subplots(2,2,figsize=(11,6),layout='constrained')
            for col,(arm,v) in enumerate(target['arms'].items()):
                c=control['arms'][arm];t=v['targets'][0];checks=[owners.get((tid,role,arm)) for role in ('control','target_0')]
                verified=bool(all(q and q['all_pass'] and not q['incumbent_ownership_changes'] and not q['control_ownership_changes'] for q in checks))
                graph.append(dict(model=model,scan=job['label'],track_id=tid,arm=arm,paired_RF_pass=target['paired_valid'],control_pass=control['paired_valid'],exact_owner_verified=verified,
                    added=v['added_points'],lost=v['lost_points'],control_error_km=error(c),target_error_km=error(v),
                    target_conditional_RMS_hz=float(np.sqrt(np.mean(np.array(t['residual_hz'])**2))),minimum_gate_slack=v.get('minimum_gate_slack')))
                axs[0,col].scatter(t['times_s'],np.array(t['CFO_hz'])/1000,s=10);axs[0,col].plot(t['times_s'],np.array(t['predicted_CFO_hz'])/1000)
                axs[1,col].plot(t['times_s'],t['residual_hz'],'.-',ms=3);axs[1,col].axhline(0,c='black',lw=.5)
                axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Conditional residual (Hz)')
            fig.suptitle(f"{model} / {job['label']} / NORAD {t['norad']}\nPaired RF pass: {target['paired_valid']}");f=f'figures/{tid}_{model}.png';fig.savefig(out/f,dpi=120);plt.close(fig);gallery.append(f"## {model} / {job['label']} / {tid}\n\n![Graph trial]({f})")
    csvout('graph_trials.csv',graph);csvout('graph_gate_failures.csv',failures);csvout('graph_executions.csv',graph_execution)
    (out/'graph_gallery.md').write_text('# Every original and constrained graph trial\n\n'+'\n\n'.join(gallery)+'\n')
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        before={r['track_id']:r for r in graph if r['model']=='unconstrained' and r['arm']==arm};rr=[r for r in graph if r['model']=='constrained' and r['arm']==arm];yy=np.arange(len(rr))
        ax.barh(yy-.17,[before[r['track_id']]['target_conditional_RMS_hz'] for r in rr],.34,color='#999999',label='Unconstrained')
        ax.barh(yy+.17,[r['target_conditional_RMS_hz'] for r in rr],.34,color=['#0072b2' if r['paired_RF_pass'] and r['exact_owner_verified'] else '#d55e00' for r in rr],label='Constrained (orange: not qualified)')
        ax.set(yticks=yy,yticklabels=[r['scan'] for r in rr],title=arm,xlabel='Target conditional RMS (Hz)');ax.tick_params(axis='y',labelsize=8);ax.legend(fontsize=7);ax.grid(axis='x',alpha=.2)
    fig.suptitle('Constrained refits: lower RMS alone is insufficient for acceptance')
    fig.savefig(out/'figures/graph_refinement.png',dpi=145);plt.close(fig)

    phase_path=s/'graph-batch22-annotation-phase-audit-v2.json';phase=load(phase_path)
    nominated=[r for r in phase['rows'] if r['nominated']]
    csvout('annotation_phase_checks.csv',[{k:r[k] for k in ('scan','track_id','seed','arm','norad','phase_s','reference_s','recorded_final_phase_change_s',
        'maximum_unclipped_phase_change_s','maximum_linearization_error_hz','held_linear_RMS_hz','held_exact_RMS_hz')} for r in nominated])
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,scan in zip(axs,('AUTO-99d8b775','AUTO-f0255747'),strict=True):
        rr=[r for r in nominated if r['scan']==scan];xx=np.arange(len(rr));ax.bar(xx-.17,[r['held_linear_RMS_hz'] for r in rr],.34,color='#999999',label='Tangent model')
        ax.bar(xx+.17,[r['held_exact_RMS_hz'] for r in rr],.34,color='#0072b2',label='Exact orbit mean')
        ax.set(title=scan,xticks=xx,xticklabels=[str(r['seed'])+' / '+r['arm'] for r in rr],ylabel='Held target RMS (Hz)');ax.tick_params(axis='x',rotation=65,labelsize=7);ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Nomination replay: a clipped reference concealed a nonconverged satellite phase')
    fig.savefig(out/'figures/annotation_phase_replay.png',dpi=145);plt.close(fig)
    fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained');tid='a8d10bb82a0c0a14ea77'
    candidate=evidence[str(s/'graph-inclusion-batch22-constrained-v1'/tid/'target_0.json')]
    for col,arm in enumerate(('c0','fitted_c')):
        t=candidate['arms'][arm]['targets'][0];a=next(r for r in audit_rows if r['model']=='constrained' and r['track_id']==tid and r['role']=='target_0' and r['arm']==arm)
        exact=next(r for r in a['family_witnesses'] if r['component']==t['component']);times=np.array(t['times_s']);y=np.array(t['CFO_hz']);linear=np.array(t['residual_hz']);residual=np.array(exact['residual_hz'])
        if len(times)!=len(residual):raise ValueError('exact plot support mismatch')
        axs[0,col].scatter(times,y/1000,s=12,color='black',label='GLRT')
        for res,color,label in [(linear,'#999999','Tangent approximation'),(residual,'#d55e00','Exact orbit replay')]:
            axs[0,col].plot(times,(y-res)/1000,color=color,label=label);axs[1,col].plot(times,res,'.-',ms=3,color=color,label=label)
        for ax in axs[:,col]:ax.grid(alpha=.2);ax.legend(fontsize=7)
        axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Conditional residual (Hz)');axs[1,col].axhline(0,c='black',lw=.5)
    fig.suptitle('AUTO-99d8b775: reject the apparent 46-point recovery\nFitted phase ≈18.1 s; linearization reference stuck at 15 s')
    fig.savefig(out/'figures/rejected_exact_orbit.png',dpi=145);plt.close(fig)

    previous=args.previous/'annotation_ledger.csv';sources[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger};q=s/'systematic-annotation-v1';attempt=q/'attempt-23';batch=[]
    load(attempt/'protocol.json')
    for j in load(attempt/'selected.json'):
        tid=j['track_id'];term=load(attempt/(tid+'-terminal.json'));v=dict(scan=j['label'],track_id=tid,status='execution_'+term['status'],norad=None)
        if term['status']=='complete':
            path=q/tid/'result.json';r=load(path);a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
            v.update(status=a['status'],norad=a['norad']);byid[tid].update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),annotation_source=str(path),partition_policy='distinct timestamps',geometry_only_early_exit=r.get('geometry_only_early_exit',False),distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        else:byid[tid]['state']=v['status']
        batch.append(v)
    if len(ledger)!=1630 or len(byid)!=1630:raise ValueError('inventory changed')
    for row in ledger:
        row.setdefault('phase_prior_state','');row.setdefault('phase_audit_source','')
    for a in phase['annotations']:
        row=byid[a['track_id']];row.update(phase_prior_state=row['state'],phase_audit_source=str(phase_path),state=a['corrected']['status'])
    csvout('annotation_ledger.csv',ledger);csvout('annotation_batch.csv',batch)
    summary=dict(graph_assessed=sum(bool(r['annotation_source']) for r in ledger),graph_total=len(ledger),annotation_batch=dict(Counter(r['status'] for r in batch)),
        training_confidence_executions=dict(Counter(r['training_support_status'] for r in executions)),
        training_confidence_paired_pass=sum(r['control_qualified'] and r['target_qualified'] for r in folds),
        completed_fold_arms=len(folds),matched_policy_comparisons=len(comparison),
        constrained_graph_executions=dict(Counter(r['status'] for r in graph_execution if r['model']=='constrained')),
        constrained_graph_paired_pass=sum(r['paired_RF_pass'] and r['exact_owner_verified'] for r in graph if r['model']=='constrained' and r['arm']=='c0'),
        annotation_phase_downgrades=sum(a['original']['status']!=a['corrected']['status'] for a in phase['annotations']),
        production_changed=False,retained_cohort_policy_changed=False)
    for name in ('report_training_confidence.py','training_curve_confidence.py','validate_explicit_phase_position.py','run_explicit_phase_validation.py','audit_explicit_phase_validation.py','refine_graph_inclusion_constraints.py',
                 'phase_reference_checks.py','annotate_track_predictively.py','include_curved_family_annotations.py','audit_annotation_phase.py'):
        path=Path(__file__).with_name(name);sources[str(path.resolve())]=hashlib.sha256(path.read_bytes()).hexdigest()
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(out/'sources.json').write_text(json.dumps(sources,indent=2)+'\n')
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f)
    full={k:v for k,v in evidence.items() if 'training-confidence' in k or k.endswith('qualified_owner_audit.json')}
    with gzip.open(out/'validation_receipts.json.gz','wt') as f:json.dump(full,f,separators=(',',':'))
    paired=[r for r in graph if r['model']=='constrained']
    (out/'README.md').write_text(f'''# Training-derived confidence and constrained graph recovery

This iteration finds and fixes a concrete false-convergence bug: measuring phase-reference change **after clipping** can report convergence even when the fitted satellite phase remains several seconds beyond the reference. Exact orbit replay rejects one apparently successful recovery and invalidates its earlier conditional identity annotation. A different 46-point recovery passes exact replay and improves both position-error arms. Refreshing the old confidence heuristic is not a general solution.

The experiments test whether old confidence weights are stale and whether constrained fitting can retain supported curves in the original model. They continue the [cross-family prediction study](../2026_10_30_cross_family_prediction/README.md). Production and retained cohort policy remain unchanged; no result is selected using GPS error.

## Training-only confidence experiment

The old heuristic is recomputed from training observations, using the same randomized scan-wide 12-second blocks and 2-second guards as the prior experiment. The c=0 unit-weight curved pilot supplies radio correction and a position. Candidate competition is evaluated at that position and four offsets of ±2 km east/north, clipped to the original 25 × 25 km region. The full causal catalogue is screened at every anchor using only each curve's training points. The native recovery candidate does not participate in weight learning. The resulting **same frozen weights** are used by both c arms and both control/addition variants. Measurement noise remains 150 Hz, so this isolates the power heuristic from noise-scale changes.

As in the original heuristic, a satellite with active training support on two receivers gets power 1; otherwise multiple receiver/channel owners and per-curve minimum confidence ≥0.95 give 0.6, and remaining curves receive 0.2. The screen integrates a linearized phase and constant approximation and omits physical orbit modes. Its soft catalogue score is **not a calibrated probability**. The rule can give two-receiver families full weight despite ambiguous competitor scores; this experiment deliberately preserves that behavior rather than silently changing the rule.

The graph, identities, earlier guard/prior choices and alias assignments remain frozen conditioning assumptions. Therefore this is not independent satellite identification. All fitting and scoring of the new confidence policy excludes held observed values; tests perturb excluded frequency, geometry and radio-correction inputs to the confidence screen. Completed fitted endpoints are also rebuilt and checked with the excluded-value perturbation audit. No future TLE or new RF collection is used.

{table(executions,['scan','seed','unit_status','training_support_status'])}

{table(weight_summary,['scan','seed','active_curves','downweighted_curves','changed_from_original','weighted_points_fraction'])}

![Confidence changes](figures/weight_changes.png)

Recomputed weights mostly reproduce the original stored powers. This weakens the specific hypothesis that stale stored powers are the main cause in these two cases; it does not establish that the heuristic itself is well calibrated. Small numbers of changed powers can still have large geometric effects.

## Independent-family prediction and position

The primary witness is the identical held original curved evidence from other satellite families, requiring at least four training points per curve. Positive RMS gain means better prediction. The control omits the recovered native curve; the target includes its training-only view. Constants for held native/predictive curves are learned from training points only. This uses plug-in orbit/receiver means, not a fully marginalized predictive probability. Partitions overlap and cannot be pooled as independent statistical replicates.

{table(folds,['scan','seed','arm','control_qualified','target_qualified','other_RMS_gain_hz','native_RMS_gain_hz','control_error_km','target_error_km'])}

![Held weighting comparison](figures/held_weight_comparison.png)

The weighting change helps some completed DS24-0063 partitions by a few Hz on other-family held evidence but substantially worsens seed 94721, where training gates also fail. The new curve's own held fit remains insufficient to certify a position improvement. DS24-0093 shows much smaller other-family changes. Neither this weighting rule nor the recovered-curve acceptance rule is ready for promotion.

![Position errors of training fits](figures/training_position_comparison.png)

These position errors describe **randomized-block training subsets**, not full-scan ALGO performance. GPS is used only for this evaluation. Some folds reach the regional boundary or fail gates; orange bars/crosses remain visible. A timeout is an unresolved execution and is excluded from paired comparisons, not relabeled as a scientific failure or success. The unit-policy comparison reuses the exact previous completed outputs and verifies identical held observation IDs. [All comparisons](weight_policy_comparison.csv), [family breakdown](held_family_comparison.csv), [native-addition effects](native_addition_held.csv), [weights](curve_weights.csv), [full validation receipts](validation_receipts.json.gz).

## Original-model graph inclusion and constrained refits

All 12 newly supported graph identities from annotation attempt 22 were tested in the original full model, with matched c arms and a refitted no-addition control. None passes. Eleven have residual-structure failures; one fails only the independent orbital-owner support gate. Several have both kinds of failure. Apparent position gains from rejected fits are not recoveries.

Eight trials have residual failures and **no** multiple-orbital-owner failure in either arm. Every such trial enters a second, bounded test; selection does not read position error. Both the control and target receive five additional phase-refresh rounds with 40 constrained optimizer steps each, starting at their corresponding original-model endpoints. The objective, identities, observations, receiver/orbit priors, noise, confidence powers, and acceptance gates remain unchanged. A 0.01 constraint margin is requested; final original gates and phase convergence are checked directly. The constrained optimizer can move position while nuisance parameters retain the original posterior-mean treatment. This is distinct from introducing an explicit satellite phase coordinate.

{table(paired,['scan','arm','paired_RF_pass','control_pass','exact_owner_verified','added','lost','control_error_km','target_error_km','minimum_gate_slack'])}

![Constrained graph diagnostics](figures/graph_refinement.png)

The constrained batch has **{summary['constrained_graph_paired_pass']} passing, exact-orbit/ownership-verified paired candidates**. `paired_RF_pass` is the archived tangent-model qualification, not final acceptance; `exact_owner_verified` is the independent follow-up check. Point additions in any failed row remain provisional. Complete fits retain all failure evidence, including failed gates on existing curves. [Every CFO and residual figure](graph_gallery.md), [all graph results](graph_trials.csv), [failures by component](graph_gate_failures.csv), [execution statuses](graph_executions.csv).

The verified recovery is **AUTO-f0255747, RX2 CH5, NORAD 67957, 46 points**. Error changes **1.899 → 0.250 km (c=0)** and **1.602 → 1.340 km (fitted c)** against the matched constrained controls. Both arms improve, but their large disagreement is important: this is not a robust 250 m localization claim. Exact selected-family orbit differences are below 10⁻⁸ Hz, and no incumbent or control satellite owner changes. Another constrained case, AUTO-64e97379, passes its modeled residual gates but loses **17 old points in c=0**, so it is rejected.

## A concrete bug: clipped phase is not convergence

AUTO-99d8b775 initially appears to recover 46 points with NORAD 100486. The fitted phases are **18.135 s (c=0)** and **18.079 s (fitted c)**, but the next linearization reference is clipped to **15 s**. Comparing successive clipped values gives a near-zero change, masking the remaining ~3.1 s error between the fitted phase and the linearization point. The tangent model and exact orbit differ by up to **269.9 / 260.3 Hz**. Exact replay fails slope, quadratic, mean, step and lag-one residual checks. The apparent position improvement is therefore not accepted evidence.

![False recovery exposed by exact orbit](figures/rejected_exact_orbit.png)

Reconstructing all original candidate endpoints for this annotation confirms the same problem in all six winning fold/arm fits. The winning phase is **18.06–18.39 s**, while the recorded clipped change is below 10⁻⁵ s. Held target RMS changes from roughly **36–92 Hz** under the tangent approximation to **145–263 Hz** under the exact orbit. Those RMS values alone do not prove a wrong satellite; they prove the earlier convergence and approximation claims were invalid. The candidate requires a valid exact/refreshed model before its identity can be supported.

![Nomination phase replay](figures/annotation_phase_replay.png)

The fix measures `max(abs(fitted_phase - reference))` **before clipping** the next reference. It keeps clipping for bounded geometry, records both changes and phase overflow, and rejects false convergence through the existing 0.01 s criterion. No phase window, prior or residual gate is relaxed. It is applied to future annotation training, graph inclusion, constrained graph refits and explicit-phase validation tools. The original historical receipts remain unchanged.

Replaying the annotation with only this convergence metadata corrected changes AUTO-99d8b775 from `conditionally_supported_identity` to **`prediction_mismatch`**; the scores are not reranked to manufacture a replacement identity. AUTO-f0255747 remains conditionally supported and has negligible tangent/exact discrepancy. The ledger records both the original state and the corrective audit source. The remaining historical annotations have not all received this retrospective check; their status remains conditional, and this audit must be expanded before relying on them for automatic inclusion.

[Winning-fold phase checks](annotation_phase_checks.csv) preserve both cases; all original competitor endpoints are archived in the numerical evidence. The displayed native validation qualification also uses newly replayed **unclipped** convergence checks, rather than trusting historical clipped flags.

## Inventory and next step

The original inventory now has **{summary['graph_assessed']} completed annotations out of 1,630 entries**, spanning DS24 and the automatic recordings. New batch classifications are `{summary['annotation_batch']}`. This is annotation coverage, not accepted association coverage. Timeouts and unresolved identity classes remain explicit. Native overlapping branches remain a separate inventory and are not added to this denominator. [Complete ledger](annotation_ledger.csv), [new batch](annotation_batch.csv).

The next priority is a bounded retrospective phase-consistency audit of supported annotations and passing inclusion candidates, followed by exact or correctly refreshed fitting for affected hypotheses. Refreshing the same support heuristic is not sufficient. Owner-only failures need independent family evidence rather than a weaker gate. Residual failures that survive the constrained fit need a model or evidence explanation, not acceptance based on lower GPS error.

## Reproduction and checks

Run `tools/run_explicit_phase_validation.py --weight-policy training_support` with the two diagnostic directories in the source receipts, then `tools/audit_explicit_phase_validation.py`. The noise level, masks, seeds, candidate catalogue, priors and per-fit budgets are matched to the previous unit-weight study. The 360-second per-job cap includes confidence learning; timeouts can therefore differ despite identical optimizer iteration budgets.

Run `tools/run_supported_graph_inclusions.py` on attempt 22, audit its rejected fits with `tools/audit_receiver_ramp_gates.py --graph`, and use `tools/refine_graph_inclusion_constraints.py run` for the recorded residual-only subset. Re-audit the constrained results with the residual and ownership/exact-orbit tools. The next annotation batch is attempt 23; all its terminal receipts are included.

**23 targeted tests pass**, covering exclusion of held values from confidence, active-training-owner counting, confidence thresholds, constrained-trial selection, training-view immutability, phase calculations, held observation identity, and false convergence at a clipped phase boundary. Endpoint replays and source hashes accompany the numerical evidence. No new ALGO version or dataset-wide improvement is claimed.

[Summary](summary.json), [source hashes](sources.json), [compact evidence](evidence.json.gz), [full validation receipts](validation_receipts.json.gz).
''')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--refresh',action='store_true');run(p.parse_args())
