"""Publish step-witness validation, bounded inventory progress and inclusion."""
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
from report_inactive_fragment_transfer import replay_slacks


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();hashes={};evidence={};executions=[]
    def load(p):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p);evidence[str(p)]=compact_replays(compact_evidence(r));return r
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger};batch=[];q=s/'systematic-annotation-v1'
    for number in (35,36):
        attempt=q/f'attempt-{number}';load(attempt/'protocol.json');load(attempt/'execution.json')
        for job in load(attempt/'selected.json'):
            tid=job['track_id'];term=load(attempt/(tid+'-terminal.json'));executions.append(dict(group=f'annotation{number}',**term))
            if term['status']!='complete':
                byid[tid].update(state='execution_'+term['status'],annotation_execution_source=str(attempt/(tid+'-terminal.json')))
                batch.append(dict(attempt=number,scan=job['label'],track_id=tid,status='execution_'+term['status'],norad=None));continue
            path=q/tid/'result.json';r=load(path);load(path.parent/'protocol.json');a=r['annotation'];fragment=r.get('inactive_graph_fragment',False)
            if fragment:byid[tid].update(inactive_fragment_annotation_source=str(path),inactive_fragment_state=a['status'],inactive_fragment_norad=a['norad'])
            else:byid[tid].update(predictive_recheck_source=str(path),predictive_recheck_state=a['status'],predictive_recheck_minimum_margin=a.get('minimum_margin'),
                state=a['status'],norad=a['norad'],annotation_likelihood_role='predictive_only; first assessment')
            batch.append(dict(attempt=number,scan=job['label'],track_id=tid,points=job['points'],fragment=fragment,status=a['status'],norad=a['norad']))
    csvout('annotation_batches.csv',batch)
    root=s/'predictive-queue35-inclusion-v1';load(root/'protocol.json');cases=load(root/'execution.json');trials=[];comparison=[];failures=[];qualified_records=[]
    for case in cases:
        assert case['status']=='complete';job=case['job'];tid=job['track_id'];folder=root/tid;f=folder/'trial';shared=case['shared_family']
        for stage in case['stages']:executions.append(dict(group='position',scan=job['label'],**load(folder/(stage['stage']+'-terminal.json'))))
        pr=load(f/'protocol.json');c=load(f/'control.json');a=load(f/('target_0.json' if shared else 'new_family.json'));audit=load(f/'exact_owner_replay.json')
        inv=load(Path(job['inventory']));den=inv['summary'][0]['total_GLRT'];target=set(o for t in pr['targets'] for o in t['observation_ids'])
        qualified=c['paired_valid'] and a['paired_valid'] and audit['all_verified']
        if qualified:qualified_records.append((job,c,a,den))
        row=dict(scan=job['label'],norad=job['annotation']['norad'],points=len(target),RF_qualified=qualified)
        for arm in ('c0','fitted_c'):row.update({arm+'_control_km':error(c['arms'][arm]),arm+'_addition_km':error(a['arms'][arm])})
        comparison.append(row)
        for role,pair in [('control',c),('target_0' if shared else 'new_family',a)]:
            for arm,v in pair['arms'].items():
                rr=next(r for r in audit['rows'] if (r['role'],r['arm'])==(role,arm));slacks=replay_slacks(rr)
                old=set(c['arms'][arm]['proposed_associated_ids']);ids=set(v['proposed_associated_ids']);new=ids-old;changes=rr['incumbent_ownership_changes']
                trials.append(dict(scan=job['label'],role=role,arm=arm,error_km=error(v),proposed_points=len(ids),proposed_percent=100*len(ids)/den,
                    added_target=len(new&target),incidental_added=len(new-target),lost=len(old-ids),paired_valid=pair['paired_valid'],exact_verified=rr['verified'],RF_qualified=qualified,
                    minimum_exact_slack=min(slacks.values()),missing_owners=sum(x['after'] is None for x in changes),reassigned_owners=sum(x['after'] is not None for x in changes),
                    objective=v['negative_twice_elbo'],phase_gap_s=v['final_phase_change_s'],quadrature_pass=v.get('phase_resolution_audit',{}).get('local_agreement')))
                for gate,slack in slacks.items():
                    if slack<0:failures.append(dict(scan=job['label'],role=role,arm=arm,gate=gate,slack=slack))
                for diag in v.get('family',{}).get('diagnostics',[]):
                    n=diag['noise'];ratios=dict(mean=n['mean_z']/3,slope=n['slope_z']/3,quadratic=n['quadratic_bic_gain']/10,step=n['maximum_step_z']/4,lag1=abs(n['lag1_acf'])/(4/np.sqrt(len(diag['times_s']))))
                    for k,ratio in ratios.items():
                        if ratio>1:failures.append(dict(scan=job['label'],role=role,arm=arm,gate=diag['component']+'/target/'+k,slack=1-ratio))
        byid[tid].update(predictive_inclusion_source=str(f),predictive_research_inclusion='RF_verified_candidate; not production promoted' if qualified else 'rejected; complete trial and replay retained')
    csvout('position_trials.csv',trials);csvout('comparison.csv',comparison);csvout('failed_gates.csv',failures)
    root=s/'inactive-fragment-step-witness-v1';load(root/'protocol.json');load(root/'execution.json');step=load(root/'step_results.json');witnesses=[]
    for j in load(root/'protocol.json')['jobs']:
        load(root/(j['track_id']+'.json'));executions.append(dict(group='witness',**load(root/(j['track_id']+'-terminal.json'))))
    for r in step['results']:
        for m in r['models']:
            b=m['best'];after=m.get('target_after_counterfactual',{})
            witnesses.append(dict(scan=r['job']['label'],arm=r['arm'],scope=m['scope'],scaling=m['scaling'],supported_exploratory=m['supported_exploratory_proposal'],
                time_s=None if not b else b['time_s'],amplitude_hz=None if not b else b['predicted_target_amplitude_hz'],search_adjusted_gain=None if not b else b['search_adjusted_gain'],
                distinct_families=None if not b else b['distinct_families'],same_sign_two_sigma_families=None if not b else b['same_sign_two_sigma_families'],
                target_step_before=r['before']['noise']['maximum_step_z'],target_step_after=after.get('noise',{}).get('maximum_step_z'),
                counterfactual_target_pass=after.get('noise',{}).get('noise_screen_pass'),acceptance_authorized=False))
    csvout('witness_models.csv',witnesses)
    root=s/'inactive-fragment-step-validation-v1';load(root/'protocol.json');term=load(root/'execution.json');assert term['status']=='complete';executions.append(dict(group='validation',**term))
    load(root/'trial/protocol.json');validation=load(root/'trial/result.json');folds=[]
    for f in validation['folds']:
        load(root/'trial'/(str(f['seed'])+'.json'))
        for arm in ('c0','fitted_c'):
            a=f['models']['original'][arm];b=f['models']['training_selected_step'][arm];times=np.array(b['target_held_times_s'])
            folds.append(dict(seed=f['seed'],arm=arm,event_selected=bool(f['events']),event_time_s=f['events'][0]['time_s'] if f['events'] else None,
                target_held_start_s=float(times.min()),target_held_end_s=float(times.max()),held_target_points=int(len(times)),held_after_full_diagnostic_65s=int((times>=65).sum()),
                target_score_delta=b['target_score']['negative_twice_log_density']-a['target_score']['negative_twice_log_density'],
                target_RMS_before_hz=a['target_score']['rms_hz'],target_RMS_after_hz=b['target_score']['rms_hz'],
                existing_score_delta=b['existing_score']['negative_twice_log_density']-a['existing_score']['negative_twice_log_density'],phase_gap_s=b['final_phase_change_s']))
    csvout('random_block_validation.csv',folds)
    # Keep a concrete list of still-unassessed records, including earlier claims.
    claimed={r['track_id']:p for p in sorted(q.glob('attempt-*'),key=lambda p:int(p.name.split('-')[1])) for r in read(p/'selected.json')}
    queue={r['track_id']:r for r in read(q/'protocol.json')['rows']};remaining=[]
    for r in ledger:
        if r.get('annotation_source') or r.get('predictive_recheck_source') or r.get('inactive_fragment_annotation_source'):continue
        tid=r['track_id'];attempt=claimed.get(tid);terminal=attempt/(tid+'-terminal.json') if attempt else None
        remaining.append(dict(track_id=tid,label=r['label'],state=r['state'],queue_state=queue[tid]['state'],
            claim=None if attempt is None else attempt.name,terminal_status=read(terminal)['status'] if terminal and terminal.exists() else None,
            output_exists=(q/tid).exists(),result_exists=(q/tid/'result.json').exists()))
    csvout('remaining_assessments.csv',remaining);csvout('annotation_ledger.csv',ledger);csvout('executions.csv',executions)
    fig,axs=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    selected=[r for r in step['results'] if r['arm']=='c0']
    for col,r in enumerate(selected):
        model=next(m for m in r['models'] if m['scope']=='same_receiver' and m['scaling']=='hz');t=r['target']['times_s']
        axs[0,col].plot(t,r['before']['residual_hz'],'o-',ms=3,label='Original target residual')
        axs[0,col].plot(t,model['target_after_counterfactual']['residual_hz'],'o-',ms=3,label='Counterfactual witness correction')
        axs[0,col].axvline(model['best']['time_s'],c='k',ls='--');axs[0,col].set(title=r['job']['label'],xlabel='Time (s)',ylabel='Profile residual (Hz)');axs[0,col].legend(fontsize=8)
        for scaling,offset in [('hz',-.16),('fractional',.16)]:
            mm=[next(m for m in r['models'] if m['scope']==scope and m['scaling']==scaling) for scope in ('same_receiver','same_receiver_band','other_receiver')]
            values=[m['best']['search_adjusted_gain'] if m['best'] else np.nan for m in mm]
            axs[1,col].bar(np.arange(3)+offset,values,.3,label=scaling)
        axs[1,col].axhline(0,c='k',ls='--');axs[1,col].set(xticks=np.arange(3),xticklabels=['same RX','same RX/band','other RX'],ylabel='Exploratory search-adjusted gain');axs[1,col].legend()
        for ax in axs[:,col]:ax.grid(alpha=.2)
    fig.suptitle('A correction can improve residuals without enough evidence to use it\nFrozen control fits; target family excluded from witness votes; missing bars mean insufficient spanning families')
    save(fig,'step_witnesses.png')
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained');seeds=[f['seed'] for f in validation['folds']]
    for ax,key in zip(axs,('target_score_delta','existing_score_delta'),strict=True):
        for arm,offset in [('c0',-.16),('fitted_c',.16)]:
            rr=[next(r for r in folds if r['seed']==seed and r['arm']==arm) for seed in seeds]
            ax.bar(np.arange(3)+offset,[r[key] for r in rr],.3,label=arm)
        ax.axhline(0,c='k',lw=.6);ax.set(xticks=np.arange(3),xticklabels=[str(seed) for seed in seeds],ylabel='Held negative twice log-density change',title='Target fragment' if key.startswith('target') else 'Other families');ax.legend();ax.grid(axis='y',alpha=.2)
    fig.suptitle('Training-only event discovery: negative changes favor the step\nOnly the first partition selects an event; it holds out target points BEFORE the step')
    save(fig,'random_block_validation.png')
    fig,axs=plt.subplots(1,2,figsize=(14,6),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        for i,r in enumerate(comparison):
            ax.scatter(r[arm+'_control_km'],r[arm+'_addition_km'],c='#009e73' if r['RF_qualified'] else '#d55e00',s=45)
            ax.annotate(r['scan'].replace('AUTO-',''),(r[arm+'_control_km'],r[arm+'_addition_km']),fontsize=6,xytext=(3,3),textcoords='offset points')
        limit=max(max(r[arm+'_control_km'],r[arm+'_addition_km']) for r in comparison)*1.05
        ax.plot([0,limit],[0,limit],'k--',lw=.8);ax.set(xlabel='Matched control error (km)',ylabel='Proposed addition error (km)',title=arm);ax.grid(alpha=.2)
    fig.suptitle('All 12 supported identities tested in position fits\nGreen: passes paired physical/numerical/ownership checks; orange: rejected, even if error improves')
    save(fig,'position_transfer.png')
    if len(qualified_records)==1:
        job,c,a,den=qualified_records[0];fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
        for arm,color in [('c0','#0072b2'),('fitted_c','#d55e00')]:
            d=a['arms'][arm]['family']['diagnostics'][0];t=np.array(d['times_s'])
            if arm=='c0':axs[0].scatter(t,np.array(d['CFO_hz'])/1000,c='k',s=12,label='Graph GLRT')
            axs[0].plot(t,(np.array(d['prediction_CFO_hz'])+d['profile_bias_hz'])/1000,c=color,label=arm+' satellite + profiled offset')
            axs[1].plot(t,np.array(d['raw_residual_hz'])-d['profile_bias_hz'],'.-',c=color,label=arm)
        axs[0].set(xlabel='Time (s)',ylabel='CFO (kHz)');axs[1].set(xlabel='Time (s)',ylabel='Profile residual (Hz)');axs[1].axhline(0,c='k',lw=.6)
        for ax in axs:ax.grid(alpha=.2);ax.legend(fontsize=8)
        fig.suptitle(job['label']+' / NORAD '+str(job['annotation']['norad'])+' / 27-point research recovery candidate')
        save(fig,'qualified_curve.png')
    summary=dict(batch_results=dict(Counter(r['status'] for r in batch)),new_annotation_attempts=len(batch),
        completed_assessments=len(ledger)-len(remaining),inventory_total=len(ledger),remaining=len(remaining),
        remaining_claimed=sum(r['claim'] is not None for r in remaining),position_cases=len(comparison),qualified_cases=sum(r['RF_qualified'] for r in comparison),
        qualified_target_points=sum(r['points'] for r in comparison if r['RF_qualified']),production_changed=False)
    write(out/'summary.json',summary)
    for name in ('run_annotation_inventory.py','independent_step_witness.py','analyze_inactive_step_witnesses.py','validate_inactive_step_witness.py','diagnose_graph_residual_witnesses.py','report_inactive_step_validation.py'):
        p=Path(__file__).with_name(name);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    text=f'''# Cross-family step evidence, random-block validation and inventory transfer

This iteration tests whether the two previously rejected partial curves have independent receiver-step witnesses, advances two bounded annotation batches, and runs every supported identity from the first batch through matched position inclusion. **One 27-point curve qualifies as a research recovery candidate; no production policy changes.** Other apparent improvements remain rejected when physical, numerical or ownership checks fail.

## Receiver-step evidence is uneven

Residuals are reconstructed at the saved **no-addition control position**. The unused fragment never enters that fit. Receiver-step discovery excludes every curve assigned to the target's satellite family. We examine a timestamp-defined 1 s grid across the target span, using witnesses within the span plus 10 s on each side. Each witness must have at least four points on either side of the proposed event. A constant and linear trend are removed per witness so a smooth rate discrepancy cannot automatically vote for a jump. Multiple channels of one family receive one averaged-information vote. At least two families are required.

The exploratory model uses fixed 150 Hz measurement noise and a 150 Hz Gaussian amplitude prior. We retain all three scopes (same receiver, same receiver/band, other receiver) and additive-Hz/fractional-frequency scalings. A proposal needs positive gain after a `2 log(grid points × 6)` search penalty and two same-sign family amplitudes exceeding two posterior standard deviations. This is a deliberately explicit **diagnostic rule, not calibrated event confidence**. The residuals share full-fit parameters, so different-family votes alone do not establish independent held-out prediction. Other-receiver results are controls, not permission to transfer a correction between receivers.

![Step evidence and counterfactual residuals](figures/step_witnesses.png)

For AUTO-5cf2a9a9 / 64004, the target step maximum is between **65.06 and 66.13 s**, separating 45 earlier points from five later points. Other RX1 curves belonging to **59213 and 59222** favor an additive-Hz step at **65 s**, about **+274 Hz**. Their family-specific amplitudes are roughly +210 and +223 Hz after prior shrinkage. The aggregate exploratory search-adjusted gain is only **+0.59 / +0.62** in c=0 / fitted-c. Applying that estimate counterfactually reduces the target step statistic from **4.25 / 4.28** to **2.78 / 2.73**, with the unchanged limit of 4, and all target noise gates pass. Fractional scaling falls below the discovery threshold; same-band and other-receiver controls lack two spanning families. This is a plausible receiver hypothesis, not a recovered association.

For AUTO-74824694 / 69450, the target step maximum lies between **169.90 and 171.31 s**. A hypothetical roughly −66 Hz receiver step near 170 s would also make the target pass, but its witness gain is about **−11**, with no two-sigma family votes. That correction is unsupported. This distinction is important: finding a correction that improves the target is much easier than establishing that it belongs in the receiver model. [All 24 arm/scope/scaling outcomes](witness_models.csv) remain visible.

## Training-only discovery does not yet validate the changed interval

For the one scan with a positive exploratory proposal, we repeat discovery inside each of its three existing random scanwide **12 s block / 2 s guard** partitions. The target's entire satellite family is excluded from calibration, all predictive incumbents are excluded from training, noise is fixed at 150 Hz, and the event time is reselected from c=0 training residuals only. The same event candidate, prior, observations and search budget are then used in both c arms. If training does not support an event, the candidate policy falls back to the original model. Target training observations can condition the satellite predictive mixture, but cannot calibrate the receiver or event.

{table(folds,['seed','arm','event_selected','event_time_s','target_held_start_s','target_held_end_s','target_RMS_before_hz','target_RMS_after_hz','target_score_delta','existing_score_delta'])}

![Random block validation](figures/random_block_validation.png)

Only seed **94721** selects the 65 s event. It improves target held RMS from **375 → 130 Hz** (c=0) and **364 → 120 Hz** (fitted-c), and improves the held predictive score for other families too. However, its held target points are **36.27–46.93 s, before the event**. The partition withholding **60.09–68.62 s**, which contains the changed target interval, does **not** support an event from training. The remaining partition also falls below the discovery threshold. The neutral score changes in those folds are explicit no-event fallbacks, not successful step predictions. Thus this experiment does not yet independently validate prediction of the changed interval, integrate event-time uncertainty, or justify a position update using this correction. No step-based position trial or coverage gain is claimed here.

## Every supported identity in batch 35 reaches position evaluation

The 12 candidates are selected by predictive identity support, not by GPS error. All controls/additions start at the same 25 × 25 km regional-box center (37.906, −122.545), preserve causal TLEs and physical priors, and run c=0 and fitted-c with matched observation/candidate sets and budgets. GPS (37.849061591561885, −122.48574968092912) is read only for this report's error calculation. Existing-family candidates retain shared conditioning; absent/uncalibrated families use causal phase mixtures with orbital and receiver covariance. Each stage has a 600 s cap; four workers process the 12 independent cases. New-family fits use five phase rounds with 48 iterations / 240 objective calls per round; shared-family fits retain five rounds / 48 steps.

{table(comparison,['scan','norad','points','c0_control_km','c0_addition_km','fitted_c_control_km','fitted_c_addition_km','RF_qualified'])}

![Position transfer](figures/position_transfer.png)

**AUTO-ceb24498 / 63388** is the sole qualified research candidate: **27 added points**, no lost observations, no changed incumbent owners, and both physical/numerical qualification and independent exact-orbit replay pass. Error changes **2.145 → 2.069 km** (c=0) and **2.100 → 2.050 km** (fitted-c). Target RMS is about **143 / 142 Hz**; target noise gates pass. The minimum incumbent exact slack is about **0.0147 / 0.0148**, so this is a verified endpoint under the current gates, not a broad robustness guarantee. Exact replay substitutes one incumbent family at a time rather than refitting all orbits simultaneously.

![Qualified curve](figures/qualified_curve.png)

The other 11 proposals remain rejected, even where GPS error appears much lower. The raw proposed coverage must not be counted as accepted coverage. [Every arm/role](position_trials.csv), [failed gates](failed_gates.csv), objective scores, quadrature status and owner omissions/reassignments are retained. Scores with different observation sets are not used as proof of improved localization. This small development cohort is not a full-dataset improvement or an ALGO promotion.

## Inventory progress and reproducibility

Attempts 35 and 36 assess **{summary['new_annotation_attempts']}** additional queued curves. Outcomes: **{summary['batch_results']}**. Partial curves now route automatically to their unused observations; whole curves retain the predictive-member route. Timestamp-only partition selection and exclusive attempt claims are preserved. Batch-36 supported identities have not yet received position trials in this report.

The [ledger](annotation_ledger.csv) contains **{summary['completed_assessments']} / {summary['inventory_total']}** curves assessed in at least one likelihood role, including ambiguity, prediction mismatch and insufficient-partition outcomes. These are not accepted associations. [The remaining {summary['remaining']} records](remaining_assessments.csv) include **{summary['remaining_claimed']} previously claimed cases**, which must be diagnosed rather than silently restarted. Completing the pending queue alone will therefore not prove inventory completion.

The active goal remains incomplete. Next work is to process the remaining inventory and supported candidates, and investigate event-time uncertainty or independent same-scan evidence for the 65 s change. The 170 s correction should not be fitted merely because it makes the target look better. [Execution receipts](executions.csv), [source hashes](sources.json), [compressed scientific evidence](evidence.json.gz), and [annotation outcomes](annotation_batches.csv) preserve the experiments. **50 targeted tests pass.** New tests verify that affine trends cannot vote for a step, duplicated channels cannot manufacture independent family support, target-family/receiver exclusions hold, and partial queue routing preserves its predictive role; the suite also covers existing receiver-event propagation, family exclusion, ownership, phase convergence and covariance handling. No RF collection, future TLE, production change or gate relaxation is introduced.
'''
    (out/'README.md').write_text(text);print(summary,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):parser.add_argument('--'+name,type=Path,required=True)
    run(parser.parse_args())
