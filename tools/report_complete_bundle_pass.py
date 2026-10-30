"""Complete the frozen group pass and publish qualified and rejected additions."""
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
from report_predictive_covariance_transfer import compact_replays


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();hashes={};verified={};evidence={}
    def load(p):
        d=read(p);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();evidence[str(p)]=compact_replays(compact_evidence(d))
        if isinstance(d,dict):
            for name,digest in d.get('source_hashes',{}).items():
                if name not in verified:verified[name]=hashlib.sha256(Path(name).read_bytes()).hexdigest()
                if verified[name]!=digest:raise ValueError('source changed: '+name)
        return d
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    root=s/'graph-bundle-remaining-annotation-v1';pr=load(root/'protocol.json');execution=load(root/'execution.json')
    assert len(execution)==27 and all(r['status']=='complete' for r in execution)
    annotations=[];new_byid={};executions=[]
    for b in pr['jobs']:
        bid=b['bundle_id'];r=load(root/bid/'result.json');load(root/bid/'protocol.json');term=load(root/(bid+'-terminal.json'))
        executions.append(dict(group='annotation',bundle=bid,stage='annotation',status=term['status'],seconds=term['seconds']))
        a=r['annotation'];row=dict(bundle=bid,scan=b['job']['label'],points=b['points'],status=a['status'],norad=a['norad'],
            minimum_margin=a.get('minimum_margin'),member_identity_pass=r['bundle_member_checks']['passed'],source=str(root/bid/'result.json'))
        annotations.append(row);new_byid[bid]=row
    csvout('new_annotations.csv',annotations)
    trials=s/'graph-bundle-remaining-inclusion-v1';jobs=load(trials/'protocol.json')['jobs'];load(trials/'execution.json')
    comparisons=[];members=[];split_rows=[];physical=[];accepted=[];plots=[];qualified_byid={}
    for job in jobs:
        b=job['bundle'];bid=b['bundle_id'];folder=trials/bid;terminal=load(trials/(bid+'-terminal.json'))
        for stage in terminal['stages']:executions.append(dict(group='inclusion',bundle=bid,**stage))
        split=load(folder/'split/result.json');load(folder/'split/protocol.json');split_rows.extend(dict(bundle=bid,**r) for r in split['rows'])
        assert split['all_support_shared']
        trial=folder/'trial';protocol=load(trial/'protocol.json');control=load(trial/'control.json');addition=load(trial/'new_family.json');audit=load(trial/'exact_owner_replay.json');member=load(folder/'member_audit.json')
        qualified=member['qualified_research_candidate'];qualified_byid[bid]=qualified
        members.extend(dict(bundle=bid,**{k:v for k,v in r.items() if k not in ('times_s','residual_hz','noise')},**r['noise']) for r in member['rows'])
        inv=load(Path(b['inventory']));den=inv['summary'][0]['total_GLRT'];row=dict(bundle=bid,scan=b['job']['label'],norad=job['norad'],points=b['points'],qualified=qualified)
        for arm,v in addition['arms'].items():
            c=control['arms'][arm];row.update({arm+'_control_km':error(c),arm+'_addition_km':error(v)})
            cids=set(c['proposed_associated_ids']);aids=set(v['proposed_associated_ids']);target=set(o for e in protocol['targets'] for o in e['observation_ids'])
            assert len(target)==b['points'] and len(target&cids)==0
            if qualified:assert aids-cids==target and not cids-aids
            physical.append(dict(bundle=bid,scan=b['job']['label'],norad=job['norad'],arm=arm,qualified=qualified,
                baseline_points=len(cids),proposed_points=len(aids),target_points=len(target),credited_target_points=len(target) if qualified else 0,
                baseline_percent=100*len(cids)/den,proposed_percent=100*len(aids)/den,total_GLRT=den,
                RMS_hz=v['family']['diagnostics'][0]['profile_RMS_hz'],
                maximum_absolute_residual_hz=float(np.max(abs(np.array(v['family']['diagnostics'][0]['raw_residual_hz'])-v['family']['diagnostics'][0]['profile_bias_hz']))),optimizer_success=v['history'][-1]['success'],
                phase_gap_s=v['final_phase_change_s'],quadrature_pass=v['phase_resolution_audit']['local_agreement'],
                **v['family']['diagnostics'][0]['noise']))
        comparisons.append(row)
        if qualified:accepted.append((b,protocol,addition,folder));plots.append((b,addition))
    csvout('position_comparison.csv',comparisons);csvout('physical_checks.csv',physical);csvout('member_checks.csv',members);csvout('split_identity.csv',split_rows);csvout('executions.csv',executions)
    # Check which accepted measurements were already in the previous joint recovery.
    previous_joint=s/'predictive-ceb24498-joint63388-refined-v1/trial/protocol.json'
    if not previous_joint.exists():raise ValueError('prior joint recovery provenance missing')
    old=load(previous_joint);oldids=set(o for t in old['targets'] for o in t['observation_ids'])
    recovered=[]
    for b,p,a,folder in accepted:
        ids=set(o for t in p['targets'] for o in t['observation_ids']);overlap=ids&oldids
        if b['job']['label']=='AUTO-ceb24498':assert ids==oldids
        recovered.append(dict(bundle=b['bundle_id'],scan=b['job']['label'],norad=p['targets'][0]['norad'],qualified_points=len(ids),
            previously_qualified_63388_points=len(overlap),newly_qualified_points=len(ids-overlap),source=str(folder/'trial')))
    csvout('qualified_recoveries.csv',recovered)
    groupfile=args.previous/'group_status.csv';hashes[str(groupfile)]=hashlib.sha256(groupfile.read_bytes()).hexdigest();groups=list(csv.DictReader(groupfile.open()))
    for g in groups:
        bid=g['bundle']
        if bid in new_byid:g.update({k:new_byid[bid][k] for k in ('status','norad','source')})
        else:load(Path(g['source']))
        g['this_iteration_position_status']='qualified_research_candidate' if qualified_byid.get(bid) else ('position_rejected' if bid in qualified_byid else 'not_position_tested_this_iteration')
    assert len(groups)==35 and all(g['status']!='not_group_annotated' for g in groups)
    csvout('group_status.csv',groups)
    ledgerpath=args.previous/'annotation_ledger.csv';hashes[str(ledgerpath)]=hashlib.sha256(ledgerpath.read_bytes()).hexdigest();ledger=list(csv.DictReader(ledgerpath.open()));byid={r['track_id']:r for r in ledger}
    assert len(byid)==len(ledger)==1630
    # Group qualification is separate from the earlier single-fragment result.
    for b,p,a,folder in accepted:
        for m in b['members']:
            byid[m['track_id']].update(bundle_research_id=b['bundle_id'],bundle_research_norad=p['targets'][0]['norad'],
                bundle_research_inclusion='RF_verified_joint_candidate; not production promoted',bundle_inclusion_source=str(folder/'trial'))
    csvout('annotation_ledger.csv',ledger)
    native=load(s/'bundle-63381-native-audit-v1/result.json');native_rows=[]
    for arm in native['arms']:
        for m in arm['members']:
            native_rows.append(dict(arm=arm['arm'],member=m['member'],points=m['orbital_same_bundle_bias']['points'],
                polynomial_RMS_hz=m['original_polynomial']['RMS_hz'],orbital_RMS_hz=m['orbital_same_bundle_bias']['RMS_hz'],
                orbital_lag1=m['orbital_same_bundle_bias']['noise']['lag1_acf']))
    csvout('63381_fragment_audit.csv',native_rows)
    summary=dict(new_annotation_statuses=dict(Counter(r['status'] for r in annotations)),all_group_statuses=dict(Counter(r['status'] for r in groups)),
        frozen_groups=35,group_annotations_complete=True,position_trials=len(jobs),qualified_trials=len(accepted),
        qualified_points=sum(r['qualified_points'] for r in recovered),previously_qualified_points=sum(r['previously_qualified_63388_points'] for r in recovered),
        newly_qualified_points=sum(r['newly_qualified_points'] for r in recovered),individual_inventory_rows=len(ledger),production_changed=False,
        entire_large_curve_goal_complete=False,verified_source_hashes=len(verified))
    fig,axs=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        x=np.arange(len(comparisons));ax.barh(x-.17,[r[arm+'_control_km'] for r in comparisons],.34,color='#888',label='Matched control')
        ax.barh(x+.17,[r[arm+'_addition_km'] for r in comparisons],.34,color=['#009e73' if r['qualified'] else '#d55e00' for r in comparisons],label='Addition (green qualifies)')
        ax.set(yticks=x,yticklabels=[f"{r['scan']} / {r['norad']}" for r in comparisons],xlabel='Evaluation position error (km)',title=arm);ax.invert_yaxis();ax.grid(axis='x',alpha=.2);ax.legend(fontsize=8)
    save(fig,'position_trials.png')
    fig,axs=plt.subplots(len(plots),2,figsize=(14,4*len(plots)),layout='constrained',squeeze=False)
    for row,(b,a) in zip(axs,plots,strict=True):
        fit=b['nomination'];t=np.array(fit['times_s']);y=np.array(fit['aligned_values_hz']);mi=np.array(fit['member_indices'])
        for k in range(len(b['members'])):row[0].scatter(t[mi==k],y[mi==k]/1000,s=13,label=f'Fragment {k+1}')
        for arm,color in [('c0','#0072b2'),('fitted_c','#d55e00')]:
            d=a['arms'][arm]['family']['diagnostics'][0];r=np.array(d['raw_residual_hz'])-d['profile_bias_hz'];row[1].plot(d['times_s'],r,'.-',lw=.6,c=color,label=arm)
        row[0].set(title=f"{b['job']['label']} / {b['points']} points",xlabel='Time (s)',ylabel='Alias-aligned native CFO (kHz)');row[1].set(title='Qualified residuals, one common group bias',xlabel='Time (s)',ylabel='Residual (Hz)');row[1].axhline(0,c='k',lw=.5)
        for ax in row:ax.legend(fontsize=8);ax.grid(alpha=.2)
    save(fig,'qualified_curves.png')
    fig,axs=plt.subplots(1,2,figsize=(13,4),layout='constrained')
    for k,m in enumerate(next(a for a in native['arms'] if a['arm']=='fitted_c')['members']):axs[0].plot(m['times_s'],m['residual_hz'],'.-',lw=.6,label=f'Original fragment {k+1}')
    points=native['observations'];axs[1].plot([r['time_s'] for r in points],[r['uniform_timing_shift_hz'] for r in points],'.',label='Uniform-frame centroid')
    axs[1].plot([r['time_s'] for r in points],[r['maximum_support_timing_shift_hz'] for r in points],lw=.8,label='Maximum within-support first-order bound')
    axs[0].set(title='63381: structure exists in original fragments',xlabel='Time (s)',ylabel='Orbital residual (Hz)');axs[1].set(title='Timing sensitivity; no measurement changed',xlabel='Time (s)',ylabel='Expected CFO change (Hz)')
    for ax in axs:ax.axhline(0,c='k',lw=.5);ax.legend(fontsize=8);ax.grid(alpha=.2)
    save(fig,'63381_native_audit.png')
    write(out/'summary.json',summary);write(out/'sources.json',dict(report_sources=hashes,verified_upstream_sources=verified))
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    qualified_table=[r for r in comparisons if r['qualified']]
    coverage=[r for r in physical if r['qualified'] and r['arm']=='fitted_c']
    text=f'''# Completed fragment-group annotation pass and qualified position additions

All **35 frozen geometric groups** now have an annotation result. The remaining 27-group batch produced eight supported identities; all eight survived the separate-fragment satellite challenge. **Three position trials pass** pooled and member residual checks, phase-grid checks, exact orbit replay and ownership preservation. They contain 182 points: **130 newly qualified points**, plus the already-qualified 52-point 63388 recovery tested here as one common-bias group. These are research inclusions, not a production rollout or ALGO promotion. Completing this grouping pass does not complete the full 1,630-curve objective.

## Systematic selection and identity safeguards

Every remaining group in the frozen inventory was evaluated, ordered by point count, with eight workers and 600-second case limits. Selection uses no GPS or satellite label. Each group keeps all native observations and integer alias lifts. Three timestamp-selected randomized scanwide 12-second partitions with two-second guards assess pooled and member-specific identity. Six bounded causal candidate nominations are used per fold. Both c arms use the same candidate set, priors and budgets.

New-batch outcomes: **{dict(Counter(r['status'] for r in annotations))}**. Six groups fail member-specific support even when pooling appears convincing; nine switch identity between partitions. The 35-group inventory is in [group_status.csv](group_status.csv), and new results are in [new_annotations.csv](new_annotations.csv). Annotation outcomes include unresolved and rejected hypotheses; they are not 35 confirmed satellites.

For the eight supported groups, each fragment is challenged with independently nominated competing satellites. This adversarial search may use held frequencies to nominate counterexamples; fitting still uses training observations. It is conditional model checking, not an unbiased full-catalogue posterior. All eight pass every available member check, with coverage for both members and both c arms. [split_identity.csv](split_identity.csv) retains the individual margins.

## Position inclusion, with matched c ablation

All eight candidates use the new/uncalibrated-family causal phase-mixture route. Each has one satellite identity and one shared curve constant, with physical orbital and receiver uncertainty integrated. They do not alter receiver calibration equations at a fixed position. Each control/addition starts at the same center of a 25×25 km box; both c arms have five phase-refresh rounds and matching optimizer budgets. A predeclared 0.025-second phase grid avoids the earlier coarse-grid issue; local score/gradient checks compare half and quarter spacing. All 16 addition-arm numerical audits pass. Future TLEs and true GPS are excluded from inference; the supplied true site is used only for error reporting.

After fitting, every member is checked with the **same fitted group bias**, without per-member rebiasing. Mean, trend, quadratic, step, correlation, RMS and physical gates remain unchanged. Nominal and continuously refined phase predictions must pass for every member in both arms. Exact incumbent-family replay and ownership checks must also pass. A good fragment cannot conceal a weak neighbor, and a member pass cannot override whole-group failure.

{table(comparisons,['scan','norad','points','qualified','c0_control_km','c0_addition_km','fitted_c_control_km','fitted_c_addition_km'])}

![All matched position trials](figures/position_trials.png)

The five rejections retain structured target residuals. Two also report an optimizer failure in one arm; these are not numerical-only failures, so no optimizer retry is used to disguise the physical discrepancy. Some rejected trials improve evaluation error substantially; GPS improvement does not determine acceptance. The 56816 group passes separate member checks but fails pooled correlation/step checks, demonstrating why both levels are needed.

## Qualified recoveries and coverage

{table(qualified_table,['scan','norad','points','c0_control_km','c0_addition_km','fitted_c_control_km','fitted_c_addition_km'])}

{table(coverage,['scan','baseline_points','proposed_points','total_GLRT','baseline_percent','proposed_percent'])}

![Qualified curves and residuals](figures/qualified_curves.png)

AUTO-e32d57a7 adds 69 points assigned to 67634, improving error by about 244–253 metres. DS24-0091 adds 61 points assigned to 67700, with error essentially unchanged and slightly worse (about 2–5 metres). This is a valid association recovery without a demonstrated localization gain. AUTO-ceb24498's 52-point 63388 group reproduces previously qualified measurements; exact ID-set equality against the earlier joint trial prevents double counting. Its common-bias grouping is a different model from two independently biased fragments, so small endpoint differences are expected. The totals are across separate scans and cannot be treated as one joint position fit.

The 67634 plot retains an isolated roughly 430 Hz residual near the start. It passes the predeclared group/member screens, but qualification is not proof that every point has the correct source. No outlier is clipped or hidden. The maximum residual is recorded in the physical-check table; native-point and influence checks remain appropriate before promoting this research recovery.

[qualified_recoveries.csv](qualified_recoveries.csv) distinguishes newly qualified from repeated points. The 1,630-row [individual ledger](annotation_ledger.csv) keeps previous single-fragment results and adds separate group-inclusion fields for the six members of qualified groups. Position and annotation statuses remain separate. This research state must still be integrated and evaluated scan-wide before production promotion.

## 63381: native provenance, fragment structure and timing

The earlier 96-point 63381 group remains rejected. Every exported observation is replayed from the original tracking contract's gated maximum-margin candidate. Each graph value equals that native GLRT CFO plus an integer alias; timestamps and observation order match exactly. No polynomial-smoothed replacement values entered the position trial. Both original fragments have one polynomial piece, so this is not a hidden many-piece construction.

{table(native_rows,['arm','member','points','polynomial_RMS_hz','orbital_RMS_hz','orbital_lag1'])}

![Native fragment and timing audit](figures/63381_native_audit.png)

Orbital residual structure exists in both original fragments separately. This excludes joining as the sole source of that structure, but does not prove the common-satellite model is complete. Near-time one-to-one pairs (25 pairs within 1.5 seconds) have only about 0.26 residual correlation and about 78 Hz difference RMS, so neither a perfectly shared receiver fluctuation nor a single smooth orbital correction explains all the discrepancy.

Using each archived epoch and the GLRT's pilot-symbol/frame sample support, the uniform-frame centroid sensitivity changes expected CFO by at most **{native['maximum_uniform_timing_shift_hz']:.2f} Hz**. The maximum first-order change anywhere within the sampled pilot support is **{native['maximum_support_timing_shift_hz']:.2f} Hz**. These use the original polynomial derivative; actual IQ frame weights are unknown. They are sensitivity bounds, not a timestamp calibration or absolute-clock audit. The ordinary probe-midpoint approximation is therefore not supported as the sole explanation for the roughly 71 Hz pooled residual scatter.

The current GLRT implementation uses a discrete CFO search, but the exported winning-candidate contract lacks the acquired-CFO/scout values needed to attribute this track's residual to a particular frequency bin. A native-IQ remeasurement would be needed to test that mechanism here. Earlier raw-pilot work on a different scan found only a partial scatter reduction, so it should not be assumed to solve 63381.

## Remaining work

This pass establishes a reproducible route from full-inventory geometric groups through guarded identity checks to position inclusion. It does not resolve every large curve: ambiguous identities, insufficient member evidence and systematic residuals remain. Continue with independent receiver/satellite evidence and bounded native-pilot diagnostics for those failure classes. Keep the new 67634 and 67700 recoveries in the research inclusion registry, evaluate them alongside existing per-scan recoveries without duplicate observations, and validate aggregate behavior before promotion. Do not relax residual gates or use GPS to choose which associations survive.

## Validation and provenance

All 27 annotation cases and all eight split/inclusion/replay pipelines finish. Twenty-one targeted tests pass, including the new pilot-support geometry and exhaustive member-qualification tests, plus bundle, alias and conditional-likelihood tests. Raw trials remain immutable. [executions.csv](executions.csv), [sources.json](sources.json), [evidence.json.gz](evidence.json.gz), [physical_checks.csv](physical_checks.csv) and [member_checks.csv](member_checks.csv) retain the receipts and evidence. The report generator verifies source hashes, all 35 group statuses, target ownership and exact overlap with the earlier 63388 recovery. No RF was collected or recording modified.
'''
    (out/'README.md').write_text(text);print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
