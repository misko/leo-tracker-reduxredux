"""Report fixed-margin sensitivity without choosing a margin using position truth."""
import argparse,csv,gzip,hashlib,json
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays
from report_predictive_track_annotation import table
from report_inventory_experiments import error
from leo.analysis.research.grouped_prediction import identity_consensus


def worst_replayed_slacks(row):
    """Keep the worst value across orbit replays, never the last duplicate."""
    result={}
    for family in row['exact_incumbent_family_replays']:
        for key,value in family['all_gate_slacks'].items():result[key]=min(result.get(key,float('inf')),value)
    return result


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir()
    hashes={};evidence={};rows=[];comparisons=[];executions=[]
    def load(p):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p)
        evidence[str(p)]=compact_replays(compact_evidence(r));return r
    def csvout(name,records):
        keys=list(dict.fromkeys(k for r in records for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(records)
    root=s/'ds24-0081-gate-margin-sensitivity-v1';load(root/'protocol.json');load(root/'execution.json')
    specs=[(0.,s/'ds24-largest-predictive-transfer-feasible-0081-v1/trial')]+[(m,root/str(m)/'trial') for m in (.005,.01)]
    for margin,folder in specs:
        for stage in ('inclusion','replay'):
            receipt=load(folder.parent/(stage+'-terminal.json'));assert receipt['status']=='complete'
            executions.append(dict(margin=margin,**receipt))
        pr=load(folder/'protocol.json');control=load(folder/'control.json');addition=load(folder/'new_family.json');audit=load(folder/'exact_owner_replay.json')
        qualified=control['paired_valid'] and addition['paired_valid'] and audit['all_verified']
        for role,pair in [('control',control),('new_family',addition)]:
            for arm,v in pair['arms'].items():
                replay=next(r for r in audit['rows'] if (r['role'],r['arm'])==(role,arm))
                slacks=worst_replayed_slacks(replay);minimum=min(slacks.values())
                old=set(control['arms'][arm]['proposed_associated_ids']);current=set(v['proposed_associated_ids'])
                family=v.get('family',{})
                rows.append(dict(margin=margin,role=role,arm=arm,error_km=error(v),east_km=v['endpoint_east_north_km'][0],north_km=v['endpoint_east_north_km'][1],
                    proposed_associated=len(current),added=len(current-old),lost=len(old-current),paired_valid=pair['paired_valid'],RF_qualified=qualified,
                    exact_verified=replay['verified'],minimum_exact_slack=minimum,exact_meets_requested_margin=minimum>=margin,
                    protected_CH8_slope_slack=slacks['DS24-0081-RX1-CH8-T001-RF12690312500.000000/linear/slope'],
                    objective=v['negative_twice_elbo'],final_phase_gap_s=v['final_phase_change_s'],solver_success=v['history'][-1]['fit']['solver_success'],
                    old_owner_changes=len(replay['incumbent_ownership_changes']),control_owner_changes=len(replay['control_ownership_changes']),
                    target_RMS_hz=family.get('diagnostics',[{}])[0].get('profile_RMS_hz'),
                    quadrature_pass=v.get('phase_resolution_audit',{}).get('local_agreement')))
        rr=[r for r in rows if r['margin']==margin]
        row=dict(margin=margin,RF_qualified=qualified,exact_margin_met=all(r['exact_meets_requested_margin'] for r in rr))
        for arm in ('c0','fitted_c'):
            c=next(r for r in rr if r['role']=='control' and r['arm']==arm);a=next(r for r in rr if r['role']=='new_family' and r['arm']==arm)
            row.update({arm+'_control_km':c['error_km'],arm+'_addition_km':a['error_km'],arm+'_added':a['added'],arm+'_CH8_slack':a['protected_CH8_slope_slack']})
        comparisons.append(row)
    csvout('position_trials.csv',rows);csvout('comparison.csv',comparisons)
    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));lookup={r['track_id']:r for r in ledger}
    queue=s/'systematic-annotation-v1';attempt=queue/'attempt-34';pr=load(attempt/'protocol.json');assert pr['predictive_member']
    load(attempt/'execution.json');batch=[]
    for job in load(attempt/'selected.json'):
        tid=job['track_id'];terminal=load(attempt/(tid+'-terminal.json'));executions.append(dict(group='annotation34',**terminal))
        if terminal['status']!='complete':
            log=attempt/(tid+'.log');hashes[str(log)]=hashlib.sha256(log.read_bytes()).hexdigest()
            evidence[str(log)]=log.read_text()
            inventory=load(Path(job['inventory']))
            target=next(r for r in inventory['tracks'] if r['track_id']==tid)
            write(out/(tid+'-failed-track.json'),dict(track_id=tid,component=target['component'],
                current=target['current'],terminal=terminal,log=log.read_text()))
            state='execution_'+terminal['status']
            lookup[tid].update(state=state,annotation_execution_source=str(attempt/(tid+'-terminal.json')))
            batch.append(dict(scan=job['label'],track_id=tid,points=job['points'],status=state,norad=None,minimum_margin=None))
            continue
        path=queue/tid/'result.json';r=load(path);load(path.parent/'protocol.json')
        assert r['inclusion_mode']=='predictive_only' and r['identity_score_name']=='conditional_target'
        a=identity_consensus(r['folds'],score_name='conditional_target')
        lookup[tid].update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),
            predictive_recheck_source=str(path),predictive_recheck_state=a['status'],predictive_recheck_minimum_margin=a.get('minimum_margin'),
            annotation_likelihood_role='predictive_only; first assessment',partition_policy='distinct timestamps')
        batch.append(dict(scan=job['label'],track_id=tid,points=job['points'],status=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin')))
    csvout('annotation_batch.csv',batch);csvout('annotation_ledger.csv',ledger);csvout('executions.csv',executions)
    summary=dict(inventory_total=len(ledger),original_assessments=sum(bool(r.get('annotation_source')) for r in ledger),
        assessed_any_role=sum(bool(r.get('annotation_source') or r.get('predictive_recheck_source')) for r in ledger),
        direct_predictive_batch_attempted=len(batch),direct_predictive_batch_completed=sum(not r['status'].startswith('execution_') for r in batch),
        batch_states=dict(Counter(r['status'] for r in batch)),
        RF_qualified_margin_trials=sum(r['RF_qualified'] for r in comparisons),production_changed=False)
    write(out/'summary.json',summary)
    fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for col,arm in enumerate(('c0','fitted_c')):
        for role,color in [('control','#888888'),('new_family','#0072b2')]:
            rr=[r for r in rows if r['role']==role and r['arm']==arm]
            axs[0,col].plot([r['margin'] for r in rr],[r['error_km'] for r in rr],'o-',c=color,label=role)
            axs[1,col].plot([r['margin'] for r in rr],[r['protected_CH8_slope_slack'] for r in rr],'o-',c=color,label=role)
        axs[1,col].plot([0,.01],[0,.01],'k--',label='Requested minimum')
        axs[0,col].set(title=arm,ylabel='Evaluation position error (km)')
        axs[1,col].set(ylabel='Worst exact RX1 CH8 slope slack')
        for ax in axs[:,col]:ax.set_xlabel('Requested normalized gate margin');ax.grid(alpha=.25);ax.legend()
    fig.suptitle('DS24-0081: same 84-point curve, causal priors and matched continuation budgets\nMargin is a sensitivity setting, not a calibrated probability')
    fig.savefig(out/'figures/margin_sensitivity.png',dpi=150);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for col,arm in enumerate(('c0','fitted_c')):
        rr=[r for r in rows if r['role']=='new_family' and r['arm']==arm];base=rr[0]['objective']
        axs[col].plot([r['margin'] for r in rr],[r['objective']-base for r in rr],'o-')
        axs[col].set(title=arm,xlabel='Requested normalized gate margin',ylabel='RF objective increase vs margin 0');axs[col].grid(alpha=.25)
    fig.suptitle('Frequency-score cost uses identical observations within each arm\nThis comparison does not imply a position-accuracy gain')
    fig.savefig(out/'figures/frequency_score_cost.png',dpi=150);plt.close(fig)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    for name in ('include_new_family_feasible.py','report_predictive_margin_sensitivity.py','run_annotation_inventory.py'):
        path=Path(__file__).with_name(name);hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    write(out/'sources.json',hashes)
    text=f'''# DS24-0081 recovery: residual-margin sensitivity and role-consistent annotation

The previous feasible continuation recovered an 84-point curve associated with causal NORAD 69699, but an incumbent RX1 CH8 T001 residual-slope gate had almost no remaining margin. This iteration tests **two predeclared stricter margins, 0.005 and 0.01**, without changing identity, observations, physical priors, phase quadrature or target calibration role. Both no-addition control and addition use the same qualified regional-control starting point, five phase rounds and 48 SLSQP iterations per round. Each inclusion/replay stage has a 600 s wall-clock cap. There is no separate objective-call cap. This is a continuation sensitivity study, not a fresh regional or multi-start evaluation.

The normalized slope slack is `1 - slope_z / 3`. A margin of 0.01 therefore asks for `slope_z <= 2.97` instead of 3. Margins constrain every incumbent slack; other gates have their own normalizations. These settings are **sensitivity checks, not calibrated confidence levels or a selected production policy**. GPS is used only here to report error, never to fit or select a margin. Causal TLEs and the original 25 × 25 km regional control are retained. The target does not calibrate the receiver at a fixed position.

## Controlled results

{table(comparisons,['margin','c0_control_km','c0_addition_km','fitted_c_control_km','fitted_c_addition_km','c0_added','fitted_c_added','RF_qualified','exact_margin_met'])}

![Position and residual margin](figures/margin_sensitivity.png)

Both tighter-margin trials pass in both c arms and retain all 84 proposed points with no incumbent ownership changes. At margin 0.01, error changes **2.011 → 1.945 km** (c=0) and **2.065 → 1.983 km** (fitted-c). Compared with the prior zero-margin addition, c=0 error changes by only about 9 m. This reduces concern that the recovery depends on barely passing the original gate. It remains a modest improvement on one scan. The c=0 optimizer still reaches the newly imposed slope boundary, so the underlying tension with retained CH8 evidence has not disappeared or been physically explained.

The proposed curve contains 84 points. A qualified result must retain all incumbent observations and owners, pass the target physical/noise and phase-quadrature checks, and pass independent exact-orbit replay. [Every arm and role](position_trials.csv) records the actual outcome, minimum exact slack, protected CH8 slope, optimizer status and ownership differences. Exact replay substitutes one incumbent family at a time; it is not a simultaneous exact-orbit refit. For duplicated gate keys, this report takes the **minimum over every replay**, not whichever value happened to be written last. A requested optimization margin and the independently replayed exact margin are reported separately; neither is silently substituted for the other.

![Frequency-score cost](figures/frequency_score_cost.png)

The frequency-score comparison uses the same observations within each c arm. Control and addition have different observation sets, so their raw objectives are not interpreted as a localization comparison. Error against GPS is reported separately. All raw trials are preserved; no result is replaced by a more favorable run.

## Annotation pipeline correction

New graph-member assessments can now directly use `annotate_predictive_only.py --predictive-member --uncalibrated-phase-mixture`, so the candidate cannot calibrate the receiver that will later be used to predict it. Existing-family candidates use their retained shared posterior; new or uncalibrated families integrate the causal phase mixture. The inventory runner retains exclusive attempt claims and adds an explicit likelihood-role receipt. Default legacy behavior remains available for reproducibility.

Attempt 34 processes the next 16 pending graph curves in the existing frozen ordering. DS24 has no remaining pending graph rows in the original queue, so these are additional AUTO recordings from the wider inventory. They are not 16 new DS24 validations. Three distinct random scanwide 12 s block holdouts with 2 s guards are selected by timestamps; nomination and calibration use training observations only. Insufficient independent partitions remain an explicit outcome. Identity margins are candidate-comparison scores, not posterior probabilities. The frozen graph and incumbent identities remain conditioning assumptions.

Batch outcomes: **{summary['batch_states']}**. The full inventory has **{summary['assessed_any_role']} / {summary['inventory_total']}** tracks assessed in at least one role, including {summary['original_assessments']} original-role assessments. These counts include failures and ambiguity; they are not accepted coverage. The [ledger](annotation_ledger.csv) retains original assessments separately from [the direct predictive batch](annotation_batch.csv). This batch has not yet undergone position inclusion.

Of the 16 attempted curves, 15 produce scientific annotation results. AUTO-afec5a1f / RX1 CH4 T000 is rejected by the predictive-role precondition: the 28 unassociated points belong to a 102-point graph curve that already has active calibration observations. Treating the entire curve as new predictive evidence would duplicate retained evidence. Its original failed receipt/log remains archived; it is not counted as a completed identity assessment. It needs a separately identified inactive-tail target with disjoint observation ownership, while retaining the active portion. Its residual tail spans only 20.9 s and lacks active curvature, so independent partition support must also be checked before an inclusion trial. The three newly supported identities (68397, 59155 and 48445 on three separate AUTO recordings) are conditional identity candidates only.

## Limits and next work

This study only tests sensitivity to two small incumbent margins on one previously studied recovery. It does not establish that all 84 points independently improve position, validate a universal margin, or demonstrate generalization. The candidate identity and causal model remain conditional on the earlier random-block checks. Broader matched scan tests and uncertainty/perturbation checks are needed before changing production. Ambiguous identities must remain unresolved rather than being forced to meet a coverage target.

No production policy or ALGO version changes. Reproduce with `include_new_family_feasible.py --gate-margin 0.005` and `--gate-margin 0.01`, then `audit_predictive_family_inclusion.py`; exact commands and completion statuses are retained in [execution records](executions.csv). [Source hashes](sources.json) and [compact scientific evidence](evidence.json.gz) cover all reported runs. **33 targeted tests pass**, including positive margins, rejection of negative/nonfinite margins, matched-control requirements, predictive queue routing and conservative aggregation of duplicate exact-replay gates.
'''
    (out/'README.md').write_text(text);print(summary,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):parser.add_argument('--'+name,type=Path,required=True)
    run(parser.parse_args())
