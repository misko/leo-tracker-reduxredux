"""Publish bundle hypotheses, independent-label challenges and matched trials."""
import argparse,csv,gzip,hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays
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
    discovery=load(s/'predictive-graph-bundles-v1.json');root=s/'predictive-graph-bundle-annotation-v1'
    load(root/'protocol.json');load(root/'execution.json');annotations=[];member_votes=[];plots=[]
    for b in discovery['bundles']:
        bid=b['bundle_id'];term=load(root/(bid+'-terminal.json'));executions.append(dict(group='annotation',**term));assert term['status']=='complete'
        r=load(root/bid/'result.json');pr=load(root/bid/'protocol.json');a=r['annotation'];checks=r['bundle_member_checks']
        annotations.append(dict(bundle=bid,scan=b['job']['label'],points=b['points'],members=';'.join(m['track_id'] for m in b['members']),
            degree=b['nomination']['degree'],nomination_RMS_hz=b['nomination']['RMS_hz'],second_alias_lift=b['members'][1]['alias_lift'],
            status=a['status'],norad=a['norad'],pooled_minimum_margin=a.get('minimum_margin'),member_checks_pass=checks['passed']))
        member_votes.extend(dict(bundle=bid,scan=b['job']['label'],**v) for v in checks['votes']);plots.append((b,r,pr))
    csvout('bundle_annotations.csv',annotations);csvout('member_votes.csv',member_votes)
    root=s/'predictive-graph-bundle-split-identity-v1';load(root/'protocol.json');load(root/'execution.json');split_rows=[]
    for b in load(root/'protocol.json')['jobs']:
        bid=b['bundle_id'];executions.append(dict(group='split_identity',**load(root/(bid+'-terminal.json'))));load(root/bid/'protocol.json')
        result=load(root/bid/'result.json');split_rows.extend(dict(bundle=bid,**r) for r in result['rows'])
        for path in sorted((root/bid).glob('seed-*.json')):load(path)
    csvout('split_identity.csv',split_rows)
    comparisons=[];trials=[];failure_rows=[];diagnostics=[]
    def position(label,folder,scan,norad):
        pr=load(folder/'protocol.json');c=load(folder/'control.json');a=load(folder/'new_family.json');audit=load(folder/'exact_owner_replay.json')
        qualified=bool(c['paired_valid'] and a['paired_valid'] and audit['all_verified']);target=set(o for t in pr['targets'] for o in t['observation_ids'])
        row=dict(variant=label,scan=scan,norad=norad,points=len(target),RF_qualified=qualified)
        inv=load(s/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');den=inv['summary'][0]['total_GLRT']
        for arm in ('c0','fitted_c'):row.update({arm+'_control_km':error(c['arms'][arm]),arm+'_addition_km':error(a['arms'][arm])})
        comparisons.append(row)
        for role,pair in [('control',c),('new_family',a)]:
            for arm,v in pair['arms'].items():
                replay=next(r for r in audit['rows'] if (r['role'],r['arm'])==(role,arm));slacks=replay_slacks(replay)
                old=set(c['arms'][arm]['proposed_associated_ids']);ids=set(v['proposed_associated_ids']);last=v['history'][-1];changes=replay['incumbent_ownership_changes']
                trials.append(dict(variant=label,role=role,arm=arm,error_km=error(v),points=len(ids),percent=100*len(ids)/den,target_added=len((ids-old)&target),
                    incidental_added=len((ids-old)-target),lost=len(old-ids),paired_valid=pair['paired_valid'],exact_verified=replay['verified'],RF_qualified=qualified,
                    missing_owners=sum(r['after'] is None for r in changes),changed_owners=sum(r['after'] is not None for r in changes),
                    minimum_incumbent_slack=min(slacks.values()),optimizer_success=last['success'],optimizer_message=last['message'],
                    objective=v['negative_twice_elbo'],phase_gap_s=v['final_phase_change_s'],quadrature_pass=v.get('phase_resolution_audit',{}).get('local_agreement')))
                for gate,slack in slacks.items():
                    if slack<0:failure_rows.append(dict(variant=label,role=role,arm=arm,gate=gate,slack=slack))
                if role=='new_family':
                    for d in v['family']['diagnostics']:
                        diagnostics.append(dict(variant=label,arm=arm,**d))
                        n=d['noise'];ratios=dict(mean=n['mean_z']/3,slope=n['slope_z']/3,quadratic=n['quadratic_bic_gain']/10,step=n['maximum_step_z']/4,lag1=abs(n['lag1_acf'])/(4/np.sqrt(len(d['times_s']))))
                        for key,value in ratios.items():
                            if value>1:failure_rows.append(dict(variant=label,role=role,arm=arm,gate='target/'+key,slack=1-value))
    p=s/'predictive-queue36-inclusion-v1/51e2e62b59ea4572676b/trial';position('69525 original',p,'AUTO-26dcef1d',69525)
    for name,label,scan,norad in [('predictive-69525-optimizer-followup-v1','69525 Powell','AUTO-26dcef1d',69525),
                                ('predictive-graph-bundle-optimizer-v1','59326 bundle Powell','AUTO-2f13639a',59326)]:
        root=s/name;load(root/'protocol.json');execution=load(root/'execution.json');assert execution['status']=='complete'
        for stage in execution['stages']:executions.append(dict(group=label,**load(root/(stage['stage']+'-terminal.json'))))
        position(label,root/'trial',scan,norad)
    root=s/'predictive-graph-bundle-inclusion-v1';load(root/'protocol.json');cases=load(root/'execution.json')
    for case in cases:
        assert case['status']=='complete' and not case['shared_family'];folder=root/case['job']['bundle_id']
        for stage in case['stages']:executions.append(dict(group='bundle_position',**load(folder/(stage['stage']+'-terminal.json'))))
        position('59326 bundle original',folder/'trial',case['job']['job']['label'],59326)
    csvout('comparison.csv',comparisons);csvout('position_trials.csv',trials);csvout('failed_gates.csv',failure_rows);csvout('executions.csv',executions)
    # Keep prior per-curve identity roles unchanged; bundle hypotheses are a separate table.
    prior=args.previous/'annotation_ledger.csv';hashes[str(prior)]=hashlib.sha256(prior.read_bytes()).hexdigest();ledger=list(csv.DictReader(prior.open()))
    for row in ledger:
        if row['track_id']=='51e2e62b59ea4572676b':
            row.update(predictive_inclusion_source=str(s/'predictive-69525-optimizer-followup-v1/trial'),predictive_research_inclusion='RF_verified_candidate; matched optimizer follow-up; not production promoted')
    csvout('annotation_ledger.csv',ledger)
    fig,axs=plt.subplots(len(plots),2,figsize=(14,4*len(plots)),squeeze=False,layout='constrained')
    for pair,(b,r,pr) in zip(axs,plots,strict=True):
        fit=b['nomination'];times=np.array(fit['times_s']);values=np.array(fit['aligned_values_hz']);labels=[]
        inv=load(Path(b['inventory']));tracks=load(Path(inv['job']['root'])/inv['job']['case']/'tracks.json')
        for k,m in enumerate(b['members']):labels.extend([k]*len(tracks[m['track_index']]['times']))
        labels=np.array(labels)
        for k,m in enumerate(b['members']):pair[0].scatter(times[labels==k],values[labels==k]/1000,s=13,label='Fragment '+str(k+1))
        order=np.argsort(times);pair[0].plot(times[order],(values-np.array(fit['residual_hz']))[order]/1000,'k--',lw=.8,label='Nomination polynomial')
        pair[0].set(title=b['job']['label']+' / '+str(b['points'])+' points',xlabel='Time (s)',ylabel='Alias-aligned CFO (kHz)');pair[0].legend(fontsize=8)
        votes=r['bundle_member_checks']['votes']
        for arm,offset,color in [('c0',-.1,'#0072b2'),('fitted_c',.1,'#d55e00')]:
            rows=[v for v in votes if v['arm']==arm];pair[1].scatter([v['margin'] for v in rows],np.arange(len(rows))+offset,c=color,label=arm)
        pair[1].axvline(10,c='k',ls='--');pair[1].set_xscale('symlog',linthresh=10);pair[1].set(xlabel='Member margin against shared-label competitors',ylabel='Member / held-block check',title=r['annotation']['status']);pair[1].legend(fontsize=8)
        for ax in pair:ax.grid(alpha=.2)
    save(fig,'bundle_candidates.png')
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        x=np.arange(len(comparisons));ax.bar(x-.18,[r[arm+'_control_km'] for r in comparisons],.35,color='#888',label='Matched control')
        ax.bar(x+.18,[r[arm+'_addition_km'] for r in comparisons],.35,color=['#009e73' if r['RF_qualified'] else '#d55e00' for r in comparisons],label='Proposed addition')
        ax.set(xticks=x,xticklabels=[r['variant'] for r in comparisons],ylabel='Evaluation error (km)',title=arm);ax.tick_params(axis='x',labelrotation=30);ax.legend();ax.grid(axis='y',alpha=.2)
    fig.suptitle('Green qualifies; orange remains rejected. Each optimizer has its own matched control.')
    save(fig,'position_trials.png')
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for arm,color in [('c0','#0072b2'),('fitted_c','#d55e00')]:
        d=next(d for d in diagnostics if d['variant']=='69525 Powell' and d['arm']==arm)
        t=np.array(d['times_s']);y=np.array(d['CFO_hz']);res=np.array(d['raw_residual_hz'])-d['profile_bias_hz']
        if arm=='c0':axs[0].scatter(t,y/1000,c='k',s=14,label='Original GLRT')
        axs[0].plot(t,(y-res)/1000,c=color,label=arm+' satellite + profiled offset')
        axs[1].plot(t,res,'.-',c=color,label=arm)
    axs[0].set(xlabel='Time (s)',ylabel='CFO (kHz)',title='69525 / 25-point numerical recovery')
    axs[1].set(xlabel='Time (s)',ylabel='Profile residual (Hz)',title='Residuals under unchanged gates');axs[1].axhline(0,c='k',lw=.6)
    for ax in axs:ax.legend(fontsize=8);ax.grid(alpha=.2)
    save(fig,'numerical_recovery_curve.png')
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained');step_rows=[]
    bundle=next(t for t in plots if t[0]['bundle_id']=='5f24814427ef8860cf0e');membership=np.array(bundle[2]['target']['member_indices'])
    for arm,color in [('c0','#0072b2'),('fitted_c','#d55e00')]:
        d=next(d for d in diagnostics if d['variant']=='59326 bundle Powell' and d['arm']==arm);t=np.array(d['times_s']);res=np.array(d['raw_residual_hz'])-d['profile_bias_hz']
        for k in range(2):axs[0].scatter(t[membership==k],res[membership==k],marker='o' if k==0 else '^',c=color,s=18,label=arm+' fragment '+str(k+1))
        splits=np.arange(4,len(t)-3);jump=np.cumsum(res)[splits-1]/splits-(res.sum()-np.cumsum(res)[splits-1])/(len(t)-splits)
        z=abs(jump)/(max(np.std(res,ddof=1),75)*np.sqrt(1/splits+1/(len(t)-splits)));idx=int(np.argmax(z));k=int(splits[idx])
        axs[1].plot((t[splits-1]+t[splits])/2,z,c=color,label=arm)
        step_rows.append(dict(arm=arm,maximum_z=float(z[idx]),left_time_s=t[k-1],right_time_s=t[k],left_points=k,
            left_member0=int(sum(membership[:k]==0)),left_member1=int(sum(membership[:k]==1)),left_minus_right_mean_hz=jump[idx],RMS_hz=d['profile_RMS_hz']))
    axs[0].axhline(0,c='k',lw=.5);axs[1].axhline(4,c='k',ls='--',label='Unchanged gate')
    axs[0].set(xlabel='Time (s)',ylabel='Profile residual (Hz)',title='59326 union: first/second fragment markers')
    axs[1].set(xlabel='Candidate split time (s)',ylabel='Cumulative two-side mean contrast z',title='Maximum occurs inside the first fragment')
    for ax in axs:ax.legend(fontsize=8);ax.grid(alpha=.2)
    save(fig,'bundle_residual_step.png');csvout('step_location.csv',step_rows)
    fig,ax=plt.subplots(figsize=(11,4),layout='constrained')
    for arm,off,color in [('c0',-.1,'#0072b2'),('fitted_c',.1,'#d55e00')]:
        rr=[r for r in split_rows if r['arm']==arm];ax.scatter([r['alternative_minus_shared'] for r in rr],np.arange(len(rr))+off,c=color,label=arm)
    ax.axvline(10,c='k',ls='--');ax.set(xlabel='Best independent satellite score minus shared 59326 score',ylabel='Member / held-block check',title='Positive favors shared identity; bounded adversarial competitor search');ax.legend();ax.grid(alpha=.2)
    save(fig,'split_identity.png')
    summary=dict(bundle_inputs=discovery['short_fragment_inputs'],bundles=len(annotations),scans=len({r['scan'] for r in annotations}),
        supported_bundles=sum(r['status']=='conditionally_supported_identity' for r in annotations),
        position_configurations=len(comparisons),RF_qualified_configurations=sum(r['RF_qualified'] for r in comparisons),
        split_identity_checks=len(split_rows),all_split_checks_support_shared=all(r['supports_shared'] for r in split_rows),production_changed=False)
    write(out/'summary.json',summary)
    text=f'''# Fragment bundles, independent-label challenges and numerical recovery

This iteration tests whether incomplete graph fragments can supply useful evidence together. Four same-lane pair hypotheses are frozen from 105 recently assessed curves lacking enough independent partitions. One 50-point bundle supports satellite **59326**, including an adversarial search for different labels on its two fragments, but remains **rejected for position inclusion**. Separately, a numerical-only retry recovers a **25-point curve assigned to 69525**, improving error in both c arms. No production promotion or gate relaxation.

## Grouping supplies missing time coverage without inventing observations

Pairs must share RX, channel and RF, have disjoint observation IDs and distinct timestamps, contain no points owned in either c arm, and overlap or be separated by at most 12 s. At least three 12 s timestamp blocks must be present in the union. Nomination fits order 1–4 polynomials, penalizes order with BIC using a fixed 150 Hz floor, and requires RMS below 250 Hz. Relative alignment changes only an integer multiple of the native alias period (1/4.4 microseconds); no continuous per-fragment frequency shift is fitted into the observations. The original graph, calibration rows, timestamps, IDs and receiver basis rows remain unchanged. The appended view is predictive-only.

The pair nomination uses the frozen graph's full CFO data. Subsequent evidence is therefore **conditional on that graph and nominated grouping**, not an independent validation of the grouping procedure. No satellite ID or GPS error selects the four pairs. Their overlapping memberships are explicit; counts cannot be added across configurations.

{table(annotations,['scan','bundle','points','degree','nomination_RMS_hz','second_alias_lift','status','norad','member_checks_pass'])}

![Bundle curves and member checks](figures/bundle_candidates.png)

## A strong fragment must not hide a weak neighbor

Each union receives three distinct timestamp-selected random scanwide 12 s holdouts with 2 s guards. Receiver calibration and predictive distributions use training data only. The same causal candidates, priors and budgets are used in c=0 and fitted-c. In addition to pooled identity consensus, every member must have at least one held evaluation with four points in both arms. Every available member check must favor the common identity by at least 10 units of negative twice log predictive density, with held RMS at most 450 Hz. These are conditional comparisons under a common-label model, not posterior probabilities.

For AUTO-3dabeeab, pooling the 23-point and 20-point fragments supports 100412, but the short member's margins are only **1.94 / 2.73**, below 10. The member veto rejects this extension. It does not revoke the previous 23-point result or prove its satellite label wrong. The two AUTO-3ec63849 pairs remain unstable or ambiguous. Only AUTO-2f13639a, with **21 + 29 points** and one integer alias alignment, survives the member checks.

## Challenge the assumption that both fragments share one satellite

For the surviving 59326 bundle, each held member is also scored under independent satellite hypotheses, conditioning only on that member's training observations rather than on its partner. Receiver fits are reconstructed and shared predictive scores replay to tolerance. Six candidates per member are nominated from the causal bank over the existing regional search. This adversarial competitor screening **uses held frequencies**; it is explicitly model search, not an unbiased held-out performance estimate. Three integer aliases centered on the inherited alias are marginalized with equal prior weight rather than selected by held RMS. No GPS is used. The search remains bounded and does not prove exhaustive catalogue uniqueness.

![Independent-label challenge](figures/split_identity.png)

All **{len(split_rows)} member/arm/block comparisons** favor shared 59326 by at least **{min(r['alternative_minus_shared'] for r in split_rows):.2f}** score units. The closest independent alternatives include 63670, 66344 and 58385. This strengthens the identity hypothesis; it does not remove the residual-model failure below. [Every comparison](split_identity.csv) and the candidate evidence are retained.

## Position inclusion separates numerical and physical failures

{table(comparisons,['variant','scan','points','c0_control_km','c0_addition_km','fitted_c_control_km','fitted_c_addition_km','RF_qualified'])}

![Matched position trials](figures/position_trials.png)

The existing **69525 / AUTO-26dcef1d** candidate already passed exact replay, physical gates and phase-integration checks but its L-BFGS-B addition optimizer reported failure. Repeating both control and addition with Powell, from the same regional center and with unchanged 48-iteration / 240-evaluation limits per phase round, resolves that numerical failure. The qualified recovery adds 25 points, with no losses or incumbent owner changes. Error changes **0.453 → 0.397 km** for c=0 and **0.497 → 0.424 km** for fitted-c. This follow-up was selected by execution/gate evidence, not by GPS improvement.

![Numerically recovered curve and prediction](figures/numerical_recovery_curve.png)

The **59326 bundle** initially has an unsuccessful fitted-c control optimizer and a c=0 target residual failure. Powell resolves the control convergence issue but does not resolve the target structure. Both optimizer trials remain visible. The residual RMS is low, about **66 Hz / 60 Hz**, yet the c=0 maximum cumulative mean contrast is **4.080**, above the unchanged limit of 4. Fitted-c is about **2.649** and passes this statistic. Other retained-family exact slacks do not fail, and no observations or owners are lost. Thus this is a supported candidate identity with an unresolved shared-model discrepancy, not a reason to force acceptance.

![Residual contrast and source fragments](figures/bundle_residual_step.png)

The largest contrast separates the first eight points from the remaining 42, between **38.37 and 39.79 s**, about **118 Hz** in c=0. Those eight points all belong to the first fragment; the maximum is **not at the join between the two source fragments**. This weakens a simple bad-join explanation. The cumulative statistic does not prove an instantaneous receiver step; smooth model error or correlated residuals can also produce it. A new receiver or satellite correction needs independent evidence. We do not fit a correction merely to lower this statistic.

## Reproducibility and next work

All position controls/additions start at the same 25 × 25 km regional box center (37.906, −122.545). GPS 37.849061591561885, −122.48574968092912 is used only for error reporting. All inference uses causal TLEs. Exact replay substitutes one incumbent family at a time rather than jointly refitting all exact orbits. Each independent stage is bounded to 600 s. No collection or production setting changes. The new-family bundle route is exercised end to end here; bundle reconstruction for an already calibrated shared family is implemented but has not yet been exercised by a supported real-data bundle in this iteration.

The updated [1,630-entry ledger](annotation_ledger.csv) preserves individual annotation roles; bundle hypotheses are separate, so a pooled identity cannot silently overwrite a member's unresolved status. The numerical recovery updates only its own research-inclusion entry. [Trial metrics](position_trials.csv), [failed gates](failed_gates.csv), [execution receipts](executions.csv), [source hashes](sources.json) and [compact evidence](evidence.json.gz) accompany the figures. Passing inference checks alone does not establish dataset-wide localization improvement.

Next work should test consistent groups of more than two fragments, expand discovery beyond this 105-curve subset, retain independent-label challenges, and seek cross-family evidence for the 59326 residual discrepancy. The full goal remains incomplete: many short, ambiguous or model-mismatched curves still lack a justified inclusion. The targeted suite passes **63 tests**, including immutable reconstruction, owner protection, alias invariance, member veto and existing family/phase checks.
'''
    (out/'README.md').write_text(text)
    for name in ('predictive_graph_bundle.py','discover_predictive_graph_bundles.py','audit_bundle_split_identity.py','annotate_predictive_only.py','include_predictive_annotations.py','include_new_predictive_family.py','audit_predictive_family_inclusion.py','audit_shared_predictive_inclusion.py','report_predictive_graph_bundles.py'):
        p=Path(__file__).with_name(name);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    print(summary,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
