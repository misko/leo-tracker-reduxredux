"""Report complete predictive trials and disjoint partial-curve recovery."""
import argparse,csv,gzip,hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_predictive_covariance_transfer import compact_replays
from report_systematic_annotation import compact_evidence
from report_predictive_track_annotation import table
from report_inventory_experiments import error
from report_predictive_margin_sensitivity import worst_replayed_slacks


def replay_slacks(row):
    return worst_replayed_slacks(dict(exact_incumbent_family_replays=row.get('exact_family_replays',row.get('exact_incumbent_family_replays',[]))))


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();hashes={};evidence={}
    def load(p):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p)
        evidence[str(p)]=compact_replays(compact_evidence(r));return r
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger}
    roots=[('Initial graph inclusion','predictive-queue34-inclusion-v1'),('Numerical follow-up','predictive-queue34-numerical-followup-v1'),
        ('Inactive fragment','inactive-graph-fragment-inclusion-v1'),('Fragment shared refresh','inactive-graph-fragment-shared-refresh-v1')]
    rows=[];comparisons=[];failures=[];executions=[];plots={}
    for label,name in roots:
        root=s/name;load(root/'protocol.json');cases=load(root/'execution.json')
        if (root/'replay-v2-execution.json').exists():load(root/'replay-v2-execution.json')
        for case in cases:
            job=case['job'];tid=job['track_id'];folder=root/tid;trial=folder/'trial'
            for stage in case['stages']:executions.append(dict(scan=job['label'],variant=label,**load(folder/(stage['stage']+'-terminal.json'))))
            if (folder/'replay-v2-terminal.json').exists():
                corrected=load(folder/'replay-v2-terminal.json');assert corrected['status']=='complete'
                executions.append(dict(scan=job['label'],variant=label,**corrected))
                log=folder/'replay.log';hashes[str(log)]=hashlib.sha256(log.read_bytes()).hexdigest();evidence[str(log)]=log.read_text()
            else:assert case['status']=='complete'
            pr=load(trial/'protocol.json');shared=case.get('shared_family',False)
            control=load(trial/'control.json');addition=load(trial/('target_0.json' if shared else 'new_family.json'))
            path=trial/('exact_owner_replay-v2.json' if (trial/'exact_owner_replay-v2.json').exists() else 'exact_owner_replay.json');audit=load(path)
            qualified=control['paired_valid'] and addition['paired_valid'] and audit['all_verified']
            target=set(o for t in pr['targets'] for o in t['observation_ids']);inv=load(Path(job['inventory']));den=inv['summary'][0]['total_GLRT']
            for role,pair in [('control',control),('target_0' if shared else 'new_family',addition)]:
                for arm,v in pair['arms'].items():
                    replay=next(r for r in audit['rows'] if (r['role'],r['arm'])==(role,arm));slacks=replay_slacks(replay)
                    before=set(control['arms'][arm]['proposed_associated_ids']);ids=set(v['proposed_associated_ids']);new=ids-before
                    changes=replay['incumbent_ownership_changes']
                    rows.append(dict(scan=job['label'],track_id=tid,variant=label,role=role,arm=arm,error_km=error(v),
                        proposed_associated=len(ids),percent_proposed=100*len(ids)/den,target_points=len(target),target_added=len(new&target),
                        incidental_added=len(new-target),lost=len(before-ids),paired_valid=pair['paired_valid'],exact_verified=replay['verified'],RF_qualified=qualified,
                        old_owner_missing=sum(c['after'] is None for c in changes),old_owner_reassigned=sum(c['after'] is not None for c in changes),
                        minimum_exact_slack=min(slacks.values()),objective=v['negative_twice_elbo'],phase_gap_s=v['final_phase_change_s'],
                        quadrature_pass=v.get('phase_resolution_audit',{}).get('local_agreement')))
                    for gate,slack in slacks.items():
                        if slack<0:failures.append(dict(scan=job['label'],variant=label,role=role,arm=arm,gate=gate,slack=slack))
                    if role!='control':
                        if shared:
                            diag=v['target_diagnostics'][0];times=np.array(diag['times_s']);residual=np.array(diag['residual_hz'])
                            ratios={k:1-slacks[diag['component']+'/linear/'+k] for k in ('slope','quadratic','step','lag1')}
                            cfo=diag['CFO_hz'];rms=diag['RMS_hz']
                        else:
                            diag=v['family']['diagnostics'][0];times=np.array(diag['times_s']);residual=np.array(diag['raw_residual_hz'])-diag['profile_bias_hz']
                            n=diag['noise'];ratios=dict(slope=n['slope_z']/3,quadratic=n['quadratic_bic_gain']/10,step=n['maximum_step_z']/4,lag1=abs(n['lag1_acf'])/(4/np.sqrt(len(times))))
                            cfo=diag['CFO_hz'];rms=diag['profile_RMS_hz']
                            for k,ratio in ratios.items():
                                if ratio>1:failures.append(dict(scan=job['label'],variant=label,role=role,arm=arm,gate=diag['component']+'/target/'+k,slack=1-ratio))
                        plots[job['label'],label,arm]=dict(times=times,residual=residual,cfo=cfo,ratios=ratios,rms=rms,qualified=qualified)
            c=dict(scan=job['label'],variant=label,target_points=len(target),RF_qualified=qualified)
            for arm in ('c0','fitted_c'):
                c[arm+'_control_km']=error(control['arms'][arm]);c[arm+'_addition_km']=error(addition['arms'][arm])
            comparisons.append(c)
            if 'fragment' in name:
                byid[tid].update(inactive_fragment_inclusion_source=str(trial),inactive_fragment_inclusion_status='RF_verified_candidate' if qualified else 'rejected')
            else:byid[tid].update(predictive_inclusion_source=str(trial),predictive_research_inclusion='RF_verified_candidate' if qualified else 'rejected; residual/numerical/owner evidence archived')
    csvout('position_trials.csv',rows);csvout('comparison.csv',comparisons);csvout('failed_gates.csv',failures)
    root=s/'inactive-graph-fragment-annotation-v1';pr=load(root/'protocol.json');load(root/'execution.json');partial=[];parent_curves=[]
    for source,digest in pr['source_hashes'].items():assert hashlib.sha256(Path(source).read_bytes()).hexdigest()==digest
    write(out/'partial_inventory.json',pr)
    for job in pr['selected']:
        tid=job['track_id'];term=load(root/(tid+'-terminal.json'));assert term['status']=='complete';executions.append(dict(stage='fragment_annotation',**term))
        path=root/tid/'result.json';r=load(path);p=load(path.parent/'protocol.json');a=r['annotation'];target=p['target']
        partial.append(dict(scan=job['label'],track_id=tid,unused_points=len(target['observation_ids']),state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),
            distinct_partition_seeds=p['seed_list']))
        byid[tid].update(inactive_fragment_annotation_source=str(path),inactive_fragment_state=a['status'],inactive_fragment_norad=a['norad'])
        inv=load(Path(job['inventory']));tracks=load(Path(inv['job']['root'])/inv['job']['case']/'tracks.json');parent=tracks[target['parent_track_index']]
        selected=set(target['observation_ids']);mask=np.array([o in selected for o in parent['observation_ids']])
        parent_curves.append((job['label'],parent,mask,a['status']))
    csvout('partial_annotations.csv',partial);csvout('annotation_ledger.csv',ledger);csvout('executions.csv',executions)
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for ax,(scan,t,mask,state) in zip(axs.flat,parent_curves,strict=True):
        times=np.array(t['times']);values=np.array(t['values'])/1000
        ax.scatter(times[~mask],values[~mask],s=15,c='#888',label='Retained / excluded from candidate')
        ax.scatter(times[mask],values[mask],s=15,c='#d55e00',label='Disjoint unused candidate')
        ax.set(title=scan+' / '+state,xlabel='Scan time (s)',ylabel='Graph GLRT CFO (kHz)');ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle('Partial curves: retain the parent and annotate only unused observations\nSelection excludes ownership in either c arm; no CFO edits or new polynomial fit')
    save(fig,'partial_curves.png')
    fig,axs=plt.subplots(1,2,figsize=(16,6),layout='constrained');x=np.arange(len(comparisons))
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        ax.bar(x-.18,[r[arm+'_control_km'] for r in comparisons],.35,color='#888',label='Matched control')
        ax.bar(x+.18,[r[arm+'_addition_km'] for r in comparisons],.35,color='#d55e00',label='Proposed addition')
        ax.set(xticks=x,xticklabels=[r['scan']+'\n'+r['variant']+('\nQUALIFIED' if r['RF_qualified'] else '\nREJECTED') for r in comparisons],ylabel='Evaluation error (km)',title=arm)
        ax.tick_params(axis='x',labelrotation=65,labelsize=7);ax.legend();ax.grid(axis='y',alpha=.2)
    fig.suptitle('Every controlled trial remains visible; proposed points are not accepted points')
    save(fig,'position_trials.png')
    final=[('AUTO-8d229584','Numerical follow-up'),('AUTO-f08da5cb','Initial graph inclusion'),('AUTO-5b808147','Numerical follow-up'),
        ('AUTO-5cf2a9a9','Fragment shared refresh'),('AUTO-74824694','Fragment shared refresh')]
    fig,axs=plt.subplots(2,5,figsize=(19,7),layout='constrained')
    for col,(scan,label) in enumerate(final):
        for arm,color in [('c0','#0072b2'),('fitted_c','#d55e00')]:
            v=plots[scan,label,arm];axs[0,col].plot(v['times'],v['residual'],'.-',c=color,label=arm)
            keys=list(v['ratios']);offset=-.15 if arm=='c0' else .15
            axs[1,col].bar(np.arange(len(keys))+offset,list(v['ratios'].values()),.28,color=color)
        axs[0,col].set(title=scan,xlabel='Time (s)',ylabel='Profile residual (Hz)');axs[0,col].axhline(0,c='k',lw=.5);axs[0,col].legend(fontsize=7)
        axs[1,col].axhline(1,c='k',ls='--');axs[1,col].set(xticks=np.arange(len(keys)),xticklabels=keys,ylabel='Statistic / gate limit');axs[1,col].tick_params(axis='x',labelrotation=45)
        for ax in axs[:,col]:ax.grid(alpha=.2)
    fig.suptitle('Low RMS can still contain systematic structure\nProfile residuals above; whitened-noise gate statistics below (pass ≤ 1)')
    save(fig,'target_residuals.png')
    summary=dict(partial_inventory=len(pr['partial_inventory']),fragment_annotations=len(partial),fragment_statuses=dict(Counter(r['state'] for r in partial)),
        matched_position_trials=len(comparisons),qualified_trials=sum(r['RF_qualified'] for r in comparisons),
        assessed_any_role=sum(bool(r.get('annotation_source') or r.get('predictive_recheck_source') or r.get('inactive_fragment_annotation_source')) for r in ledger),inventory_total=len(ledger),production_changed=False)
    write(out/'summary.json',summary)
    for name in ('inactive_graph_fragment.py','annotate_predictive_only.py','include_predictive_annotations.py','include_new_predictive_family.py','audit_shared_predictive_inclusion.py','audit_predictive_family_inclusion.py','include_new_family_feasible.py','report_inactive_fragment_transfer.py'):
        p=Path(__file__).with_name(name);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    text=f'''# Predictive transfer failures and disjoint partial-curve recovery

This iteration advances two parts of systematic recovery: run every newly supported whole-curve candidate from annotation attempt 34 through controlled position inclusion, and support partially retained graph curves without duplicating observations. Identity support and physical compatibility remain separate decisions. **No production change is made.**

## All three supported whole-curve candidates were tested

The selection is all three supported identities from the preceding 16-case predictive-role batch, with no GPS selection. NORAD 68397 and 48445 use new/uncalibrated-family causal phase mixtures with orbital and receiver uncertainty; 59155 uses its retained shared-family posterior. Every control and addition starts at the same 25 × 25 km regional-box center (37.906, −122.545), with five phase rounds and matched budgets. c=0 and fitted-c observations, candidates and other priors are matched. GPS (37.849061591561885, −122.48574968092912) enters only this report's error calculation.

{table(comparisons,['scan','variant','target_points','c0_control_km','c0_addition_km','fitted_c_control_km','fitted_c_addition_km','RF_qualified'])}

![All position trials](figures/position_trials.png)

None of the three initial whole-curve additions passes full qualification. AUTO-8d229584 / 68397 improves apparent error by about 0.73 km, but its ~98 Hz target residual has a slope statistic near 3.95 (limit 3), step statistic near 4.48 (limit 4), and excessive lag correlation. A matched Powell follow-up resolves optimizer termination but leaves those physical residual failures. The apparent accuracy improvement does not authorize inclusion.

AUTO-f08da5cb / 59155 fails target slope, quadratic and step gates. AUTO-5b808147 / 48445 produces a large error regression, fails target and incumbent slope/structure checks, and leaves 16 incumbent owner entries missing. These are **missing owner records, not evidence of 16 confirmed reassignments**. Its 0.1 s phase quadrature also fails score/gradient agreement. A predeclared numerical follow-up uses Powell and 0.025 s quadrature for both control and addition; the local integration audit and residual checks still fail. That result remains numerically and physically unqualified. The immutable initial and follow-up evidence is preserved.

Each supervised stage has a 600 s cap. New-family fits allow 48 iterations / 240 objective calls per phase round. Shared-family fits retain the existing 48-step budget. Numerical follow-ups are triggered by optimizer or quadrature diagnostics, not by error against GPS. Raw objective comparisons between control and addition are not used as proof of localization improvement because their observation sets differ. [Arm-level results](position_trials.csv) separately report score, error, target additions, incidental extension additions, owner changes and qualification.

## Partial curves need a separate observation set

The inventory contains **{summary['partial_inventory']} distinct partially associated curves**. We freeze the three largest by unused-point count and the 28-point attempt-34 precondition failure. The new fragment view contains only parent observations unused by **both** c arms, including calibration and predictive ownership. Original graph tracks and calibration arrays remain unchanged. Times, CFO values, alias lifts and receiver basis rows are copied exactly by index; no new polynomial is fitted and no tail is cut by residual quality or position error.

{table(partial,['scan','unused_points','state','norad','minimum_margin'])}

![Partial curves](figures/partial_curves.png)

The 50-point fragment supports 64004 and the 49-point fragment supports 69450. The 51-point fragment has a prediction mismatch; the 28-point / 20.9 s fragment lacks enough independent random partitions. Annotation retains scanwide random 12 s blocks and 2 s guards, three distinct timestamp-selected holdouts, training-only nomination and no target-driven receiver calibration. Fragment labels remain conditional on the frozen parent graph and retained identities; they are not unconditional satellite probabilities.

Inclusion reconstructs the exact annotated fragment and rejects changed parent or ownership selections. It routes through the existing shared-family or new-family likelihood as appropriate. Both supported fragments are shared-family cases. Their first controlled inclusions retain all incumbent owners but fail the fragment residual-step gate (~4.2–4.3 versus 4). We then test the existing marginal shared-satellite refresh on both cases, preserving receiver means and unchanged gates. Every result is shown above; acceptance is determined by both c arms and independent exact-orbit/ownership replay, not RMS or coverage alone.

Shared refresh does not qualify either fragment. AUTO-5cf2a9a9 retains its target step failure. AUTO-74824694 passes the target's noise gates after refresh but fails conditional-mean gates on retained RX2 tracks. The matched shared-refresh controls also have conditional-mean failures, so this variant cannot support a clean inclusion claim. Neither the slight apparent error improvement for the latter scan nor the target-only pass overrides those control/incumbent failures.

![Target residuals and normalized gate failures](figures/target_residuals.png)

## Audit correction and interpretation

The first fragment replay encountered an indexing error: an appended predictive fragment was traversed as an original graph track, although it has no entry in the original orbit-time index. The fit already used the original graph-only membership view. The audit now uses the same view while retaining the fragment in predictive entries. Original failed receipts/logs remain archived; a separately named replay-v2 runs on the **same saved fits without refitting**. It verifies the physical failures instead of treating an audit crash as a scientific result. Unit tests protect the graph view, unchanged original arrays, both-arm ownership exclusion and annotation reconstruction.

**39 targeted tests pass**, including six tests for partial-fragment selection and provenance, plus existing predictive ownership/routing, phase convergence, covariance, queue and feasible-inclusion checks. The scientific runs separately exercise actual shared-family fragment inclusion and exact replay. The new-family fragment reconstruction path is implemented, but these two supported fragments do not empirically exercise it; that path still needs a suitable supported new-family fragment case.

These trials show why high predictive identity margins do not guarantee usable localization evidence: a candidate can beat its nominated competitors under uncertainty while retaining structured residuals under the physical endpoint model. Low RMS does not establish noise-like errors. Conversely, fragment selection now handles a real representation gap without dropping the parent or counting observations twice. The next diagnostic question is whether the remaining step-like behavior is shared by other simultaneous receiver/channel evidence, or local to the fragment/family. A shared nuisance correction needs independent witnesses; a free correction per curve could hide a wrong identity or join. No thresholds are widened here.

## Reproducibility and remaining scope

The ledger now records **{summary['assessed_any_role']} / {summary['inventory_total']}** curves assessed in at least one role. Fragment results are separate columns and do not overwrite earlier whole-parent evidence. This iteration has {summary['matched_position_trials']} matched position trials and {summary['qualified_trials']} fully qualified trials; qualification is not synonymous with accuracy improvement or production promotion. The other partially associated curves and remaining inventory entries still need assessment.

Use `annotate_predictive_only.py --inactive-fragment --uncalibrated-phase-mixture --distinct-partitions`; supported fragments then use the existing inclusion entry point, which reads their annotation provenance. Exact commands, terminal receipts and failed audit attempts are in [execution records](executions.csv). [The partial inventory](partial_inventory.json), [ledger](annotation_ledger.csv), [failed gates](failed_gates.csv), [source hashes](sources.json) and [compact scientific evidence](evidence.json.gz) preserve provenance. Current source hashes identify the report/replay implementation; original numerical trials predate the fragment route and remain preserved in their source paths. No future TLE, new RF recording, GPS-guided fit, production policy change or ALGO promotion is included.
'''
    (out/'README.md').write_text(text);print(summary,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('study','previous','output'):p.add_argument('--'+k,type=Path,required=True)
    run(p.parse_args())
