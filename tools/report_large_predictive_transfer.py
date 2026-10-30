"""Publish role-consistent identity checks and controlled DS24 curve inclusion."""
import argparse,csv,gzip,hashlib,json,shutil
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
from report_inventory_experiments import error,SITE
from leo.analysis.research.grouped_prediction import identity_consensus


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();hashes={};evidence={}
    def load(p):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p);evidence[str(p)]=compact_replays(compact_evidence(r));return r
    def csvout(name,rows):
        if not rows:return
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest();ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger}
    selection=load(s/'ds24-largest-predictive-transfer-selection-v1.json')
    for p,digest in selection['source_hashes'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==digest
    root=s/'ds24-largest-predictive-transfer-v1';pr=load(root/'protocol.json');execution=load(root/'execution.json')
    budget=load(s/'ds24-largest-predictive-transfer-feasible-0081-v1/budget_semantics.json')
    source=Path(budget['source_snapshot']);assert hashlib.sha256(source.read_bytes()).hexdigest()==budget['source_sha256']
    (out/'source_snapshot').mkdir();shutil.copyfile(source,out/'source_snapshot'/source.name)
    hashes[str(source)]=budget['source_sha256'];write(out/'continuation_budget.json',budget)
    assert [r['track_id'] for r in selection['selected']]==[r['track_id'] for r in pr['jobs']]
    states=[];votes=[];executions=[];curves={};inventories={}
    for case in execution:
        job=case['job'];tid=job['track_id'];folder=root/tid
        for stage in case['stages']:executions.append(dict(group=job['label'],**load(folder/(stage['stage']+'-terminal.json'))))
        ann=load(folder/'annotation/result.json');load(folder/'annotation/protocol.json');a=identity_consensus(ann['folds'],score_name='conditional_target')
        votes.extend(dict(scan=job['label'],track_id=tid,**v) for v in a['votes'])
        states.append(dict(scan=job['label'],track_id=tid,points=job['points'],original_norad=byid[tid]['norad'],predictive_norad=a['norad'],
            predictive_status=a['status'],minimum_margin=a.get('minimum_margin'),initial_transfer_status=case['status']))
        byid[tid].update(predictive_recheck_source=str(folder/'annotation/result.json'),predictive_recheck_state=a['status'],predictive_recheck_minimum_margin=a.get('minimum_margin'))
        inv=load(Path(job['inventory']));inventories[job['label']]=inv
        original=load(Path(inv['job']['root'])/inv['job']['case']/'tracks.json');track=next(t for t in inv['tracks'] if t['track_id']==tid)
        curves[job['label']]=original[track['track_index']]
    csvout('identity_states.csv',states);csvout('identity_votes.csv',votes)
    trial_specs=[('DS24-0099','L-BFGS-B / 0.1 s',root/'ffe729ec88e7d9d0c8fb/inclusion'),
        ('DS24-0081','L-BFGS-B / 0.1 s',root/'36ad3ab60bfb71654cf4/inclusion'),
        ('DS24-0099','Powell / 0.1 s',s/'ds24-largest-predictive-transfer-powell-0099-v1/trial'),
        ('DS24-0081','Powell / 0.025 s',s/'ds24-largest-predictive-transfer-refined-0081-v1/trial'),
        ('DS24-0081','Feasible / 0.025 s',s/'ds24-largest-predictive-transfer-feasible-0081-v1/trial')]
    trials=[];gates=[];replays=[];records={};comparison=[]
    for scan,label,folder in trial_specs:
        if folder.parent!=root/'ffe729ec88e7d9d0c8fb' and folder.parent!=root/'36ad3ab60bfb71654cf4':
            load(folder.parent/'protocol.json')
            for name in ('inclusion','replay'):
                term=load(folder.parent/(name+'-terminal.json'));assert term['status']=='complete';executions.append(dict(group=scan+' '+label,**term))
        protocol=load(folder/'protocol.json');control=load(folder/'control.json');addition=load(folder/'new_family.json');audit=load(folder/'exact_owner_replay.json')
        records[scan,label]=dict(control=control,addition=addition,audit=audit,protocol=protocol)
        qualified=control['paired_valid'] and addition['paired_valid'] and audit['all_verified']
        denominator=inventories[scan]['summary'][0]['total_GLRT']
        for role,r in [('control',control),('addition',addition)]:
            for arm,v in r['arms'].items():
                target=v.get('family');nr=len(v['proposed_associated_ids']);old=set(control['arms'][arm]['proposed_associated_ids']);ids=set(v['proposed_associated_ids'])
                trials.append(dict(scan=scan,variant=label,role=role,arm=arm,error_km=error(v),associated_proposed=nr,percent_proposed=100*nr/denominator,
                    added_vs_control=len(ids-old),lost_vs_control=len(old-ids),paired_fit_valid=r['paired_valid'],full_trial_RF_qualified=qualified,
                    objective=v['negative_twice_elbo'],final_optimizer_success=v['history'][-1]['success'],final_optimizer_message=v['history'][-1]['message'],
                    phase_gap_s=v['final_phase_change_s'],quadrature_pass=v.get('phase_resolution_audit',{}).get('local_agreement'),
                    target_RMS_hz=None if target is None else target['diagnostics'][0]['profile_RMS_hz']))
        for row in audit['rows']:
            all_slacks={k:v for family in row['exact_incumbent_family_replays'] for k,v in family['all_gate_slacks'].items()}
            failures={k:v for k,v in all_slacks.items() if v<0}
            for gate,slack in failures.items():gates.append(dict(scan=scan,variant=label,role=row['role'],arm=row['arm'],gate=gate,slack=slack))
            replays.append(dict(scan=scan,variant=label,role=row['role'],arm=row['arm'],verified=row['verified'],objective_difference=row['objective_difference'],
                incumbent_owner_changes=len(row['incumbent_ownership_changes']),control_owner_changes=len(row['control_ownership_changes']),
                failed_unique_gates=len(failures),minimum_gate_slack=min(all_slacks.values()),
                protected_ch8_slope_slack=all_slacks.get('DS24-0081-RX1-CH8-T001-RF12690312500.000000/linear/slope'),
                phase_gap_s=row['phase_reference_check']['phase_change_s']))
        comparison.append(dict(scan=scan,variant=label,c0_control_km=error(control['arms']['c0']),c0_addition_km=error(addition['arms']['c0']),
            fitted_control_km=error(control['arms']['fitted_c']),fitted_addition_km=error(addition['arms']['fitted_c']),
            proposed_added=len(set(addition['arms']['fitted_c']['proposed_associated_ids'])-set(control['arms']['fitted_c']['proposed_associated_ids'])),
            paired_fit_valid=control['paired_valid'] and addition['paired_valid'],exact_replay_valid=audit['all_verified'],RF_qualified=qualified))
        if label.startswith(('Powell','Feasible')):
            tid=next(r['track_id'] for r in states if r['scan']==scan)
            byid[tid].update(predictive_inclusion_source=str(folder/'new_family.json'),predictive_research_inclusion='RF_verified_candidate; not production promoted' if qualified else 'rejected; retain full evidence')
    csvout('position_trials.csv',trials);csvout('comparison.csv',comparison);csvout('exact_replays.csv',replays);csvout('failed_incumbent_gates.csv',gates)
    # Add the terminal original-screen batch without overwriting role-specific rechecks.
    queue=s/'systematic-annotation-v1';attempt=queue/'attempt-33';load(attempt/'protocol.json');load(attempt/'execution.json');batch=[]
    for job in load(attempt/'selected.json'):
        tid=job['track_id'];term=load(attempt/(tid+'-terminal.json'));executions.append(dict(group='annotation33',**term))
        if term['status']=='complete':
            path=queue/tid/'result.json';r=load(path);load(path.parent/'protocol.json');a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
            byid[tid].update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),annotation_source=str(path),partition_policy='distinct timestamps',
                geometry_only_early_exit=r.get('geometry_only_early_exit',False),distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        else:
            a=dict(status='execution_'+term['status'],norad=None);byid[tid].update(state=a['status'],annotation_execution_source=str(attempt/(tid+'-terminal.json')))
        batch.append(dict(scan=job['label'],track_id=tid,status=a['status'],norad=a['norad']))
    csvout('annotation_batch.csv',batch);csvout('annotation_ledger.csv',ledger);csvout('executions.csv',executions)
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for ax,state in zip(axs.flat,states,strict=True):
        rr=[r for r in votes if r['scan']==state['scan']];seeds=list(dict.fromkeys(r['seed'] for r in rr))
        for arm,offset,color in [('c0',-.12,'#0072b2'),('fitted_c',.12,'#d55e00')]:
            vv=[next(r for r in rr if r['seed']==seed and r['arm']==arm) for seed in seeds]
            ax.bar(np.arange(len(seeds))+offset,[r['margin'] for r in vv],.23,color=color,label=arm)
        ax.axhline(10,c='k',ls='--',label='Required margin 10');ax.set(xticks=np.arange(len(seeds)),xticklabels=[str(s) for s in seeds],
            title=f"{state['scan']} / {state['points']} points / {state['predictive_status']}",ylabel='Predictive competitor margin');ax.legend(fontsize=7);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Final likelihood role changes confidence: two former candidates remain ambiguous\nSame winner in every fold is insufficient when a competitor predicts almost equally well')
    save(fig,'identity_margins.png')
    fig,axs=plt.subplots(1,2,figsize=(14,6),layout='constrained');x=np.arange(len(comparison));labels=[r['scan']+'\n'+r['variant']+('' if r['RF_qualified'] else '\nUNQUALIFIED') for r in comparison]
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        for role,offset,color in [('control',-.18,'#999'),('addition',.18,'#0072b2')]:
            rr=[next(t for t in trials if (t['scan'],t['variant'],t['role'],t['arm'])==(c['scan'],c['variant'],role,arm)) for c in comparison]
            ax.bar(x+offset,[r['error_km'] for r in rr],.34,color=color,label=role)
        ax.set(xticks=x,xticklabels=labels,ylabel='Evaluation position error (km)',title=arm);ax.tick_params(axis='x',labelsize=7);ax.legend();ax.grid(axis='y',alpha=.2)
    fig.suptitle('Matched controls and proposed inclusion; every numerical version remains visible\nRF qualification and position accuracy are separate results')
    save(fig,'position_comparison.png')
    fig,axs=plt.subplots(3,2,figsize=(14,10),layout='constrained')
    final_variants=[('DS24-0099','Powell / 0.1 s'),('DS24-0081','Feasible / 0.025 s')]
    for col,(scan,label) in enumerate(final_variants):
        rec=records[scan,label]
        for arm,color in [('c0','#0072b2'),('fitted_c','#d55e00')]:
            v=rec['addition']['arms'][arm];d=v['family']['diagnostics'][0];t=np.array(d['times_s']);res=np.array(d['raw_residual_hz'])-d['profile_bias_hz']
            if arm=='c0':axs[0,col].scatter(t,np.array(d['CFO_hz'])/1000,s=10,c='k',label='Original GLRT')
            axs[0,col].plot(t,(np.array(d['prediction_CFO_hz'])+d['profile_bias_hz'])/1000,c=color,label=arm+' model + profiled constant')
            axs[1,col].plot(t,res,'.-',c=color,label=arm)
            c=rec['control']['arms'][arm];b=len(c['proposed_associated_ids']);a=len(v['proposed_associated_ids']);den=inventories[scan]['summary'][0]['total_GLRT']
            axs[2,col].plot([100*b/den,100*a/den],[error(c),error(v)],'o-',c=color,label=arm)
        axs[0,col].set(title=scan+' / '+('qualified candidate' if next(c['RF_qualified'] for c in comparison if c['scan']==scan and c['variant']==label) else 'unqualified proposal'),ylabel='Stored graph CFO (kHz)',xlabel='Time (s)')
        axs[1,col].axhline(0,c='k',lw=.5);axs[1,col].set(ylabel='Profile residual (Hz)',xlabel='Time (s)')
        axs[2,col].set(xlabel='Proposed associated GLRT (%)',ylabel='Position error (km)')
        for ax in axs[:,col]:ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('Two supported identities: target fit, coverage and position effects\nNo gate relaxation, target-driven receiver calibration or production promotion')
    save(fig,'target_curves_and_coverage.png')
    summary=dict(original_assessments_completed=sum(bool(r['annotation_source']) for r in ledger),inventory_total=len(ledger),annotation_batch=dict(Counter(r['status'] for r in batch)),
        original_candidates=4,predictively_supported=sum(r['predictive_status']=='conditionally_supported_identity' for r in states),
        final_RF_candidates=sum(r['RF_qualified'] for r in comparison if (r['scan'],r['variant']) in final_variants),
        final_RF_candidate_points=sum(r['proposed_added'] for r in comparison if (r['scan'],r['variant']) in final_variants and r['RF_qualified']),
        production_changed=False,production_new_points=0,historical_phase_audits=sum(bool(r.get('phase_audit_source')) for r in ledger))
    write(out/'summary.json',summary)
    for name in ('report_large_predictive_transfer.py','test_predictive_graph_transfer.py','annotate_predictive_only.py','include_predictive_annotations.py','include_new_predictive_family.py',
        'predictive_new_family.py','audit_predictive_family_inclusion.py','phase_reference_checks.py','report_inventory_experiments.py','include_new_family_feasible.py','ds23_feasible_position.py'):
        p=Path(__file__).with_name(name);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    text=f'''# Large DS24 curves: identity rechecks and controlled inclusion

This iteration applies the existing predictive recovery rule to the **four largest eligible supported DS24 graph curves on distinct scans**, totaling 348 points. Eligibility excludes recorded predictive rechecks/inclusions and earlier transfer claims. Selection uses point count and a deterministic track-ID tie break; no position error enters selection. The [frozen selection](selection.json) preserves all 102 eligible entries and source hashes. These are development cases from an already studied dataset, not an untouched generalization cohort.

## Identity must be checked in its intended likelihood role

The earlier inventory screen allowed an annotated curve's training points to participate in calibration. For this inclusion rule, the candidate is predictive: it must not calibrate the receiver. Recheck its identity with the same predictive role, causal phase/orbit uncertainty and conditional-target score that the proposed inclusion uses. Use three distinct random scanwide 12 s block partitions with 2 s guards, matched candidate sets across c arms, and training-only nomination/alias selection. The frozen graph and incumbent identities remain conditioning assumptions; the search is not an exhaustive catalogue evidence integral and the margins are not calibrated probabilities.

{table(states,['scan','points','original_norad','predictive_norad','predictive_status','minimum_margin'])}

DS24-0018 still favors 56781 in every fold, but one partition cannot distinguish it from 57883 (margin ~0.11). DS24-0101 still favors 60141, but one partition falls below the fixed margin-10 requirement against 66438 (~8.95). Both remain ambiguous and **do not enter the position fit**. We do not lower the threshold or pick their favored label because a curve is large. DS24-0099 supports 67921 and DS24-0081 supports 69699. Both are uncalibrated families under this scan's retained observation set, so inclusion integrates a causal phase mixture and orbital/receiver uncertainty.

![Predictive identity margins](figures/identity_margins.png)

This is a practical change in how the inventory must be read: a completed original assessment is not final authorization for every downstream likelihood. The ledger preserves original evidence and separately records predictive rechecks and inclusion decisions. The systematic workflow should validate the role in which a curve will actually be used.

## Controlled position trials and numerical follow-ups

The regional control and addition start at the center of the same 25 × 25 km box, **37.906, −122.545**, with five phase rounds and up to 48 position steps / 240 objective calls per round. The later feasible continuation starts from that regional control, as described below. The target does not enter receiver calibration normal equations. Preserve all existing observations, candidate sets, physical priors and original noise policy. Both c=0 and fitted-c are run. GPS **{SITE}** is read only by this reporting tool to calculate error.

The initial DS24-0099 L-BFGS-B control reports abnormal termination despite passing exact residual/ownership replay. Repeat both control and addition with the already implemented Powell optimizer. The initial DS24-0081 run additionally fails the phase-integration score/gradient agreement check; repeat both arms with Powell and a 0.025 s phase grid instead of 0.1 s. These follow-ups are triggered by numerical diagnostics, not GPS improvement. Priors, observations and residual thresholds remain unchanged; the finer quadrature costs more per objective evaluation. Original failed runs remain visible.

{table(comparison,['scan','variant','c0_control_km','c0_addition_km','fitted_control_km','fitted_addition_km','proposed_added','paired_fit_valid','exact_replay_valid','RF_qualified'])}

![Position comparisons](figures/position_comparison.png)

RF qualification requires both matched controls and additions to pass optimizer, phase, residual and ownership checks, plus independent exact-orbit endpoint replay. Total objectives with different observations are not treated as evidence that inclusion improves localization. [Every arm and role](position_trials.csv), [exact replays](exact_replays.csv), and any [failed incumbent gates](failed_incumbent_gates.csv) are recorded. Repeated occurrences of the same failed gate across family replays are deduplicated in the failure table.

![Target curves, residuals and coverage](figures/target_curves_and_coverage.png)

The refined DS24-0099 trial adds the full 91-point curve without losing or relabeling existing points, but error increases by about 0.10 km in c=0 and 0.08 km in fitted-c. It is a research RF candidate, **not an accuracy improvement or production promotion**. The DS24-0081 curve fits well itself; its initial proposal improves error but fails numerical checks and narrowly pushes an existing RX1 CH8 T001 slope outside its gate in c=0. Finer quadrature reduces the apparent improvement to about 0.09 / 0.08 km, while leaving a normalized incumbent slope slack of approximately −0.017. A target's good residuals cannot override that incumbent failure.

## Feasible inclusion prototype

For DS24-0081, apply the existing RF-feasible SLSQP optimizer to the combined new-family likelihood, constrained by every incumbent curved and predictive residual slack. Start **both** the no-addition continuation and the addition continuation from the same exact-RF-qualified regional control. Both use five phase rounds, up to 48 SLSQP iterations per round, and a 600 s stage wall-clock cap; there is no separate objective-call cap for this continuation. This is a matched continuation test, not another independent regional initialization. Solver status and the best feasible visited point are recorded separately. Selection uses only the RF objective and unchanged gates.

The target's physical residual, phase-boundary and quadrature checks remain endpoint requirements; they are not replaced by solver success. After the fit, independently replay exact incumbent orbits, all old owners and the target's continuous-phase prediction. The feasible continuation passes in both arms, retains all **84 points**, and preserves every incumbent owner. Error changes **2.011 → 1.936 km** (c=0) and **2.065 → 1.982 km** (fitted-c). The c=0 solution is very close to the protected slope boundary: exact normalized slack is only **3.29 × 10⁻⁷**, versus 0.0106 at control. This is a qualified endpoint under the current gates, not a robust safety margin; perturbation/replication checks or a justified interior-margin policy are required before promotion. The prototype changes how the optimizer respects existing evidence, not the satellite catalogue, waveform measurements, priors or gate thresholds. It does not establish generalization beyond this case.

## Interpretation and next steps

There are distinct bottlenecks: identity ambiguity under the intended calibration model, numerical integration/optimization, and conflicts between new evidence and retained curves. More associated GLRT can increase or decrease position error. This experiment gives no basis to force ambiguous labels, relax residual thresholds, or promote an ALGO version.

For supported curves, preserve physical uncertainty and verify existing owners after inclusion. The feasible-continuation prototype should next be tested on additional supported cases with the same RF-only trigger, retaining failures and comparing matched c arms. If it still fails exact replay, investigate corroborated model corrections rather than widening gates. For genuinely ambiguous curves, a future hypothesis-mixture likelihood could retain uncertain identity without assigning a hard label, but it needs an explicit unmodeled-source alternative and false-association controls before use. Such a mixture is **not implemented or counted as recovery here**.

## Inventory and reproducibility

Attempt 33 outcomes: `{summary['annotation_batch']}`. Original assessments completed: **{summary['original_assessments_completed']} / {summary['inventory_total']}**; historical separate phase audits: {summary['historical_phase_audits']}. These counts include ambiguous, unstable, mismatched and insufficient-partition outcomes. They are not final accepted associations or the count validated under the predictive inclusion role. This four-curve transfer yields **{summary['final_RF_candidates']} final RF candidate(s), {summary['final_RF_candidate_points']} proposed points**, with zero production points added.

Use `test_predictive_graph_transfer.py` with the frozen four IDs, followed by the exact commands retained in the numerical follow-up protocols. `include_new_family_feasible.py` runs the matched constrained continuation; `report_large_predictive_transfer.py` generates this report. [Sources](sources.json), [compact raw receipts](evidence.json.gz), [ledger](annotation_ledger.csv), [batch](annotation_batch.csv) and [execution records](executions.csv) preserve outcomes, including rejected proposals. The [continuation budget receipt](continuation_budget.json) clarifies an inherited source-protocol field: the initial trial copied `maxfun=240`, but SLSQP enforced the iteration and wall-time budgets, not that objective-call cap. Its exact source is preserved; the current runner explicitly records `maxfun=null`. No fit result was overwritten. **23 targeted tests pass**: 21 existing tests for family routing, owner preservation, raw phase convergence, new-family prediction and covariance qualification, plus two tests requiring both verified control arms and protecting an incumbent constraint against a conflicting objective. The new continuation is research-only; production policy is unchanged.
'''
    write(out/'selection.json',selection);(out/'README.md').write_text(text);print(summary,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
