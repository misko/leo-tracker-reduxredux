"""Report a complete shifted-origin batch and the 58528 family challenge."""
import argparse,csv,gzip,hashlib,json,shutil
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from annotation_partition_plan import require_distinct_annotation
from leo.analysis.research.grouped_prediction import replay_split
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_predictive_role_reassessment import complete_replay_slacks
from report_omitted_predictive_recovery import target_diagnostic
from report_predictive_covariance_transfer import compact_replays
from report_systematic_annotation import compact_evidence
from review_annotation_competition import matched_expansion


def run(args):
    s=args.study;iteration=getattr(args,'batch',1);out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();hashes={};evidence={}
    def load(p):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p);evidence[str(p)]=compact_replays(compact_evidence(r));return r
    def csvout(name,rows):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    def verify_sources(record):
        for path,digest in record.get('source_hashes',{}).items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('source changed: '+path)
    q=s/'shifted-annotation-inventory-v1';frozen=load(q/'protocol.json');verify_sources(frozen)
    attempt=q/f'attempt-{iteration}';jobs=load(attempt/'selected.json');load(attempt/'protocol.json');load(attempt/'execution.json')
    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest();ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger}
    provenance=s/f'shifted-capture-provenance-v{iteration}';cap=load(provenance/'summary.json');verify_sources(cap);capture={r['track_id']:r for r in load(provenance/'rows.json')}
    shutil.copyfile(provenance/'capture_provenance.csv',out/'capture_provenance.csv')
    annotations=[];partitions=[];terminals=[];gallery=[];plots={};comparisons=[];positions=[];failures=[];competition=[]
    review=getattr(args,'competition_review',None);review_ids=set()
    if review:
        review_protocol=load(review/'protocol.json');verify_sources(review_protocol)
        review_ids={j['track_id'] for j in review_protocol['jobs']}
        review_execution=load(review/'execution.json')
        if {r['job']['track_id'] for r in review_execution}!=review_ids or any(r['status']!='complete' for r in review_execution):raise ValueError('competition review incomplete')
        expected={j['track_id'] for j in jobs if read(q/j['track_id']/'result.json')['annotation']['status']=='conditionally_supported_identity'}
        if review_ids!=expected:raise ValueError('competition review must cover every initially supported identity')
    for job in jobs:
        tid=job['track_id'];terminal=load(attempt/(tid+'-terminal.json'));terminals.append(terminal)
        if terminal['status']!='complete':raise ValueError('annotation not terminal complete')
        annotation_root=q;r=load(q/tid/'result.json');p=load(q/tid/'protocol.json')
        if tid in review_ids:
            expanded=load(review/tid/'result.json');counts=matched_expansion(r,expanded)
            competition.append(dict(track_id=tid,scan=job['label'],before_status=r['annotation']['status'],after_status=expanded['annotation']['status'],before_norad=r['annotation']['norad'],after_norad=expanded['annotation']['norad'],before_margin=r['annotation']['minimum_margin'],after_margin=expanded['annotation']['minimum_margin'],expanded_counts=' '.join(str(c['expanded']) for c in counts)))
            r=expanded;p=load(review/tid/'protocol.json');annotation_root=review
            terminals.append(load(review/(tid+'-terminal.json')))
        a=r['annotation'];inv=load(Path(job['inventory']))
        t=read(Path(inv['job']['root'])/inv['job']['case']/'tracks.json')[job['track_index']]
        require_distinct_annotation(r,p)
        if not p['partition_plan']['schedule']['partition_scheme']=='shifted_origin_v1':raise ValueError('not shifted validation')
        label=capture[tid]['source_case'] if capture[tid]['capture_mode']=='adaptive' else job['label']
        annotations.append(dict(scan=label,inventory_alias=job['label'],track_id=tid,points=job['points'],status=a['status'],norad=a['norad'],margin=a.get('minimum_margin'),capture_mode=capture[tid]['capture_mode']))
        for f in r['folds']:
            tr,he=replay_split(t['times'],f['split']);partitions.append(dict(track_id=tid,seed=f['seed'],origin_s=f['split']['block_origin_s'],training=int(tr.sum()),held=int(he.sum()),held_indices=' '.join(map(str,np.flatnonzero(he)))))
        byid[tid].update(predictive_recheck_source=str(annotation_root/tid/'result.json'),predictive_recheck_state=a['status'],predictive_recheck_minimum_margin=a.get('minimum_margin'),annotation_likelihood_role='predictive_only; shifted_origin_v1')
        gallery.append((job,t,a,label))
    root=s/f'shifted-annotation-inclusion-v{iteration}';retry=s/f'shifted-annotation-numerical-followup-v{iteration}';execution=load(root/'execution.json');verify_sources(load(root/'protocol.json'))
    if review and {r['job']['track_id'] for r in execution}!={a['track_id'] for a in annotations if a['status']=='conditionally_supported_identity'}:raise ValueError('inclusions must follow reviewed identities')
    followup={r['job']['track_id']:r for r in load(retry/'execution.json')};verify_sources(load(retry/'protocol.json'))
    for rec in execution:
        job=rec['job'];tid=job['track_id'];variants=[('initial',root,rec)]
        if tid in followup:variants.append(('numerical_followup',retry,followup[tid]))
        for variant,folder,run in variants:
            terminals.extend(dict(track_id=tid,variant=variant,**stage) for stage in run['stages'])
            if run['status']=='execution_failed':raise ValueError('inclusion incomplete')
            trial=folder/tid/'trial';p=load(trial/'protocol.json');control=load(trial/'control.json');v=load(trial/('target_0.json' if run['shared_family'] else 'new_family.json'));audit=load(trial/'exact_owner_replay.json');verify_sources(audit)
            qualified=bool(control['paired_valid'] and v['paired_valid'] and audit['all_verified']);final=variant==variants[-1][0]
            scope=None;scope_dir=getattr(args,'membership_scopes',None);scope_path=scope_dir/(tid+'.json') if scope_dir else None
            if final and scope_path and scope_path.exists():
                scope=load(scope_path);verify_sources(scope)
                if not scope['RF_qualified_target_only'] or str(trial/'new_family.json') not in scope['source_hashes']:raise ValueError('membership scope belongs to another trial')
                (out/'membership_scopes').mkdir(exist_ok=True);shutil.copyfile(scope_path,out/'membership_scopes'/scope_path.name)
            target_ids={o for t in p['targets'] for o in t['observation_ids']};inv=load(Path(job['inventory']));label=next(a['scan'] for a in annotations if a['track_id']==tid)
            row=dict(scan=label,inventory_alias=job['label'],track_id=tid,norad=job['annotation']['norad'],points=len(target_ids),qualified=qualified,variant=variant,final_variant=final,source_trial=str(trial))
            for arm,z in v['arms'].items():
                b=control['arms'][arm];before=set(b['proposed_associated_ids']);raw_after=set(z['proposed_associated_ids']);after=set(scope['arms'][arm]['reviewed_associated_ids']) if scope else raw_after;d=target_diagnostic(z)
                if qualified and (after-before!=target_ids or before-after):raise ValueError('unreviewed incidental membership or lost incumbent')
                row[arm+'_before_km']=error(b);row[arm+'_after_km']=error(z)
                positions.append(dict(scan=label,track_id=tid,variant=variant,arm=arm,qualified=qualified,before_km=error(b),after_km=error(z),
                    before_percent=100*len(before)/inv['summary'][0]['total_GLRT'],after_percent=100*len(after)/inv['summary'][0]['total_GLRT'],
                    raw_proposed_points=len(raw_after),reviewed_proposed_points=len(after),unvalidated_extension_points=len(raw_after-after),
                    added_points=len(after-before),lost_points=len(before-after),target_RMS_hz=d['RMS_hz'],control_objective=b['negative_twice_elbo'],addition_objective=z['negative_twice_elbo']))
                if final:plots[tid,arm]=d
            comparisons.append(row)
            for r in audit['rows']:
                for gate,slack in complete_replay_slacks(r).items():
                    if slack<0:failures.append(dict(scan=label,variant=variant,arm=r['arm'],role=r['role'],gate=gate,slack=slack))
            if final:
                byid[tid].update(predictive_inclusion_source=str(trial),predictive_research_inclusion='RF_verified_research_candidate' if qualified else 'inclusion_rejected')
                if scope:byid[tid]['membership_scope_audit']=str(scope_path)
    final=[r for r in comparisons if r['final_variant']];processed={j['track_id'] for j in jobs}
    shifted_pending=load(args.previous/'remaining_shifted_candidates.json') if iteration>1 else frozen['rows']
    if not processed<={r['track_id'] for r in shifted_pending}:raise ValueError('batch repeats a completed shifted assessment')
    shifted_remaining=[r for r in shifted_pending if r['track_id'] not in processed]
    older_remaining=[r for r in load(args.previous/'remaining_role_candidates.json') if r['track_id'] not in processed]
    write(out/'remaining_shifted_candidates.json',shifted_remaining);write(out/'remaining_role_candidates.json',older_remaining)
    for name,rows in [('annotations.csv',annotations),('partitions.csv',partitions),('comparisons.csv',comparisons),('position_trials.csv',positions),('failed_gates.csv',failures),('executions.csv',terminals)]:csvout(name,rows)
    if competition:csvout('candidate_competition.csv',competition)
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        x=np.arange(len(final));ax.barh(x-.16,[r[arm+'_before_km'] for r in final],.32,color='#999',label='Matched control');ax.barh(x+.16,[r[arm+'_after_km'] for r in final],.32,color=['#009e73' if r['qualified'] else '#d55e00' for r in final],label='Addition: green passes RF checks');ax.set(yticks=x,yticklabels=[r['scan'] for r in final],xlabel='Evaluation position error (km)',title=arm);ax.invert_yaxis();ax.legend(fontsize=7)
    save(fig,'position_comparison.png');pages=[]
    for page,start in enumerate(range(0,len(gallery),4),1):
        group=gallery[start:start+4];fig,axes=plt.subplots(len(group),2,figsize=(13,3*len(group)),squeeze=False,layout='constrained')
        for (ax,bx),(job,t,a,label) in zip(axes,group,strict=True):
            ax.plot(t['times'],np.asarray(t['values'])/1000,'.');ax.set(title=label+' / '+t['key'].split('-RF')[0],ylabel='CFO (kHz)')
            tid=job['track_id']
            if (tid,'fitted_c') in plots:
                d=plots[tid,'fitted_c'];ax.plot(d['times_s'],np.asarray(d['predicted_CFO_hz'])/1000,'k-',lw=.7)
                for arm in ('c0','fitted_c'):
                    d=plots[tid,arm];bx.plot(d['times_s'],d['residual_hz'],'.-',lw=.6,label=arm)
                bx.axhline(0,c='k',lw=.5);bx.set_ylabel('Residual (Hz)');bx.legend(fontsize=7)
            else:bx.text(.5,.5,a['status'].replace('_',' '),ha='center',transform=bx.transAxes)
            for axis in (ax,bx):axis.set_xlabel('Scan time (s)');axis.grid(alpha=.2)
        name=f'curves_{page}.png';save(fig,name);pages.append(f'![Curves {page}](figures/{name})')
    if iteration>1:
        csvout('annotation_ledger.csv',ledger)
        summary=dict(batch=iteration,annotations=len(jobs),annotation_states=dict(Counter(r['status'] for r in annotations)),position_trials=len(final),
            qualified_curves=sum(r['qualified'] for r in final),qualified_points=sum(r['points'] for r in final if r['qualified']),
            remaining_shifted=len(shifted_remaining),remaining_older_role=len(older_remaining),capture_modes=cap['modes'],numerical_followups=len(followup),competition_reviews=len(competition),competition_downgrades=sum(r['after_status']!='conditionally_supported_identity' for r in competition),production_changed=False,goal_complete=False)
        write(out/'summary.json',summary);write(out/'sources.json',hashes)
        with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
        (out/'README.md').write_text(f'''# Shifted-origin annotation batch {iteration}

The next **{len(jobs)}** wholly unowned curves from the frozen timestamp-selected queue have complete predictive-only assessments. Outcomes: **{summary['annotation_states']}**. There are **{len(final)} full position trials**, with **{summary['qualified_curves']} RF-qualified curves / {summary['qualified_points']} points** in separate trials. This is not a combined recovery or a production change.

{('All '+str(len(competition))+' initially supported identities were reassessed with a candidate cap of 12 before position inclusion. '+str(summary['competition_downgrades'])+' lost conditional support. The original scores, c arms, aliases and physical partitions replay unchanged; [candidate_competition.csv](candidate_competition.csv) records both outcomes and actual candidate counts. This expands the existing geometry nomination shortlist; it is not an exhaustive all-catalogue likelihood search.') if review else ''}

## Scope, validation and capture provenance

Selection follows native point count and immutable track ID without GPS ranking. The reconciled remaining-candidate file prevents repeating assessments completed in other queues. Every target has three distinct timestamp-selected physical holdout sets, with seeded block origins, 12-second blocks, two-second guards, at least eight training points and four held points. Sets overlap and are not independent replications. No target calibrates the receiver during annotation; the graph and incumbent identities remain conditioning assumptions.

Capture modes are **{cap['modes']}**. Adaptive records use their authoritative source case in tables, retaining historical inventory aliases separately. Direct scanner contracts and digest-verified acquisition manifests establish capture provenance; the fast adapter compatibility label does not. Canonical source identities prevent an adaptive recovery from being reported as a fast-scan result.

{table(annotations,['scan','inventory_alias','capture_mode','points','status','norad','margin'])}

## Matched position inclusion

All supported identities receive matched controls/additions and c=0/fitted-c tests using causal candidates, existing physical priors and the same regional initialization. New-family phase quadrature is 0.025 seconds. The numerical-only retry selector produces **{len(followup)}** follow-ups, with matched Powell controls/additions and unchanged physical gates. Original and follow-up outputs remain in [comparisons.csv](comparisons.csv).

{table(final,['scan','norad','points','qualified','c0_before_km','c0_after_km','fitted_c_before_km','fitted_c_after_km'])}

![Matched position comparison](figures/position_comparison.png)

Qualification requires acceptable residual structure, unchanged incumbent ownership, exact orbital/objective replay and numerical convergence. Qualified membership gains must equal exactly the independently tested target observations. [position_trials.csv](position_trials.csv) reports coverage percentages, point gains, target RMS, objectives and evaluation errors separately. Controls and additions contain different observations; lower raw objectives or more associated points do not prove improved position accuracy. [failed_gates.csv](failed_gates.csv) retains rejected results even if their position errors improve.

Any unscored automatic extension discoveries are excluded from the reviewed association gains using an explicit source-hashed membership audit. The raw membership remains unchanged, and raw versus reviewed counts are recorded separately. Such an audit must prove that incidental points never entered the position objective and that old owners and the tested target are preserved. It does not validate the incidental points themselves.

{chr(10).join(pages)}

## Remaining work

**{len(shifted_remaining)} shifted-origin candidates and {len(older_remaining)} older-role reassessments remain. These queues overlap and must not be added.** The [updated 1,630-row ledger](annotation_ledger.csv) preserves earlier ambiguity, rejections, native-IQ withholdings and joint-family results. Pass the corresponding `remaining_*_candidates.json` file to the next queue invocation using `--remaining-candidates`.

Continue bounded annotation/inclusion batches and independently supported model challenges. Research recoveries require joint consistency and cohort evaluation before promotion. Evaluation GPS never selects satellites or partitions; causal TLEs and physical gates remain unchanged. No new RF or production changes occurred. Source hashes, terminal receipts, physical partition assignments, compact scientific evidence and all figures accompany this report. The complete annotation-and-inclusion objective is unfinished.
''')
        return
    family_results=[]
    for version in (1,2):
        folder=s/f'58528-bidirectional-family-validation-v{version}';terminal=load(folder/'execution.json')
        if terminal['status']!='complete':raise ValueError('family challenge incomplete')
        verify_sources(load(folder/'analysis/protocol.json'));family_results.append(load(folder/'analysis/result.json'))
    old,new=family_results;family_rows=[];track_rows=[];grid=[];times=np.asarray(new['times_s']);off=0;slices={};members=[]
    for e in new['entries']:
        sl=slice(off,off+e['points']);off+=e['points'];slices[e['component']]=sl;members.append(dict(component=e['component'],role=e['role'],points=e['points'],start_s=float(times[sl].min()),end_s=float(times[sl].max())))
    for f,g in zip(new['folds'],old['folds'],strict=True):
        if f['seed']!=g['seed'] or f['split']!=g['split']:raise ValueError('phase comparison changes partitions')
        tr,_=replay_split(times,f['split'])
        for arm,v in f['arms'].items():
            z=v['scores'];before=z['family_to_family'];after=z['combined_to_family'];n=len(before['held_indices'])
            family_rows.append(dict(seed=f['seed'],arm=arm,held_family_points=n,before_RMS_hz=before['rms_hz'],after_RMS_hz=after['rms_hz'],
                held_density_gain=before['negative_twice_log_density']-after['negative_twice_log_density'],density_gain_per_point=(before['negative_twice_log_density']-after['negative_twice_log_density'])/n,
                target_family_only_RMS_hz=z['family_to_target']['rms_hz'],target_bias_only_RMS_hz=v['bias_only_projection']['rms_hz'],target_combined_RMS_hz=z['combined_to_target']['rms_hz']))
            for key,score in z.items():
                prior=g['arms'][arm]['scores'][key]
                if score['held_indices']!=prior['held_indices']:raise ValueError('phase comparison changes physical observations')
                grid.append(dict(seed=f['seed'],arm=arm,score=key,density_change=score['negative_twice_log_density']-prior['negative_twice_log_density'],RMS_change_hz=score['rms_hz']-prior['rms_hz']))
            for t in v['per_incumbent_track']:
                b=t['scores']['family'];a=t['scores']['combined'];res=np.asarray(b['held_residual_hz'])
                track_rows.append(dict(seed=f['seed'],arm=arm,component=t['component'],training_points=int(tr[slices[t['component']]].sum()),held_points=len(res),before_mean_hz=float(res.mean()),before_centered_RMS_hz=float(res.std()),before_RMS_hz=b['rms_hz'],after_RMS_hz=a['rms_hz'],median_prediction_sigma_hz=float(np.median(b['prediction_sigma_hz']))))
    csvout('family_predictions.csv',family_rows);csvout('family_tracks.csv',track_rows);csvout('family_members.csv',members);csvout('phase_grid_sensitivity.csv',grid)
    fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained');xx=np.arange(len(family_rows));labels=[str(r['seed'])+'\n'+r['arm'] for r in family_rows]
    for key,label in [('target_family_only_RMS_hz','Family only'),('target_bias_only_RMS_hz','Target constant bias only'),('target_combined_RMS_hz','Full target conditioning')]:axes[0,0].plot(xx,[r[key] for r in family_rows],'o-',label=label)
    axes[0,0].set_ylabel('Target held RMS (Hz)');axes[0,0].legend(fontsize=7)
    for key,label in [('before_RMS_hz','Without target training'),('after_RMS_hz','With target training')]:axes[0,1].plot(xx,[r[key] for r in family_rows],'o-',label=label)
    axes[0,1].set_ylabel('Family held RMS (Hz)');axes[0,1].legend(fontsize=7)
    axes[1,0].bar(xx,[r['density_gain_per_point'] for r in family_rows]);axes[1,0].axhline(0,c='k',lw=.5);axes[1,0].set_ylabel('Held-family density gain / point\nPositive favors target training')
    for ax in (axes[0,0],axes[0,1],axes[1,0]):ax.set_xticks(xx,labels,fontsize=7);ax.grid(alpha=.2)
    for i,e in enumerate(members):axes[1,1].plot([e['start_s'],e['end_s']],[i,i],'o-',lw=4,color='#d55e00' if e['role']=='target' else '#0072b2')
    axes[1,1].set(yticks=np.arange(len(members)),yticklabels=[e['component'].split('-RF')[0] for e in members],xlabel='Scan time (s)',title='RX1 evidence precedes the RX2 target');axes[1,1].tick_params(axis='y',labelsize=7)
    save(fig,'58528_family_prediction.png')
    byid['24c69d7ca55902f72724'].update(shared_family_prediction_source=str(s/'58528-bidirectional-family-validation-v2/analysis/result.json'),shared_family_prediction_status='unresolved; small held-family density changes; RX and time are confounded')
    csvout('annotation_ledger.csv',ledger)
    summary=dict(annotations=len(jobs),annotation_states=dict(Counter(r['status'] for r in annotations)),position_trials=len(final),qualified_curves=sum(r['qualified'] for r in final),qualified_points=sum(r['points'] for r in final if r['qualified']),remaining_shifted=len(shifted_remaining),remaining_older_role=len(older_remaining),capture_modes=cap['modes'],maximum_density_grid_change=max(abs(r['density_change']) for r in grid),maximum_RMS_grid_change_hz=max(abs(r['RMS_change_hz']) for r in grid),production_changed=False,goal_complete=False)
    write(out/'summary.json',summary);write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    (out/'README.md').write_text(f'''# First shifted-origin recovery batch and 58528 cross-track prediction

The timestamp-only validation change now yields **{summary['qualified_curves']} RF-qualified research recoveries / {summary['qualified_points']} points** in separate position trials. All sixteen curves previously lacked adequate fixed-origin partitions. Seven now have supported identity hypotheses; four remain ambiguous, three unstable and two fail absolute predictive agreement. No label is forced into localization.

## Frozen scope and acquisition provenance

The previous report identified 419 wholly unowned curves marked insufficient partitions in its input ledger. The separate 58528 trial assessed one, leaving a frozen queue of **418**. This batch takes the largest **16** by native point count, ties resolved by immutable track ID, without ranking by GPS error. All receivers and channels use the same random scanwide split. Seeded origins change block alignment; 12-second blocks, two-second guards, eight training points, four held points and three distinct physical holdout sets are retained. The sets overlap and are not independent replications. The annotation target does not calibrate the receiver. Existing receipts and default behavior are unchanged.

There are **15 verified fast recordings and one adaptive recording**. The historical inventory alias **DS24-0037 actually refers to DS25-0018**, an adaptive scan at 10 MS/s. Its recovery is not a DS24 fast-scan improvement. We preserve the immutable alias alongside the acquisition source in all result tables. Provenance comes from direct scanner contracts or digest-verified acquisition manifests, not the fast adapter's compatibility capture-mode label.

{table(annotations,['scan','inventory_alias','capture_mode','points','status','norad','margin'])}

## Matched inclusion outcomes

Every supported identity receives a full control/addition trial with matched c=0 and fitted-c arms, causal candidates, priors and search budgets. Qualification requires residual checks, preserved incumbent ownership, exact orbital/objective replay, numerical convergence and phase resolution. The numerical-only retry selector finds no eligible retries in this batch. All original outcomes remain, including position regressions. New-family phase quadrature uses 0.025-second spacing.

{table(final,['scan','norad','points','qualified','c0_before_km','c0_after_km','fitted_c_before_km','fitted_c_after_km'])}

![Matched position comparisons](figures/position_comparison.png)

The two passing cases recover **38 adaptive-scan points for 67799** and **36 fast-scan points for 56498**. Fitted-c error improves **2.493→1.914 km** and **1.053→0.977 km**, respectively. These are individual research trials, not a combined solution, a production change, or evidence that the 500 m goal is met. The complete [position table](position_trials.csv) separates GLRT coverage, RMS, numerical objective and position error. Control and addition use different observation sets, so their raw objective difference does not establish improved localization. Rejected targets and their [failed gates](failed_gates.csv) remain visible below.

GLRT coverage rises **74.41%→76.55%** for DS25-0018 and **68.09%→69.11%** for AUTO-ff2429e3 in both c arms. These gains contain exactly the independently tested target points, with no incidental extension discoveries included.

AUTO-c9b43371 illustrates why evaluation error cannot authorize an association: adding its 36-point RX1 CH8 / 67618 curve moves fitted-c error **604→438 m** and c=0 error **663→492 m**, but both arms fail target slope, quadratic and step checks. It remains rejected despite meeting the numerical position-error goal in this diagnostic trial.

{chr(10).join(pages)}

## 58528: test the other tracks, not just the target

The rejected 28-point RX2 CH4 target retains a consistent causal identity hypothesis but fails its full-fit residual slope gate. We now exclude the entire 58528 family from receiver/position calibration and fit the remaining families on each randomized training partition from the regional box center. All predictive-only rows also remain outside calibration. One shared phase/orbit distribution, one receiver covariance and the existing per-track constant-bias priors connect the family. Target training may condition that predictive distribution; it cannot refit the independently trained receiver calibration.

{table(members,['component','role','points','start_s','end_s'])}

{table([r for r in family_rows if r['arm']=='fitted_c'],['seed','held_family_points','before_RMS_hz','after_RMS_hz','held_density_gain','target_combined_RMS_hz'])}

![Bidirectional prediction and temporal support](figures/58528_family_prediction.png)

Target training changes the held-family density only modestly. Both c arms show the same negative signs, but the three folds overlap and these scores are not calibrated probabilities. Family RMS sometimes improves while joint density worsens slightly because density also accounts for predictive covariance. This is insufficient evidence to accept a correction or declare the identity wrong.

All incumbent family tracks are on RX1; the target is on RX2 and begins after the last RX1 family observation. Receiver identity and time are therefore confounded in this family comparison. A relative receiver drift and an orbital/position extrapolation error cannot be isolated here. Some incumbent tracks have only one or two training points in a partition, leaving weak constant-bias information; raw held RMS is not purely shape error. [Per-track metrics](family_tracks.csv) report training support, residual means, centered RMS and predictive uncertainty.

Halving phase spacing from 0.1 to 0.05 seconds preserves all partitions. Maximum score change is **{summary['maximum_density_grid_change']:.4f}** in −2 log density, and maximum RMS change is **{summary['maximum_RMS_grid_change_hz']:.3f} Hz** across the recorded prediction modes. Both runs have terminal receipts and unchanged acceptance. The target remains withheld; independent RX2 evidence from other satellites is needed before claiming a receiver correction.

## Remaining work and reproducibility

**{len(shifted_remaining)} shifted-origin candidates remain**, and **{len(older_remaining)} remain in the older-role queue**. Twelve of this batch's cases were also in that older queue, so the queues overlap and must not be added. The updated 1,630-row ledger preserves prior rejected, ambiguous, native-IQ-withheld and jointly verified results. Queue execution now accepts a hashed `--remaining-candidates` file so work completed through another queue is not repeated. For this queue, pass [remaining_shifted_candidates.json](remaining_shifted_candidates.json); for the older queue, pass [remaining_role_candidates.json](remaining_role_candidates.json).

Continue bounded batches and independently supported receiver/orbit challenges. Keep successful recoveries separate until they pass joint consistency and cohort evaluation. The matched regional search and causal TLE policy remain; GPS is used solely for reported position errors. No new RF was collected. Source hashes, terminal receipts, full point assignments, raw compact evidence and figures accompany this report. The full annotation-and-inclusion objective remains incomplete.

Nineteen focused tests pass, covering queue claims and cross-queue exclusions, predictive-only routing, unchanged legacy splits, shifted physical holdouts, timestamp integrity, guards, minimum support, and Gaussian grouped-prediction behavior. Report generation rechecks source digests, physical holdouts, exact replay qualification and the complete target membership scope before exporting results.
''')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('study','previous','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--batch',type=int,default=1)
    p.add_argument('--membership-scopes',type=Path)
    p.add_argument('--competition-review',type=Path)
    run(p.parse_args())
