"""Report conditional parameter diagnostics, all inclusion trials and inventory."""
import argparse
from collections import Counter
import csv,gzip,hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from leo.analysis.research.grouped_prediction import identity_consensus


def run(args):
    out=args.output;out.mkdir(exist_ok=False,parents=True);(out/'figures').mkdir();s=args.study;evidence={};hashes={}
    def load(path):
        path=Path(path);hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();r=read(path);evidence[str(path)]=r;return r
    def csvread(path):
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return list(csv.DictReader(path.open()))
    def csvout(name,rows):
        if not rows:return
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    diag=s/'native-parameter-consistency-v1';pr=load(diag/'protocol.json');full=[];held=[];witness=[];overview=[];gallery=[]
    colors=dict(bias_only='black',phase_orbit_fixed_bias='#999999',phase_orbit_bias='#0072b2',receiver_only='#d55e00',all_coordinates='#009e73')
    for j in pr['jobs']:
        bid=j['branch_id'];term=load(diag/(bid+'-terminal.json'))
        if term['status']!='complete':raise ValueError('incomplete parameter diagnostic')
        r=load(diag/bid/'result.json');load(diag/bid/'protocol.json');fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
        for col,(arm,v) in enumerate(r['full'].items()):
            axs[0,col].plot(v['times_s'],v['original']['residual_hz'],'.-',c='black',label='Original')
            for name,q in v['variants'].items():
                old_fail=sum(w['before']['compatible'] and not w['after']['compatible'] for w in q['witnesses'])
                full.append(dict(scan=j['scan'],branch_id=bid,arm=arm,model=name,before_RMS_hz=v['original']['RMS_hz'],after_RMS_hz=q['target']['RMS_hz'],
                    target_noise_pass=q['target']['noise']['noise_screen_pass'],new_conditional_witness_failures=old_fail,
                    receiver_coordinate_change=q['receiver_coordinate_change'],shift_mahalanobis=q['shift_mahalanobis'],exact_phase_error_hz=q['exact_phase']['maximum_phase_linearization_error_hz']))
                if name!='bias_only':axs[0,col].plot(v['times_s'],q['target']['residual_hz'],'.-',ms=3,color=colors[name],label=name)
            axs[0,col].set(title=arm+' / fixed-position diagnostic',xlabel='Time (s)',ylabel='Bias-profiled target residual (Hz)');axs[0,col].legend(fontsize=7)
            for k,fold in enumerate(r['folds']):
                z=fold['arms'][arm];base=z['variants']['bias_only']['prediction']
                for name,q in z['variants'].items():
                    pred=q['prediction'];held.append(dict(scan=j['scan'],branch_id=bid,arm=arm,seed=fold['seed'],model=name,
                        held_points=len(fold['held_target_indices']),RMS_hz=pred['rms_hz'],baseline_RMS_hz=base['rms_hz'],
                        RMS_gain_hz=base['rms_hz']-pred['rms_hz'],conditional_score_gain=base['negative_twice_log_density']-pred['negative_twice_log_density'],
                        receiver_coordinate_change=q['receiver_coordinate_change'],phase_change_s=z['training']['final_phase_change_s']))
                    for w in q['witnesses']:
                        witness.append(dict(scan=j['scan'],branch_id=bid,arm=arm,seed=fold['seed'],model=name,component=w['component'],
                            norad=w['norad'],receiver=w['receiver'],channel=w['channel'],same_family=w['same_family'],points=w['points'],
                            before_RMS_hz=w['before']['rms_hz'],after_RMS_hz=w['after']['rms_hz'],
                            before_noise_pass=w['before']['compatible'],after_noise_pass=w['after']['compatible']))
                for name in colors:
                    q=z['variants'][name]['prediction'];axs[1,col].scatter(k,q['rms_hz'],color=colors[name],label=name if k==0 else None)
            axs[1,col].set(xticks=range(len(r['folds'])),xticklabels=[str(f['seed']) for f in r['folds']],xlabel='Randomized block partition seed',ylabel='Held target RMS (Hz)')
            axs[1,col].legend(fontsize=7)
            for ax in axs[:,col]:ax.grid(alpha=.2)
        fig.suptitle(j['scan']+' / parameter explanation controls; no accepted recovery from these diagnostics')
        file='figures/'+bid+'_diagnostic.png';fig.savefig(out/file,dpi=140);plt.close(fig);gallery.append(f"## {j['scan']}\n\n![Parameter and held diagnostics]({file})\n")
        hh=[v for v in held if v['branch_id']==bid and v['model']=='phase_orbit_bias'];ff=next(v for v in full if v['branch_id']==bid and v['arm']=='fitted_c' and v['model']=='phase_orbit_bias')
        overview.append(dict(scan=j['scan'],branch_id=bid,original_RMS_hz=ff['before_RMS_hz'],satellite_bias_RMS_hz=ff['after_RMS_hz'],
            target_noise_pass=ff['target_noise_pass'],old_new_failures=ff['new_conditional_witness_failures'],
            held_RMS_wins=sum(v['RMS_gain_hz']>0 for v in hh),held_comparisons=len(hh),
            minimum_held_score_gain=min(v['conditional_score_gain'] for v in hh),maximum_held_score_gain=max(v['conditional_score_gain'] for v in hh)))
    csvout('full_parameter_diagnostics.csv',full);csvout('held_prediction.csv',held);csvout('held_witnesses.csv',witness)
    (out/'diagnostic_gallery.md').write_text('# Every native parameter diagnostic\n\n'+'\n'.join(gallery))
    # Aggregate witness RMS within each split; never pool overlapping split evidence.
    transfer=[]
    for j in pr['jobs']:
        r=read(diag/j['branch_id']/'result.json')
        for fold in r['folds']:
            for arm,a in fold['arms'].items():
                for name,q in a['variants'].items():
                    for family in (True,False):
                        ww=[v for v in q['witnesses'] if v['same_family']==family]
                        if not ww:continue
                        before=np.concatenate([v['before_residual_hz'] for v in ww]);after=np.concatenate([v['after_residual_hz'] for v in ww])
                        transfer.append(dict(scan=j['scan'],arm=arm,seed=fold['seed'],model=name,same_family=family,points=len(before),
                            before_RMS_hz=float(np.sqrt(np.mean(before**2))),after_RMS_hz=float(np.sqrt(np.mean(after**2)))))
    csvout('held_transfer.csv',transfer)
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,scan in zip(axs,['DS24-0090','DS24-0093'],strict=True):
        rr=[r for r in transfer if r['scan']==scan and r['model']=='all_coordinates' and not r['same_family']]
        ax.bar(range(len(rr)),[r['after_RMS_hz']-r['before_RMS_hz'] for r in rr],color=['#0072b2' if r['arm']=='c0' else '#d55e00' for r in rr])
        ax.axhline(0,c='black',lw=.7);ax.set(title=scan,xticks=range(len(rr)),xticklabels=[str(r['seed'])+'\n'+r['arm'] for r in rr],ylabel='Change in other-family held RMS (Hz)',xlabel='Positive = transferred correction worsens prediction')
        ax.grid(axis='y',alpha=.2)
    fig.suptitle('Target-driven full-parameter correction: independent held points on other families')
    fig.savefig(out/'figures/other_family_transfer.png',dpi=150);plt.close(fig)
    trials=[];execution=[];position_gallery=[]
    for optimizer,folder in [('free','native-conditional-satellite-inclusions-v1'),('feasible','native-conditional-satellite-feasible-v1')]:
        root=s/folder;protocol=load(root/'protocol.json')
        for j in protocol['jobs']:
            term=load(root/(j['key']+'-terminal.json'));directory=root/j['key'];available=all((directory/f).exists() for f in ['control.json','target_0.json'])
            execution.append(dict(scan=j['scan'],branch_id=j['branch_id'],model=j['model'],optimizer=optimizer,status=term['status'],reason=term.get('reason'),complete_pair_available=available))
            if not available:continue
            r=load(directory/'target_0.json');control=load(directory/'control.json');load(directory/'protocol.json')
            fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
            for col,(arm,v) in enumerate(r['arms'].items()):
                d=v['native_target_diagnostics'][0]
                trials.append(dict(scan=j['scan'],branch_id=j['branch_id'],model=j['model'],optimizer=optimizer,arm=arm,execution_status=term['status'],
                    passes=r['paired_valid'],control_passes=control['paired_valid'],target_pass=v['targets'][0]['compatible'],
                    added=v['added_points'],lost=v['lost_points'],before_error_km=error(control['arms'][arm]),after_error_km=error(v),
                    target_RMS_hz=d['RMS_hz'],objective=v['negative_twice_elbo'],final_phase_change_s=v['final_phase_change_s'],
                    exact_phase_error_hz=v.get('shared_satellite_replay',{}).get('maximum_phase_linearization_error_hz'),
                    failed_curved=';'.join(g['component'] for g in v['gates']['tracks'] if not g['compatible']),
                    failed_predictive=';'.join(g['component'] for g in v['linear_gates'] if not g['compatible'])))
                axs[0,col].scatter(d['times_s'],np.array(d['CFO_hz'])/1000,s=9);axs[0,col].plot(d['times_s'],np.array(d['predicted_CFO_hz'])/1000)
                axs[1,col].plot(d['times_s'],d['residual_hz'],'.-',ms=3);axs[1,col].axhline(0,c='black',lw=.6)
                axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Bias-profiled residual (Hz)')
            fig.suptitle(f"{j['scan']} / {j['model']} / {optimizer} / paired pass {r['paired_valid']}\nRejected endpoints are not accepted position estimates")
            file='figures/'+j['key']+'_'+optimizer+'.png';fig.savefig(out/file,dpi=125);plt.close(fig);position_gallery.append(f"## {j['scan']} / {j['model']} / {optimizer}\n\n![Position trial]({file})\n")
    csvout('position_trials.csv',trials);csvout('execution.csv',execution)
    (out/'position_gallery.md').write_text('# All native position trials\n\n'+'\n'.join(position_gallery))
    joint=s/'native-0014-extended-joint-v1';jp=load(joint/'protocol.json');load(joint/'execution.json')
    previous_joint=load(Path(jp['prior_joint_source']));matched_joint=load(joint/'previous/combined.json');extended=load(joint/'extended/combined.json')
    if not matched_joint['paired_valid'] or not extended['paired_valid']:raise ValueError('stacked native trial failed')
    old_owners={oid:e['norad'] for e in previous_joint['target_entries'] for oid in e['observation_ids']}
    new_owners={oid:e['norad'] for e in extended['target_entries'] for oid in e['observation_ids']}
    if any(new_owners.get(oid)!=norad for oid,norad in old_owners.items()):raise ValueError('previous native ownership changed')
    joint_rows=[];fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for col,(arm,v) in enumerate(extended['arms'].items()):
        before=previous_joint['arms'][arm];oldids=set(before['proposed_associated_ids']);newids=set(v['proposed_associated_ids'])
        if oldids-newids or len(newids-oldids)!=6:raise ValueError('incorrect net recovery')
        joint_rows.append(dict(arm=arm,before_points=len(oldids),after_points=len(newids),net_added=6,
            before_error_km=error(before),matched_previous_error_km=error(matched_joint['arms'][arm]),after_error_km=error(v)))
        d=next(d for d in v['native_target_diagnostics'] if d['component'].endswith(jp['replacement']))
        entry=next(e for e in extended['target_entries'] if e['component']==d['component']);fresh=np.array([oid not in oldids for oid in entry['observation_ids']])
        times=np.asarray(d['times_s']);cfo=np.asarray(d['CFO_hz']);residual=np.asarray(d['residual_hz'])
        axs[0,col].plot(times,np.array(d['predicted_CFO_hz'])/1000,c='#0072b2',label='Physical prediction before bias')
        for mask,color,label in [(~fresh,'#888888','Already associated: 33'),(fresh,'#d55e00','Newly recovered: 6')]:
            axs[0,col].scatter(times[mask],cfo[mask]/1000,s=20,color=color,label=label);axs[1,col].scatter(times[mask],residual[mask],s=20,color=color)
        axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[0,col].legend(fontsize=7)
        axs[1,col].set(xlabel='Time (s)',ylabel='Bias-profiled residual (Hz)');axs[1,col].axhline(0,c='black',lw=.6)
    fig.suptitle('DS24-0014: extend the accepted 33-point branch to 39 points, retain all other native branches')
    fig.savefig(out/'figures/ds24_0014_net_extension.png',dpi=150);plt.close(fig);csvout('joint_extension.csv',joint_rows)
    cohort=[]
    for r in csvread(args.previous/'cohort_accounting.csv'):
        v=extended['arms'][r['arm']] if r['scan']=='DS24-0014' else None
        if v and int(r['after_points'])!=len(previous_joint['arms'][r['arm']]['proposed_associated_ids']):raise ValueError('previous cohort baseline differs')
        cohort.append(dict(scan=r['scan'],arm=r['arm'],total_GLRT=int(r['total_GLRT']),before_points=int(r['after_points']),
            after_points=len(v['proposed_associated_ids']) if v else int(r['after_points']),before_error_km=float(r['after_error_km']),
            after_error_km=error(v) if v else float(r['after_error_km']),new_fit=bool(v)))
    csvout('cohort_accounting.csv',cohort);metrics=[]
    for arm in ('c0','fitted_c'):
        rr=[r for r in cohort if r['arm']==arm]
        for variant in ('before','after'):
            errors=[r[variant+'_error_km'] for r in rr];points=sum(r[variant+'_points'] for r in rr)
            metrics.append(dict(arm=arm,variant=variant,points=points,associated_percent=100*points/sum(r['total_GLRT'] for r in rr),
                mean_error_km=float(np.mean(errors)),median_error_km=float(np.median(errors)),p90_error_km=float(np.quantile(errors,.9))))
    csvout('cohort_metrics.csv',metrics)
    # Keep the original graph inventory distinct from overlapping native proposals.
    ledger=csvread(args.previous/'annotation_ledger.csv');byid={r['track_id']:r for r in ledger};queue=s/'systematic-annotation-v1';attempt=queue/'attempt-19';batch=[]
    load(attempt/'protocol.json')
    for r in load(attempt/'selected.json'):
        tid=r['track_id'];term=load(attempt/(tid+'-terminal.json'));entry=dict(scan=r['label'],track_id=tid,status='execution_'+term['status'],norad=None)
        if term['status']=='complete':
            path=queue/tid/'result.json';a=load(path);vote=identity_consensus(a['folds'],score_name=a.get('identity_score_name','joint'))
            entry.update(status=vote['status'],norad=vote['norad']);byid[tid].update(state=vote['status'],norad=vote['norad'],minimum_margin=vote.get('minimum_margin'),
                annotation_source=str(path),partition_policy='distinct timestamps',geometry_only_early_exit=a.get('geometry_only_early_exit',False),distinct_schedule_ready=not a.get('geometry_only_early_exit',False))
        else:byid[tid]['state']=entry['status']
        batch.append(entry)
    if len(ledger)!=1630 or len(byid)!=1630:raise ValueError('graph inventory changed')
    csvout('annotation_ledger.csv',ledger);csvout('graph_annotation_batch.csv',batch)
    gr=[];graph_gallery=[];root=s/'graph-inclusion-batch18-v1';gp=load(root/'protocol.json')
    for j in gp['jobs']:
        tid=j['track_id'];term=load(root/(tid+'-terminal.json'))
        if term['status']!='complete':raise ValueError('graph inclusion incomplete')
        r=load(root/tid/'target_0.json');c=load(root/tid/'control.json');fig,axs=plt.subplots(2,2,figsize=(11,6),layout='constrained')
        for col,(arm,v) in enumerate(r['arms'].items()):
            t=v['targets'][0];gr.append(dict(scan=j['label'],track_id=tid,arm=arm,passes=r['paired_valid'],control_passes=c['paired_valid'],target_pass=t['gate']['compatible'],
                norad=t['gate']['norad'],added=v['added_points'],lost=v['lost_points'],before_error_km=error(c['arms'][arm]),after_error_km=error(v)))
            axs[0,col].scatter(t['times_s'],np.array(t['CFO_hz'])/1000,s=9);axs[0,col].plot(t['times_s'],np.array(t['predicted_CFO_hz'])/1000)
            axs[1,col].plot(t['times_s'],t['residual_hz'],'.-',ms=3);axs[1,col].axhline(0,c='black',lw=.5)
            axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Residual (Hz)')
        fig.suptitle(f"{j['label']} / {tid} / paired pass {r['paired_valid']}");file='figures/'+tid+'_graph.png';fig.savefig(out/file,dpi=120);plt.close(fig)
        graph_gallery.append(f"## {j['label']}\n\n![Graph inclusion]({file})\n")
    csvout('graph_trials.csv',gr);(out/'graph_gallery.md').write_text('# All graph inclusions\n\n'+'\n'.join(graph_gallery))
    ga=load(root/'gate_audit.json');gate_rows=[]
    for r in ga['results']:
        for role,key in [('curved','rows'),('predictive','linear_rows')]:
            for v in r[key]:
                if not v['compatible']:gate_rows.append(dict(scan=r['scan'],track_id=r['track_id'],arm=r['arm'],role=role,target=v.get('target',False),component=v['component'],failures=';'.join(v['failures'])))
    csvout('graph_gate_failures.csv',gate_rows)
    summary=dict(native_cases=6,diagnostic_variants=list(colors),native_execution=dict(Counter(r['status'] for r in execution)),
        native_complete_pairs=sum(r['complete_pair_available'] for r in execution),native_passing_trials=sum(r['passes'] for r in trials if r['arm']=='fitted_c'),
        graph_assessed=sum(bool(r['annotation_source']) for r in ledger),graph_total=len(ledger),graph_annotation_outcomes=dict(Counter(r['status'] for r in batch)),
        graph_passing=sum(r['passes'] for r in gr if r['arm']=='fitted_c'),net_stacked_DS24_points=6,no_production_change=True)
    write(out/'summary.json',summary);write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f)
    (out/'README.md').write_text(f'''# Native residual failures: satellite, fragment bias, or receiver?

The conditional satellite/bias model does not qualify for recovery in these bounded trials. The original constrained model extends one already recovered DS24-0014 branch by six distinct points and improves its position error in both c arms. Separately, four original-model graph trials pass, adding 248 points across four automatic recordings; three improve position error and one worsens it.

This iteration follows the [matched recovery-fit audit](../2026_10_30_native_feasible_refit/README.md). It tests all four newly supported native proposals that still fail their own residual checks, plus both previously investigated native failures (DS24-0090 and DS24-0093). Selection uses failure class, not evaluation position error. It also advances the separate graph inventory and tests the preceding batch's supported identities.

## What the controlled parameter experiment means

The previous satellite-only moment projection could move a phase while leaving a correlated old fragment bias stale. For a coherent local Gaussian conditional diagnostic, partition parameters into free and fixed coordinates. Fix excluded coordinates at their original posterior means and use the **principal precision block** for the free coordinates; taking a principal covariance block would instead marginalize the allegedly fixed coordinates. Condition the free coefficients on the target using its existing measurement noise and 300 Hz constant-bias prior. No new drift, polynomial, orbital mode, threshold, or prior width is introduced.

Five diagnostic variants distinguish mechanisms: constant target bias only; existing satellite phase/orbit coordinates with old fragment biases fixed; those satellite coordinates plus their correlated old fragment biases; receiver coordinates only; and all existing coordinates. The last two can change receiver estimates and are **diagnostics only**. The proposed satellite/bias position model leaves receiver coefficients exactly unchanged at any fixed position. It changes predictive uncertainty by conditioning on excluded coordinates rather than integrating their uncertainty, so it is an empirical conditional model, not a recovered exact joint Bayesian posterior or a harmless plotting change.

The full-data diagnostic uses the saved RF-only endpoint and verifies its original objective to 1e-5. Its improvement alone is in-sample. Prediction checks refit calibration from the original regional center after withholding the same randomized 12-second blocks across **all receivers/channels**, with two-second guards. Target training points alone condition the new parameters and target constant bias. Three distinct timestamp-selected partitions and both c arms are retained. Training uses fixed 150 Hz noise, unit curve weights, and predictive variance multiplier two, matching the earlier validation protocol. Positions and Gamma noise precisions are plug-in estimates. Previously selected identities/graph assignments remain conditioning assumptions; this is model diagnosis, not independent validation of the joint identity-score rule.

{table(overview,['scan','original_RMS_hz','satellite_bias_RMS_hz','target_noise_pass','old_new_failures','held_RMS_wins','held_comparisons','minimum_held_score_gain','maximum_held_score_gain'])}

RMS columns and old-witness failures above are fitted-c full-data diagnostics; the held counts cover three partitions × two c arms. A held score gain is improvement in conditional log-predictive density relative to constant-bias-only prediction. Overlapping folds are not pooled into evidence or a significance claim. [All parameter diagnostics](full_parameter_diagnostics.csv), [held target predictions](held_prediction.csv), [held witnesses](held_witnesses.csv), and [every diagnostic plot](diagnostic_gallery.md) preserve mixed outcomes.

## What transfers to other curves?

DS24-0093 is the strongest satellite/bias hypothesis: the fixed-position target falls from about 95–105 Hz RMS to 64–66 Hz, no previously passing conditional witness fails in that diagnostic, and held target RMS improves in all six comparisons. Held density does not improve uniformly, and some same-family held witnesses worsen. The explanation therefore still needs a complete joint acceptance test.

DS24-0090 demonstrates why a target-only fit can mislead. Updating all existing coordinates lowers its held target RMS substantially, yet worsens the aggregate held residuals of other satellite families on that receiver in four of six comparisons (roughly 17–26 Hz in those cases). These witness points were excluded from calibration and conditioning. This argues against treating that target-induced receiver change as a generally supported correction. It does not by itself prove a wrong satellite ID. DS24-0063 has more favorable other-family receiver transfer in five of six comparisons and remains a separate receiver-model investigation. DS24-0069 retains target structure even after the all-coordinate full-fit diagnostic. DS24-0014's satellite/bias update improves none of the six held target RMS comparisons.

![Other-family held transfer](figures/other_family_transfer.png)

Witness aggregation is within each partition and only over available qualifying same-receiver overlapping curves. It is not a whole-scan error estimate or independent repetition across folds. [Transfer measurements](held_transfer.csv) expose the exact rows and point counts.

## Complete position trials, including failures

Every one of the six cases receives both the original predictive model and the conditional satellite/bias model, with matched c=0/fitted-c observations, candidates, original priors and regional bounds. Both start at the accepted RF incumbent and use SLSQP with five phase refreshes ×48 iterations. A second matched pair applies the existing feasibility constraints to both models, so a rescue is not automatically credited to a new satellite model when constrained fitting alone could explain it. Gate thresholds are unchanged. Final acceptance requires all old and new gates, zero old-point loss, bounded phase and at most 1 Hz exact phase-linearization discrepancy for refreshed models. Original point counts in rejected fits are proposals, not recoveries.

Execution outcomes: {summary['native_execution']}; {summary['native_complete_pairs']} complete control/target pairs; **native trials passing paired checks: {summary['native_passing_trials']}**. Partial artifacts and execution timeouts remain explicit. Passing trials are individual prototypes relative to their frozen baseline; they are not automatically stacked with the newer native joint policy, which can contain overlapping points and shared-parameter interactions.

{table([r for r in trials if r['arm']=='fitted_c'],['scan','model','optimizer','passes','control_passes','target_pass','added','lost','before_error_km','after_error_km','target_RMS_hz'])}

GPS is used only in this evaluation table after fitting. A better score or error in a rejected trial is not an accepted localization gain. Different predictive models condition on different uncertainty, so their raw scores cannot establish identity correctness. [Both-arm trial data](position_trials.csv), [execution receipts](execution.csv), and [every CFO/residual plot](position_gallery.md) contain the full comparison.

The new conditional model passes **none of its twelve complete native trials** (six scans × two optimizer variants). These bounded failures do not prove no feasible solution exists globally. The sole passing individual native trial is DS24-0014 under the original model with the existing constraints. Thus this iteration does not justify adding the conditional satellite/bias model to production.

## Stack the one supported recovery without counting overlaps

DS24-0014's passing 39-point proposal contains all 33 points of an already accepted native branch with the same satellite owner. Retain the other six native branches and replace only that branch. Run both the previous seven-branch configuration and this extended configuration with the same original-model constrained optimizer, priors and budget. Both pass in both c arms. Every prior point and native satellite owner is retained; the net recovery is **six points, not 39**.

{table(joint_rows,['arm','before_points','after_points','net_added','before_error_km','matched_previous_error_km','after_error_km'])}

![Six new points in context](figures/ds24_0014_net_extension.png)

The matched previous fit separates optimizer effects from adding the six observations. The 93-scan research-policy accounting changes only DS24-0014; the other 92 scans reuse previous results. This is not a dataset-wide rerun or validation of a new model. Nine unavailable exports remain excluded. [Joint extension](joint_extension.csv), [cohort accounting](cohort_accounting.csv), and [cohort metrics](cohort_metrics.csv) preserve this distinction.

{table(metrics,['arm','variant','points','associated_percent','mean_error_km','median_error_km','p90_error_km'])}

## Graph inventory and original-model inclusions

The annotation batch outcomes are {summary['graph_annotation_outcomes']}. **{summary['graph_assessed']} / {summary['graph_total']}** original entries now have assessments. Native alternatives do not change this denominator. [Full ledger](annotation_ledger.csv) and [batch outcomes](graph_annotation_batch.csv) retain uncertainty and timeouts.

The preceding batch supplies 20 original-model graph inclusion trials; **{summary['graph_passing']} pass** in both c arms. These automatic-recording prototypes use their original models and do not depend on the new conditional satellite/bias model.

{table([r for r in gr if r['arm']=='fitted_c' and r['passes']],['scan','norad','added','lost','before_error_km','after_error_km'])}

[All graph trials](graph_trials.csv), [failed gates](graph_gate_failures.csv), and [all graph CFO/residual figures](graph_gallery.md) preserve the rejected cases as well. These results are not merged into the DS24 native cohort's coverage percentage.

## Reproduction and limits

`probe_native_parameter_consistency.py` implements exact replay, parameter diagnostics and scan-wide randomized block refits. `fixed_coordinate_prediction.py` contains the tested conditional Gaussian calculation. `conditional_satellite_refresh.py` uses an equivalent low-dimensional Gaussian elimination for position fits; dense and low-dimensional implementations agree in tests. `include_predictive_annotations.py --conditional-satellite-refresh` is opt-in and does not change default inference. Inference protocols contain the exact commands and source hashes.

The six diagnostic jobs and twelve unconstrained position jobs have 600-second caps. The twelve matched feasible position jobs have 180-second caps. Each pool uses four workers. The two stacked DS24-0014 jobs use two workers and 180-second caps. Graph annotation uses 16 workers and 600-second per-case caps; graph inclusion uses eight workers. No new RF collection, future TLE, production deployment, or ALGO promotion occurs. Conditional physical feasibility and predictive model comparisons do not certify satellite identity. Difficult negative controls and independently selected recordings remain required before promotion.

The next diagnostic for DS24-0093 is a shared-phase feasibility interval across old and new curves at a fixed RF-only position, with fragment biases reconciled. The current constrained solver varies position while nuisance means remain conditional posterior estimates; its failure does not prove that no other plausible phase realization can satisfy the curves together. For DS24-0063, test a receiver correction learned exclusively from other families before evaluating its transfer to the native target. Keep these hypotheses separate from the unresolved false-association calibration of the identity score.

[Summary](summary.json), [source hashes](sources.json), and [compact numerical evidence](evidence.json.gz). Repetitive observation IDs and optimizer histories are compacted to receipts; full originals remain at recorded paths. The complete annotation/recovery objective remains active.
''')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('study','previous','output'):p.add_argument('--'+k,type=Path,required=True)
    run(p.parse_args())
