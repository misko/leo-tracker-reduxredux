"""Publish matched uncertainty ablations, transfer failures and inventory growth."""
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
from leo.analysis.research.grouped_prediction import identity_consensus


def compact_replays(value):
    """Retain gate failures and summaries; hash repetitive full owner/gate maps."""
    if isinstance(value,list):return [compact_replays(v) for v in value]
    if not isinstance(value,dict):return value
    result={}
    for k,v in value.items():
        if k in ('owners','proposed_owners','all_gate_slacks') and isinstance(v,dict):
            receipt=dict(count=len(v),sha256=hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest())
            if k=='all_gate_slacks':receipt.update(minimum=min(v.values()),failures={key:x for key,x in v.items() if x<0})
            result[k+'_receipt']=receipt
        else:result[k]=compact_replays(v)
    return result


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir()
    hashes={};evidence={};executions=[]
    def load(p):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p);evidence[str(p)]=compact_replays(compact_evidence(r));return r
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=150);plt.close(fig)
    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger}
    q=s/'systematic-annotation-v1';attempt=q/'attempt-27';load(attempt/'protocol.json');batch=[]
    for j in load(attempt/'selected.json'):
        tid=j['track_id'];terminal=load(attempt/(tid+'-terminal.json'));executions.append(dict(stage='annotation27',**terminal))
        row=dict(scan=j['label'],track_id=tid,status='execution_'+terminal['status'],norad=None)
        if terminal['status']=='complete':
            path=q/tid/'result.json';r=load(path);load(path.parent/'protocol.json')
            a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'));row.update(status=a['status'],norad=a['norad'])
            byid[tid].update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),annotation_source=str(path),
                partition_policy='distinct timestamps',geometry_only_early_exit=r.get('geometry_only_early_exit',False),
                distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        else:byid[tid]['state']=row['status']
        batch.append(row)
    csvout('annotation_batch.csv',batch)
    # Both numerical resolutions stay visible; only the refined experiment
    # meets all quadrature checks for every covariance combination.
    rows=[];runs={};controls={};replay_rows=[]
    labels={'both':'Orbit + receiver','orbit_only':'Orbit only','receiver_only':'Receiver only','neither':'Neither'}
    for version in (1,2):
        root=s/f'predictive-covariance-ablation-49154edb-v{version}';pr=load(root/'protocol.json')
        for job in pr['jobs']:
            name=job['name'];term=load(root/(name+'-terminal.json'));assert term['status']=='complete'
            for stage in term['stages']:executions.append(dict(group='covariance v'+str(version)+' '+name,**stage))
            folder=root/name;config=load(folder/'protocol.json');c=load(folder/'control.json');r=load(folder/'new_family.json');audit=load(folder/'exact_owner_replay.json')
            runs[version,name]=r;controls[version,name]=c
            for arm,v in r['arms'].items():
                f=v['family'];d=f['diagnostics'][0];check=v['phase_resolution_audit'];base=c['arms'][arm]
                ids=set(v['proposed_associated_ids']);old=set(base['proposed_associated_ids']);target=set(config['targets'][0]['observation_ids'])
                assert ids-old==target and not old-ids
                rows.append(dict(version=version,phase_step_s=config['phase_step_s'],variant=name,orbit_covariance=job['orbit'],receiver_covariance=job['receiver'],arm=arm,
                    control_error_km=error(base),error_km=error(v),added_points=len(ids-old),lost_points=len(old-ids),
                    associated_points=len(ids),paired_gates=r['paired_valid'],exact_owner_verified=audit['all_verified'],
                    target_RMS_hz=d['profile_RMS_hz'],target_negative_twice_log_density=f['negative_twice_log_density'],
                    phase_map_s=f['phase_map_s'],phase_sigma_s=f['phase_sigma_s'],
                    quadrature_pass=check['local_agreement'],quadrature_score_change=check['maximum_score_change'],
                    quadrature_gradient_change=check['gradient_change_per_km'],receiver_coefficient_change=f['receiver_calibration_change'],
                    maximum_orbit_posterior_sigma=max(abs(x) for x in f['orbital_posterior_mean'])))
            for v in audit['rows']:
                replay_rows.append(dict(version=version,variant=name,role=v['role'],arm=v['arm'],verified=v['verified'],
                    objective_difference=v['objective_difference'],phase_gap_s=v['phase_reference_check']['phase_change_s'],
                    incumbent_owner_changes=len(v['incumbent_ownership_changes']),control_owner_changes=len(v['control_ownership_changes'])))
    csvout('covariance_ablation.csv',rows);csvout('covariance_replays.csv',replay_rows)
    control_check=[]
    for version in (1,2):
        for arm in ('c0','fitted_c'):
            base=controls[version,'both']['arms'][arm]
            for name in labels:
                v=controls[version,name]['arms'][arm]
                delta=float(np.max(abs(np.array(v['endpoint_east_north_km'])-base['endpoint_east_north_km'])))
                assert delta<1e-8 and v['proposed_associated_ids']==base['proposed_associated_ids']
                control_check.append(dict(version=version,arm=arm,variant=name,maximum_control_coordinate_difference_km=delta,
                    control_objective_difference=v['negative_twice_elbo']-base['negative_twice_elbo']))
    csvout('matched_controls.csv',control_check)
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        rr=[r for r in rows if r['version']==2 and r['arm']==arm]
        x=np.arange(4);ax.bar(x,[r['error_km'] for r in rr],color=['#009e73','#56b4e9','#e69f00','#d55e00'])
        for i,r in enumerate(rr):ax.text(i,r['error_km']+.025,f"{r['error_km']:.3f}",ha='center')
        ax.axhline(rr[0]['control_error_km'],color='black',ls='--',label='Matched no-addition control')
        ax.set(xticks=x,xticklabels=[labels[r['variant']] for r in rr],ylabel='Position error (km)',title=arm,ylim=(0,2.3));ax.tick_params(axis='x',labelsize=9);ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
    fig.suptitle('AUTO-49154edb: same 42 points, noise, phase prior and search budgets\nAll four refined trials pass gates and replay; target never calibrates the receiver.')
    save(fig,'covariance_position_error.png')
    fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for col,arm in enumerate(('c0','fitted_c')):
        for name,color in zip(labels,['#009e73','#56b4e9','#e69f00','#d55e00'],strict=True):
            d=runs[2,name]['arms'][arm]['family']['diagnostics'][0];tt=d['times_s']
            if name=='both':axs[0,col].scatter(tt,np.array(d['CFO_hz'])/1000,s=12,color='black',label='GLRT')
            axs[0,col].plot(tt,(np.array(d['prediction_CFO_hz'])+d['profile_bias_hz'])/1000,color=color,alpha=.8)
            axs[1,col].plot(tt,np.array(d['raw_residual_hz'])-d['profile_bias_hz'],'.-',ms=3,color=color,label=labels[name])
        axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Residual after profiled bias (Hz)');axs[1,col].axhline(0,color='black',lw=.6)
        for ax in axs[:,col]:ax.grid(alpha=.2)
        axs[1,col].legend(fontsize=8)
    fig.suptitle('NORAD 58893: physical orbit uncertainty changes fit and positional influence\nAll four residual screens pass; passing residual gates alone does not assure position accuracy.')
    save(fig,'covariance_curve_residuals.png')
    fig,axs=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for ax,key,limit in zip(axs,('quadrature_score_change','quadrature_gradient_change'),(.001,.01),strict=True):
        for version,marker,color in [(1,'x','#d55e00'),(2,'o','#0072b2')]:
            rr=[r for r in rows if r['version']==version]
            ax.scatter(range(8),[r[key] for r in rr],marker=marker,color=color,label='0.1 s grid' if version==1 else '0.05 s grid')
        ax.axhline(limit,color='black',ls='--');ax.set_yscale('log');ax.set_xticks(range(8),[r['variant']+'\n'+r['arm'] for r in rows[:8]],fontsize=7)
        ax.set_ylabel(key.replace('_',' '));ax.legend();ax.grid(axis='y',alpha=.2)
    fig.suptitle('Numerical refinement was required before interpreting the factorial comparison')
    save(fig,'phase_quadrature.png')

    transfer=[];votes=[]
    cases=[('49154edb','43897235b1c6fc1e8428',s/'graph-predictive-recheck-49154edb-v1'/'annotation','new family','RF_verified_candidate'),
           ('e32d57a7','31d98d4cc908a38c734b',s/'graph-predictive-recheck-e32d57a7-v1'/'annotation','new family','identity_ambiguous'),
           ('e9398e7a','624a7b3f5981badab721',s/'graph-predictive-transfer24-v1'/'624a7b3f5981badab721'/'annotation','new family','identity_ambiguous'),
           ('e565210d','8c2ef4f04618dc6c227f',s/'graph-predictive-transfer24-v1'/'8c2ef4f04618dc6c227f'/'annotation','existing shared family','residual_lag_rejected')]
    load(s/'graph-predictive-transfer24-v1'/'protocol.json')
    for short,tid,path,route,status in cases:
        r=load(path/'result.json');load(path/'protocol.json');a=identity_consensus(r['folds'],score_name='conditional_target')
        transfer.append(dict(scan='AUTO-'+short,track_id=tid,norad=a['norad'],identity_status=a['status'],minimum_margin=a['minimum_margin'],route=route,outcome=status))
        votes.extend(dict(scan='AUTO-'+short,**v) for v in a['votes'])
        byid[tid].update(predictive_recheck_source=str(path/'result.json'),predictive_recheck_state=a['status'],predictive_recheck_minimum_margin=a['minimum_margin'])
        if short in ('e9398e7a','e565210d'):
            term=load(s/'graph-predictive-transfer24-v1'/(tid+'-terminal.json'))
            for stage in term['stages']:executions.append(dict(scan='AUTO-'+short,**stage))
            byid[tid]['predictive_research_inclusion']=status
    csvout('transfer_summary.csv',transfer);csvout('transfer_votes.csv',votes)
    root=s/'shared-predictive-transfer-e565210d-v1';load(root/'protocol.json');term=load(root/'inclusion-terminal.json');executions.append(dict(stage='shared-family reroute',**term))
    pr=load(root/'inclusion'/'protocol.json');control=load(root/'inclusion'/'control.json');target=load(root/'inclusion'/'target_0.json');audit=load(root/'inclusion'/'exact_owner_replay.json')
    byid['8c2ef4f04618dc6c227f']['predictive_inclusion_source']=str(root/'inclusion')
    shared=[]
    fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for col,(arm,v) in enumerate(target['arms'].items()):
        d=v['target_diagnostics'][0];a=next(x for x in audit['rows'] if x['role']=='target_0' and x['arm']==arm)
        family=next(x for x in a['exact_family_replays'] if x['norad']==63381)
        failed={k:z for k,z in family['all_gate_slacks'].items() if z<0}
        lag=next(z for k,z in failed.items() if k.endswith('/lag1'));n=pr['targets'][0]['points'];threshold=4/np.sqrt(n)
        shared.append(dict(arm=arm,control_error_km=error(control['arms'][arm]),target_error_km=error(v),added_proposed_points=v['added_points'],
            accepted_recovery=False,RMS_hz=d['RMS_hz'],absolute_lag1=(1-lag)*threshold,lag1_limit=threshold,
            failed_slack=lag,failed_gates=';'.join(failed),exact_owner_verified=a['verified'],
            incumbent_owner_changes=len(a['incumbent_ownership_changes']),receiver_coefficient_change=a['receiver_coefficient_change']))
        axs[0,col].scatter(d['times_s'],np.array(d['CFO_hz'])/1000,s=12,color='black')
        axs[0,col].plot(d['times_s'],(np.array(d['predicted_CFO_hz'])+d['bias_hz'])/1000,color='#d55e00')
        axs[1,col].plot(d['times_s'],d['residual_hz'],'.-',color='#d55e00');axs[1,col].axhline(0,color='black',lw=.6)
        axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Profile residual (Hz)')
        for ax in axs[:,col]:ax.grid(alpha=.2)
    fig.suptitle('AUTO-e565210d / RX1 CH1 / NORAD 63381 — REJECTED\nIdentity is supported, but shared-posterior prediction retains correlated residuals.')
    save(fig,'shared_family_rejection.png');csvout('shared_family_rejection.csv',shared)
    csvout('annotation_ledger.csv',ledger);csvout('executions.csv',executions)
    summary=dict(annotations_completed=sum(bool(r['annotation_source']) for r in ledger),inventory_total=len(ledger),
        annotation_batch=dict(Counter(r['status'] for r in batch)),cumulative_phase_audited=sum(bool(r.get('phase_audit_source')) for r in ledger),
        transfer_cases=len(transfer),predictive_inclusions_verified=1,ambiguous_identities=2,shared_family_residual_rejections=1,
        refined_factorial_all_valid=all(r['paired_gates'] and r['exact_owner_verified'] and r['quadrature_pass'] for r in rows if r['version']==2),
        production_changed=False,retained_policy_changed=False)
    write(out/'summary.json',summary);write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    refined=[r for r in rows if r['version']==2]
    (out/'README.md').write_text(f'''# Orbital uncertainty explains the adverse pull of one recovered curve

A matched four-way ablation isolates a major cause of the AUTO-49154edb regression: **omitting physical orbital uncertainty**. With the same 42 target points and no target-driven receiver calibration, fitted-c position error is **0.589 km** with orbital uncertainty, **1.573 km** with receiver uncertainty alone, and **1.893 km** with neither. The no-addition control is **0.548 km**. The new model mitigates a regression; it still does not improve that control.

The transfer experiment also limits the claim. Among all four previously RF-verified graph recoveries, the stricter predictive workflow gives one valid inclusion, two ambiguous identities and one supported identity whose shared-family residual fails. This is not a broadly validated replacement or new ALGO release.

## Controlled 2 × 2 experiment

The only factors are inclusion or removal of physical orbital covariance and shared receiver-coefficient covariance in the target predictive density. Every arm uses the same NORAD 58893, alias, 42 observations, full-data noise/weights, track-bias prior, causal phase prior, regional center start, 25 × 25 km box, five phase-reference rounds, and 48-step/240-evaluation optimizer limits. Every cell has matched c=0 and fitted-c arms. Receiver posterior means and conditioning on old predictive data are retained when receiver covariance is disabled. The target never updates receiver calibration at fixed position. It can still affect position and hence the incumbent calibration indirectly.

Physical orbital modes are removed together from the likelihood and physical prediction in the no-orbit cells. Their prior scales are fixed from the causal TLE history, not tuned against GPS. The three modes describe mean motion, inclination and RAAN perturbations, shared within the satellite family. The existing ±15 s phase box and 300 Hz bias prior are unchanged. The experiment does not vary sample rate, receiver pointing, noise policy or target/receiver feedback. Thus its result isolates orbital covariance **within this predictive model**, not every difference from the old calibrating method.

{table(refined,['variant','arm','control_error_km','error_km','added_points','target_RMS_hz','paired_gates','quadrature_pass','exact_owner_verified'])}

![Matched covariance ablation](figures/covariance_position_error.png)

All four refined variants retain the same **3,462 associated points**, adding exactly the 42 target IDs to the same 3,420-point control, with no owner changes or losses. Controls reproduce identical positions within 1e-8 km. With orbital uncertainty present, removing receiver covariance changes error by less than **one meter** in either c arm; without orbital uncertainty, receiver covariance still moderates the adverse effect by roughly **0.32–0.33 km**. This does not justify removing receiver covariance generally.

The earlier direct-calibration model gave fitted-c error 1.465 km. Its singleton support policy supplied no orbital modes for this family. The new ablation supports the explanation that a satellite model treated as too certain supplies excessive information along a weak position direction. It does not prove the actual TLE error vector, a global optimum, or the absence of shared receiver biases. The latest causal TLE is ~33.3 hours old; the physical prior was constructed from pre-observation TLE disagreement. No post-observation TLE or GPS enters fitting.

![CFO and residuals](figures/covariance_curve_residuals.png)

All refined target residual screens pass, including in the high-position-error cells. **Passing residual gates is necessary but not sufficient for accurate position.** Frequency RMS and predictive density are reported separately in [the full table](covariance_ablation.csv); lower residual RMS is not used as proof of localization improvement. The orbital posterior corrections in the retained full-uncertainty cell are below one prior standard deviation.

## Numerical resolution was checked before interpreting the comparison

The original 0.1 s phase grid fails the local score/gradient consistency guard in both no-orbit variants. Those results remain archived and rejected. We rerun **all four cells**, including their controls, on a 0.05 s grid with unchanged position-search budgets; the post-fit audit compares 0.05/0.025/0.0125 s integration at the endpoint and ±25 m neighbors. Every refined cell passes. Each is independently replayed for objective, original membership, unchanged satellite owners, raw phase convergence and physical gates; incumbent orbits are replaced one family at a time, and the target phase is also continuously refined as a diagnostic.

![Quadrature convergence](figures/phase_quadrature.png)

These are numerical checks, not new identity validation or a probability calibration. Phase truncation remains explicit: the 15 s-width Gaussian prior has 68.27% mass inside ±15 s. No grid or prior is chosen according to position error. The finer grid was triggered solely by numerical inconsistency.

## Complete transfer set: the same rule does not accept everything

{table(transfer,['scan','norad','identity_status','minimum_margin','route','outcome'])}

The additional targets are the remaining two of the four earlier exact-owner-verified graph recoveries. This completes the set; they were not selected by whether the new model improved GPS error. The first two cases were deliberately contrasting diagnostics in the previous report, so this four-case set is not an untouched population benchmark.

Fresh predictive annotations use three distinct randomized scan-wide 12 s block partitions with 2 s guards; simultaneous channels/receivers remain grouped. The target never calibrates receiver parameters, and the winning identity must have held predictive density margin at least 10 in every fold and c arm. Candidate nomination uses the same causal catalogue. Graph construction and incumbent identities remain conditioning assumptions, and position/noise-precision uncertainty is not fully integrated.

AUTO-e9398e7a prefers 63458 in every fold but has minimum margin **4.64** against 55604. It remains ambiguous and no position inclusion is run. This joins the previously ambiguous AUTO-e32d57a7 case, minimum margin **1.31** against 66322. No favorable old GPS result overrides either rejection.

AUTO-e565210d strongly supports **63381**, minimum margin **87.35**, but that family already has active calibration observations. The initial new-family routine correctly raises an eligibility error; that failed execution is preserved. The routing code now uses the shared-family predictor for an active satellite rather than inventing an independent orbital correction. Inactive graph members may enter this branch only when all their calibration mask entries are false, their observations are not duplicated, and the validated alias is stable. The original graph and calibration mask remain unchanged.

## Shared identity succeeds; shared prediction still fails

{table(shared,['arm','control_error_km','target_error_km','added_proposed_points','accepted_recovery','RMS_hz','absolute_lag1','lag1_limit'])}

![Shared-family residual failure](figures/shared_family_rejection.png)

The 42-point RX1 CH1 curve has ~62 Hz RMS, no old owner changes, and zero target-driven receiver-coefficient change at fixed position. Exact orbit discrepancies are below 0.000001 Hz. The failing gate is solely **lag-one correlation**: absolute innovation correlation is ~0.646/0.652 against the existing **4/√42 ≈ 0.617** threshold. The reported 42 proposed points are therefore **not accepted recovery**. Position changes only ~9/11 m in error, which does not authorize bypassing the residual gate. The initial wrong-route exception is an implementation eligibility issue; the subsequent correlation failure is scientific evidence about the shared prediction.

Next for this curve: compare residual structure with other observations of 63381 and simultaneous receiver/band witnesses. A shared satellite-posterior refinement may be justified if the discrepancy follows the satellite; a receiver correction needs independent families supporting it. Do not create a free per-track slope or relax the threshold simply to reach an association percentage.

## Inventory and systematic inclusion policy

Annotation attempt 27 yields `{summary['annotation_batch']}`, bringing assessed original entries to **{summary['annotations_completed']} / {summary['inventory_total']}**. Annotation states include ambiguity and mismatch; assessed count is not accepted GLRT coverage. The cumulative ledger preserves **{summary['cumulative_phase_audited']}** historical phase audits and alternate predictive outcomes without overwriting retained production policy.

The evidence supports this routing discipline:

1. Validate candidate identity under causal, random-block prediction; retain an unresolved candidate set when discrimination is inadequate.
2. For an absent or wholly uncalibrated family, integrate causal orbital and phase uncertainty even when there are too few curves to estimate a correction confidently. Use one shared family model for its evidence.
3. For an already active family, reuse its shared posterior and uncertainty. Additional fragments must not receive independent satellite corrections.
4. Separately require numerical convergence, physical residual gates, unchanged old ownership and a matched position-inclusion trial. Keep uncertainty and positional influence diagnostics alongside association percentage.

This is an emerging evidence-backed workflow, not yet a validated dataset-wide algorithm. Remaining work includes unresolved identity competition, shared-family residual structure, the unfinished inventory and independent generalization tests. The claim that every real curve must improve position remains unproven: a curve can constrain satellite uncertainty more strongly than receiver location.

## Reproduction

Run `run_predictive_covariance_ablation.py` with the frozen source inclusion and phase step 0.05 for the matched factorial trial. `test_predictive_graph_transfer.py` handles fresh identity validation and routes active versus absent families; `audit_shared_predictive_inclusion.py` independently checks the shared route. The predictive inclusion tools now measure phase convergence before clipping the numerical reference. The covariance switches default to the unchanged full-uncertainty model and are diagnostic only.

**20 targeted tests pass**, including dense Gaussian oracles for all four covariance combinations, phase mixture/resolution, role eligibility, routing, covariance isolation, ownership, grouped inventory claims and raw phase checks. Evaluation coordinates are **37.849061591561885, −122.48574968092912**; the search box remains centered at **37.906, −122.545**. GPS only evaluates errors. No production change or new ALGO promotion is made.

The compact archive retains all failing gates, minimum gate margins, numerical diagnostics and source hashes. Repetitive full owner/gate maps and observation/optimizer histories are represented by counts and hashes; the immutable full receipts remain at their recorded study paths.

[Summary](summary.json), [cumulative ledger](annotation_ledger.csv), [new annotation outcomes](annotation_batch.csv), [factorial results](covariance_ablation.csv), [matched controls](matched_controls.csv), [replays](covariance_replays.csv), [transfer set](transfer_summary.csv), [all identity votes](transfer_votes.csv), [shared-family rejection](shared_family_rejection.csv), [execution receipts](executions.csv), [source hashes](sources.json), [compact evidence](evidence.json.gz), [previous iteration](../2026_10_30_graph_position_information/README.md).
''')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('study','previous','output'):p.add_argument('--'+key,type=Path,required=True)
    run(p.parse_args())
