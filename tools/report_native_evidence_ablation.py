"""Publish cohort identity scoring, all physical trials, and graph inventory progress."""
import argparse
from collections import Counter
import csv,gzip,hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from report_inventory_experiments import error
from report_native_cohort_validation import failures
from leo.analysis.research.grouped_prediction import identity_consensus
from leo.analysis.research.target_identity_evidence import evidence_ablation
from leo.analysis.research.retained_track_likelihood import whitening,profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);figs=out/'figures';figs.mkdir();sources={};evidence={}
    def load(path,archive=True):
        path=Path(path);sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();r=read(path)
        if archive:evidence[str(path)]=r
        return r
    def csvread(path):
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return list(csv.DictReader(path.open()))
    def csvout(name,rows):
        if not rows:return
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    cohort=load(args.annotations/'protocol.json');annotations=csvread(args.annotations/'annotations.csv');votes=[];identity_rows=[]
    for row in annotations:
        root=Path(row['source']);r=load(root/'result.json');pr=load(root/'protocol.json')
        source=Path(pr['original_annotation_source'])/'result.json'
        if hashlib.sha256(source.read_bytes()).hexdigest()!=pr['original_annotation_sha256']:raise ValueError('source annotation changed')
        original=load(source,False);rebuilt=evidence_ablation(original)
        if r!=rebuilt:raise ValueError('score ablation did not replay exactly')
        for name,a in [('conditional',r['original_annotation']),('joint',r['annotation']),('training',r['training_evidence_annotation'])]:
            votes.extend(dict(scan=row['scan'],branch_id=row['branch_id'],rule=name,**v) for v in a['votes'])
        identity_rows.append(dict(scan=row['scan'],branch_id=row['branch_id'],points=int(row['points']),
            before=row['original_status'],after=row['status'],norad=row['norad'],minimum_joint_margin=row['minimum_margin'],
            training_status=row['training_status'],new_hypothesis=row['newly_supported_hypothesis']=='True'))
    csvout('identity_ablation.csv',identity_rows);csvout('identity_votes.csv',votes)
    states=['conditionally_supported_identity','ambiguous_identity','unstable_identity','prediction_mismatch','insufficient_partitions']
    matrix=np.zeros((len(states),len(states)),int)
    for r in identity_rows:matrix[states.index(r['before']),states.index(r['after'])]+=1
    fig,ax=plt.subplots(figsize=(8,7),layout='constrained');ax.imshow(matrix,cmap='Blues')
    for i in range(len(states)):
        for j in range(len(states)):ax.text(j,i,str(matrix[i,j]),ha='center',va='center',c='white' if matrix[i,j]>30 else 'black')
    labels=['Supported','Ambiguous','Unstable','Prediction mismatch','Insufficient partitions']
    ax.set(xticks=range(5),yticks=range(5),xticklabels=labels,yticklabels=labels,xlabel='Joint-evidence diagnostic',ylabel='Original conditional evidence',title='All 93 native proposals — classification changes, not truth labels')
    plt.setp(ax.get_xticklabels(),rotation=30,ha='right');fig.savefig(figs/'identity_transitions.png',dpi=140);plt.close(fig)
    native=[];native_execution=[];gallery=[];noise_rows=[];job_protocol=load(args.inclusions/'protocol.json')
    for job in job_protocol['jobs']:
        bid=job['branch_id'];root=args.inclusions/bid;terminal=load(args.inclusions/(bid+'-terminal.json'))
        available=all((root/f).exists() for f in ('control.json','target_0.json'))
        native_execution.append(dict(scan=job['scan'],branch_id=bid,status=terminal['status'],reason=terminal.get('reason'),matched_pair_available=available))
        if not available:continue
        c=load(root/'control.json');r=load(root/'target_0.json');load(root/'protocol.json')
        fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
        for col,arm in enumerate(('c0','fitted_c')):
            v=r['arms'][arm];d=v['native_target_diagnostics'][0];names={e['component'] for e in r['target_entries']}
            raw=np.asarray(d['CFO_hz'])-d['predicted_CFO_hz'];terms=profile(raw,np.zeros(len(raw)),*whitening(d['times_s']),bias_sigma=300.)
            if abs(terms['rms'][0]-d['RMS_hz'])>1e-6:raise ValueError('native residual profile did not replay')
            noise=batch_noise_screen(terms['innovations'],d['times_s']);limits={'mean_z':3.,'slope_z':3.,'quadratic_bic_gain':10.,'maximum_step_z':4.,'lag1_acf':4/np.sqrt(len(raw))}
            failed=[k for k,limit in limits.items() if abs(noise[k][0])>limit] # BIC negative means no structure.
            if noise['quadratic_bic_gain'][0]<0 and 'quadratic_bic_gain' in failed:failed.remove('quadratic_bic_gain')
            if terms['rms'][0]>450:failed.append('RMS')
            if abs(terms['bias'][0])>3000:failed.append('bias')
            if int(terms['alias'][0])!=0:failed.append('alias')
            noise_rows.append(dict(scan=job['scan'],branch_id=bid,arm=arm,target_pass=v['targets'][0]['compatible'],
                failed_replayed_checks=';'.join(failed),**{k:float(noise[k][0]) for k in limits},
                rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0]),alias=int(terms['alias'][0]),
                acf_limit=limits['lag1_acf']))
            native.append(dict(scan=job['scan'],branch_id=bid,norad=job['annotation']['norad'],arm=arm,points=job['points'],
                passes=r['paired_valid'],control_passes=c['paired_valid'],target_pass=v['targets'][0]['compatible'],
                before_km=error(c['arms'][arm]),after_km=error(v),added=v['added_points'],lost=v['lost_points'],
                target_rms_hz=d['RMS_hz'],failures=failures(v,names).replace('target_residual','target_gate'),target_noise_failures=';'.join(failed),
                failed_old_curves=';'.join(g['component'] for g in v['gates']['tracks'] if not g['compatible'])))
            axs[0,col].scatter(d['times_s'],np.array(d['CFO_hz'])/1000,s=10,c='black',label='Native GLRT CFO')
            axs[0,col].plot(d['times_s'],np.array(d['predicted_CFO_hz'])/1000,label='Prediction before track bias')
            axs[1,col].plot(d['times_s'],d['residual_hz'],'.-',ms=3);axs[1,col].axhline(0,c='black',lw=.5)
            axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Scan time (s)',ylabel='Residual after bias profiling (Hz)')
            for ax in axs[:,col]:ax.grid(alpha=.2)
            axs[0,col].legend(fontsize=7)
        fig.suptitle(f"{job['scan']} / NORAD {job['annotation']['norad']} / {job['points']} points / {'physical checks pass' if r['paired_valid'] else 'rejected'}\nExploratory identity-score change; original position model and gates")
        file=bid+'_native.png';fig.savefig(figs/file,dpi=130);plt.close(fig)
        gallery.append(f"### {job['scan']} / {bid}\n\n![CFO and residual](figures/{file})\n")
    csvout('native_position_trials.csv',native);csvout('native_execution.csv',native_execution);csvout('native_target_gate_replay.csv',noise_rows)
    (out/'native_gallery.md').write_text('# Every new native inclusion trial\n\n'+'\n'.join(gallery))
    # Advance the original graph ledger independently; native overlaps do not inflate it.
    previous=csvread(args.previous_ledger);byid={r['track_id']:r for r in previous};batch=[]
    load(args.queue/args.attempt/'protocol.json')
    for row in load(args.queue/args.attempt/'selected.json'):
        tid=row['track_id'];terminal=load(args.queue/args.attempt/(tid+'-terminal.json'))
        entry=dict(scan=row['label'],track_id=tid,points=row['points'],execution=terminal['status'],status='execution_'+terminal['status'],norad=None)
        if terminal['status']=='complete':
            path=args.queue/tid/'result.json';r=load(path);load(path.parent/'protocol.json');a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
            entry.update(status=a['status'],norad=a['norad']);byid[tid].update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),
                annotation_source=str(path),partition_policy='distinct timestamps',geometry_only_early_exit=r.get('geometry_only_early_exit',False),distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        else:byid[tid]['state']=entry['status']
        batch.append(entry)
    if len(previous)!=1630 or len(byid)!=1630:raise ValueError('graph inventory changed unexpectedly')
    csvout('annotation_ledger.csv',previous);csvout('graph_annotation_batch.csv',batch)
    graph=[];graph_execution=[];graph_gallery=[];gp=load(args.graph_inclusions/'protocol.json')
    for job in gp['jobs']:
        tid=job['track_id'];root=args.graph_inclusions/tid;terminal=load(args.graph_inclusions/(tid+'-terminal.json'))
        available=all((root/f).exists() for f in ('control.json','target_0.json'))
        graph_execution.append(dict(scan=job['label'],track_id=tid,status=terminal['status'],reason=terminal.get('reason'),matched_pair_available=available))
        if not available:continue
        c=load(root/'control.json');r=load(root/'target_0.json');load(root/'protocol.json')
        if (root/'single_combined_reuse.json').exists():
            reuse=load(root/'single_combined_reuse.json')
            if hashlib.sha256((root/'target_0.json').read_bytes()).hexdigest()!=reuse['source_sha256'] or load(root/'combined.json')!=r:
                raise ValueError('single-target reuse mismatch')
        fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
        for col,arm in enumerate(('c0','fitted_c')):
            v=r['arms'][arm];d=v['targets'][0];g=d['gate']
            graph.append(dict(scan=job['label'],track_id=tid,arm=arm,norad=job['annotation']['norad'],passes=r['paired_valid'],
                before_km=error(c['arms'][arm]),after_km=error(v),added=v['added_points'],lost=v['lost_points'],target_pass=g['compatible'],
                target_rms_hz=g['conditional_residual_gate']['rms_hz']))
            axs[0,col].scatter(d['times_s'],np.array(d['CFO_hz'])/1000,s=10,c='black',label='Graph GLRT CFO')
            axs[0,col].plot(d['times_s'],np.array(d['predicted_CFO_hz'])/1000,label='Physical prediction')
            axs[1,col].plot(d['times_s'],d['residual_hz'],'.-',ms=3);axs[1,col].axhline(0,c='black',lw=.5)
            axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Scan time (s)',ylabel='Residual (Hz)')
            for ax in axs[:,col]:ax.grid(alpha=.2)
            axs[0,col].legend(fontsize=7)
        fig.suptitle(f"{job['label']} / NORAD {job['annotation']['norad']} / {'passes' if r['paired_valid'] else 'rejected'}\nUnchanged annotation and position models")
        file=tid+'_graph.png';fig.savefig(figs/file,dpi=130);plt.close(fig);graph_gallery.append(f"### {job['label']} / {tid}\n\n![CFO and residual](figures/{file})\n")
    csvout('graph_inclusion_trials.csv',graph);csvout('graph_execution.csv',graph_execution)
    (out/'graph_gallery.md').write_text('# Every new graph inclusion trial\n\n'+'\n'.join(graph_gallery))
    audit_rows=[];target_causes=Counter()
    for r in load(args.graph_inclusions/'gate_audit.json')['results']:
        for role,key in [('curved','rows'),('predictive','linear_rows')]:
            for row in r[key]:
                if row['compatible']:continue
                audit_rows.append(dict(scan=r['scan'],track_id=r['track_id'],arm=r['arm'],role=role,
                    component=row['component'],norad=row['norad'],target=row.get('target',False),failures=';'.join(row['failures'])))
                if r['arm']=='fitted_c' and row.get('target'):target_causes.update(row['failures'])
    csvout('graph_gate_audit.csv',audit_rows)
    summary=dict(native_proposals=len(identity_rows),old_statuses=dict(Counter(r['before'] for r in identity_rows)),new_statuses=dict(Counter(r['after'] for r in identity_rows)),
        new_hypotheses=sum(r['new_hypothesis'] for r in identity_rows),native_executions=dict(Counter(r['status'] for r in native_execution)),
        native_paired_trials=len(native)//2,native_passing_trials=sum(r['passes'] for r in native if r['arm']=='fitted_c'),
        graph_annotation_outcomes=dict(Counter(r['status'] for r in batch)),graph_assessed=sum(bool(r['annotation_source']) for r in previous),graph_inventory=len(previous),
        graph_executions=dict(Counter(r['status'] for r in graph_execution)),graph_paired_trials=len(graph)//2,
        graph_passing_trials=sum(r['passes'] for r in graph if r['arm']=='fitted_c'),graph_target_gate_failures=dict(target_causes),no_production_change=True)
    write(out/'summary.json',summary);write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f)
    (out/'README.md').write_text(f'''# Native identity-evidence ablation and graph recovery iteration 17

The [preceding experiment](../2026_10_29_frozen_receiver_transfer/joint_evidence.md) found that conditional-only comparison can discard substantial evidence against a satellite's training fit. This iteration tests the score change across **all 93 previously assessed large native proposals**, then sends every newly supported hypothesis through the unchanged physical position pipeline. It also advances the separate 1,630-track graph ledger.

## Controlled score comparison

Every candidate, alias, phase prior, orbital prior, calibration fit, noise scale, randomized partition and c arm is frozen. For ordinary Gaussian-mixture predictions, add the stored training negative twice log density to the conditional-held negative twice log density. This equals the joint density of the target training-plus-held observations; guard points remain excluded. The original held RMS, geometry and convergence adequacy checks remain. We also record training-evidence-only consensus. The modular frozen-receiver predictor is explicitly rejected by this decomposition because its factorized prediction is a different model.

All 60 previously supported identities remain supported. The alternative score produces **21 additional hypotheses**: 17 formerly ambiguous and four formerly unstable. The remaining ten insufficient-partition cases and two problematic predictions are retained explicitly. This is not a count of 81 proved satellite identities. Candidate nomination used training data, the score rule was proposed after earlier case inspection, and neither false-association rates nor candidate-search completeness are independently calibrated. Incumbent associations and their shared calibration remain conditioning assumptions.

![Classification changes](figures/identity_transitions.png)

[All proposal classifications](identity_ablation.csv) and [every partition/c-arm vote](identity_votes.csv) retain the unfavorable results. No overlapping partition likelihoods are pooled, and no GPS error selects a candidate or trial.

## Original-model position trials

All 21 newly supported hypotheses are attempted, including those formerly unstable. There are **{summary['native_paired_trials']} complete paired trials; {summary['native_passing_trials']} pass** all original target/old-track gates in both c arms with no old-point losses. Execution outcomes: {summary['native_executions']}. A complete pair is reported even if a later operation times out, with its execution status preserved. Failed or unsupported-family executions are not treated as scientific rejection by the physical model.

{table([r for r in native if r['arm']=='fitted_c'],['scan','norad','points','passes','target_pass','before_km','after_km','added','target_rms_hz','failures'])}

These are individual hypotheses, not a combined recovery policy. Proposals can overlap or interact within a scan; their gains must not be summed into a dataset association percentage. Position errors above use the confirmed evaluation site only after inference. They are not evidence of identity correctness and do not select the winning trials. [Both-arm results](native_position_trials.csv), [execution receipts](native_execution.csv), [replayed target residual checks](native_target_gate_replay.csv), and [every CFO/residual figure](native_gallery.md) accompany the table. Native residual figures remove the fitted constant bias in the residual panel; the CFO panel shows the prediction before that bias. Some underlying exports retain historical DS25 component names while their frozen inventory labels are DS24; recording identities and source hashes are preserved.

The subsequent [bounded joint policy and 93-scan comparison](joint_policy.md) resolves overlaps for the selected configurations and reports actual net coverage and position changes. It preserves all previously associated point IDs and prior native satellite owners.

The rejected native trials expose two distinct problems: some targets retain residual slopes or steps, while three DS24-0089 proposals pass their own checks but the trial fails on existing RX1 CH1 T005 and loses old points. **Correction from the [matched optimizer investigation](../2026_10_30_native_feasible_refit/README.md): the no-addition control already fails.** The recovery refit had dropped the accepted incumbent's gate constraints. Retaining those constraints recovers 89 distinct points jointly without old-point losses; this supersedes the earlier interpretation that the recovered curves caused the conflict. Satellite identity and localization quality still require separate validation.

## Original graph inventory and inclusions

The next 32 graph assessments yield {summary['graph_annotation_outcomes']}. **{summary['graph_assessed']} / {summary['graph_inventory']}** original entries now have explicit assessments; ambiguous and unsuccessful results remain unresolved. Native alternatives do not inflate this denominator. Nine unavailable DS24 exports remain outside the existing frozen native cohort.

The preceding graph batch supplies **{summary['graph_paired_trials']} complete paired inclusion trials**, of which **{summary['graph_passing_trials']} pass** under the unchanged identity and position methods. Execution outcomes: {summary['graph_executions']}. The previous annotation timeout is recorded explicitly and excluded from inclusion, rather than silently dropped. Single-target `combined` results now reuse the numerically identical completed target fit, with a SHA receipt; this avoids the previously observed timeout caused by repeating that same fit. Multi-target configurations still receive their own joint fit.

{table([r for r in graph if r['arm']=='fitted_c'],['scan','norad','passes','before_km','after_km','added','target_rms_hz'])}

See the [full graph ledger](annotation_ledger.csv), [new assessments](graph_annotation_batch.csv), [both-arm inclusions](graph_inclusion_trials.csv), [execution status](graph_execution.csv), and [all graph figures](graph_gallery.md). These automatic-recording results are separate from the native DS24 cohort.

Exact endpoint replay separates the graph failures: fitted-c target causes are {dict(target_causes)}. [Every failed gate](graph_gate_audit.csv) distinguishes targets from existing curves and receiver/channel owners. A further [same-family joint experiment](graph_family_joint.md) tests whether independently nominated evidence on another receiver can supply missing orbital support without changing the model or relaxing a gate.

## Reproduction and remaining work

The numerical archives replace repetitive observation-ID lists and optimizer histories with counts and SHA-256 receipts. Full original artifacts remain at the recorded source paths; their file hashes are retained. Scores, residuals, gates, endpoints and reported metrics remain in the archives.

`audit_native_identity_evidence.py prepare` replays the 93 frozen annotations and materializes explicitly exploratory derived results. Its `evaluate` mode tests all newly supported hypotheses, using six workers and 600-second per-case caps. `run_annotation_inventory.py run --limit 32 --workers 16 --distinct-partitions` advances the graph queue. `run_supported_graph_inclusions.py --attempts attempt-16 --workers 8` tests the preceding graph annotations. All position runs preserve the regional-center 25×25 km start, original phase/receiver priors, five refresh rounds ×48 iterations, causal catalogue and matched c=0/fitted-c settings.

This step tests whether identity scoring is a bottleneck, not whether looser acceptance can inflate coverage. Inclusion gates are unchanged. Next, combine only independently supported, nonoverlapping evidence in measured joint trials, investigate old-track conflicts separately from target failures, and validate the score against difficult negative controls before promotion. The complete annotation/recovery objective remains open. [Source hashes](sources.json), [compressed numerical evidence](evidence.json.gz), and [summary](summary.json) support reproduction. No production change or new ALGO version is made.
''')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['annotations','inclusions','queue','previous-ledger','graph-inclusions','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--attempt',default='attempt-17');run(p.parse_args())
