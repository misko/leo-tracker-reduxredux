"""Report explicit phase retention, its counterexample and the bounded inventory."""
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


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=args.refresh);(out/'figures').mkdir(exist_ok=args.refresh)
    evidence={};hashes={}
    def load(path):
        path=Path(path);hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();r=read(path);evidence[str(path)]=r;return r
    def csvout(name,rows):
        if not rows:return
        with (out/name).open('w' if args.refresh else 'x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    audit=load(s/'native-explicit-phase-audit-v3.json');lookup={(Path(r['run']).name,r['role'],r['arm']):r for r in audit['rows']}
    trials=[];paired=[];run_records={};gate_rows=[]
    runs=['native-0093-explicit-phase-free-v1','native-0093-explicit-phase-constrained-v1','native-0063-explicit-phase-constrained-v1']
    for name in runs:
        root=s/name;pr=load(root/'protocol.json');control=load(root/'control.json');target=load(root/'target.json');run_records[name]=(pr,control,target)
        accepted=target['paired_valid'] and control['paired_valid'] and all(lookup[name,role,a]['all_pass'] for role in ('control','target') for a in ('c0','fitted_c'))
        for arm in ('c0','fitted_c'):
            before=control['arms'][arm];after=target['arms'][arm];baseline=target['baseline'][arm]
            n=len(baseline['proposed_associated_ids']);inv=load(Path(pr['source_protocol']['inventory']))
            # Total GLRT comes from the audited original scan accounting, not a
            # changed subset of recovered observations.
            total=next(v['total_GLRT'] for v in inv['summary'] if v['arm']==arm)
            paired.append(dict(scan=pr['job']['label'],constrained=pr['constrained'],arm=arm,passes=accepted,
                incumbent_error_km=error(baseline),control_error_km=error(before),target_error_km=error(after),
                position_shift_km=float(np.linalg.norm(np.array(after['endpoint_east_north_km'])-before['endpoint_east_north_km'])),
                added=after['added_points'],lost=after['lost_points'],
                before_associated=n,after_associated=len(after['proposed_associated_ids']),
                before_associated_percent=100*n/total,after_associated_percent=100*len(after['proposed_associated_ids'])/total,
                native_RMS_before_hz=lookup[name,'control',arm]['native']['RMS_hz'],native_RMS_after_hz=lookup[name,'target',arm]['native']['RMS_hz'],
                exact_minimum_slack=lookup[name,'target',arm]['minimum_slack']))
            for role,result in [('control',control),('target',target)]:
                row=result['arms'][arm];a=lookup[name,role,arm]
                initial=load(root/f'{role}-{arm}-initial.json')
                trials.append(dict(scan=pr['job']['label'],run=name,role=role,arm=arm,paired_valid=result['paired_valid'],
                    error_km=error(row),score=row['negative_twice_elbo'],phase_density=row['explicit_phase_density'],
                    phase_s=row['state']['phases'][pr['target']['candidate_index']],
                    phase_refresh_change_s=row['final_phase_change_s'],receiver_change=row['receiver_coefficient_change'],
                    incumbent_owner_changes=len(a['incumbent_ownership_changes']),control_owner_changes=len(a['control_ownership_changes']),
                    exact_maximum_difference_hz=a['maximum_linearization_difference_hz'],exact_gate_pass=a['all_pass'],
                    minimum_slack=a['minimum_slack'],native_RMS_hz=a['native']['RMS_hz'],
                    added=row['added_points'],lost=row['lost_points'],initial_feasible_phases=sum(v['minimum_gate_slack']>=0 for v in initial['candidates'])))
                gate_rows.extend(dict(scan=pr['job']['label'],run=name,role=role,arm=arm,gate=k,slack=v) for k,v in a['all_gate_slacks'].items())
    csvout('paired_results.csv',paired);csvout('trial_results.csv',trials);csvout('exact_gate_slacks.csv',gate_rows)
    # Preserve the full association IDs/owners as an inspectable research
    # candidate receipt; this does not overwrite the accepted cohort policy.
    candidate={name:dict(target=run_records[name][2],control=run_records[name][1]) for name in runs if 'constrained' in name}
    with gzip.open(out/'candidate_memberships.json.gz','wt') as f:json.dump(candidate,f,separators=(',',':'))
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,scan in zip(axs,['DS24-0093','DS24-0063'],strict=True):
        rows=[v for v in paired if v['scan']==scan and v['constrained']];xx=np.arange(2)
        for k,(field,color,label) in enumerate([('incumbent_error_km','#aaaaaa','Original incumbent'),('control_error_km','#56b4e9','Matched no-addition control'),('target_error_km','#0072b2','Add native curve; constrained')]):
            ax.bar(xx+(k-1)*.24,[v[field] for v in rows],.23,color=color,label=label)
        if scan=='DS24-0093':
            rejected=[v for v in paired if v['scan']==scan and not v['constrained']]
            ax.scatter(xx+.24,[v['target_error_km'] for v in rejected],marker='x',s=80,color='#d55e00',label='Unconstrained target: REJECTED')
        ax.set(xticks=xx,xticklabels=['c = 0','Fitted c'],title=scan,ylabel='Evaluation position error (km)');ax.grid(axis='y',alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('A successful retention mechanism does not guarantee better localization')
    fig.savefig(out/'figures/position_comparison.png',dpi=145);plt.close(fig)
    for scan,slug in [('DS24-0093','0093'),('DS24-0063','0063')]:
        name=f'native-{slug}-explicit-phase-constrained-v1';fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
        for col,arm in enumerate(('c0','fitted_c')):
            a=lookup[name,'control',arm]['native'];b=lookup[name,'target',arm]['native'];t=a['times_s']
            axs[0,col].scatter(t,np.array(a['CFO_hz'])/1000,s=12,c='black',label='Native GLRT')
            for v,color,label in [(a,'#999999','Control prediction'),(b,'#0072b2','Target fit')]:
                axs[0,col].plot(t,np.array(v['predicted_CFO_hz'])/1000,c=color,label=label)
                axs[1,col].plot(t,v['residual_hz'],'.-',ms=3,c=color,label=label+f" ({v['RMS_hz']:.1f} Hz)")
            for ax in axs[:,col]:ax.grid(alpha=.2);ax.legend(fontsize=7)
            axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Residual (Hz)');axs[1,col].axhline(0,c='black',lw=.5)
        fig.suptitle(scan+' / exact causal orbit with receiver correction and profiled constant\nControl curve is predicted after fitting; native observations did not fit that control')
        fig.savefig(out/f'figures/{slug}_native.png',dpi=145);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,arm in zip(axs,['c0','fitted_c'],strict=True):
        for name,role,color,label in [('native-0093-explicit-phase-constrained-v1','control','#999999','No-addition control'),
                ('native-0093-explicit-phase-free-v1','target','#d55e00','Unconstrained target'),
                ('native-0093-explicit-phase-constrained-v1','target','#0072b2','Constrained target')]:
            w=next(v for v in lookup[name,role,arm]['family_witnesses'] if 'RX1-CH4-T003' in v['component'])
            ax.plot(w['times_s'],w['residual_hz'],'.-',label=label,color=color)
        ax.axhline(0,c='black',lw=.5);ax.grid(alpha=.2);ax.legend(fontsize=8);ax.set(title=arm,xlabel='Time (s)',ylabel='Conditional residual (Hz)')
    fig.suptitle('DS24-0093 / existing RX1 CH4 T003 determines the boundary\nThe unconstrained fit fails its slope gate; constrained fits remain close to that boundary')
    fig.savefig(out/'figures/existing_curve_boundary.png',dpi=145);plt.close(fig)
    # Full-family residuals ensure that a single favorable witness is not the
    # sole evidence shown for the newly fitted phase.
    gallery=[]
    for slug in ('0093','0063'):
        name=f'native-{slug}-explicit-phase-constrained-v1';members=lookup[name,'control','c0']['family_witnesses']
        fig,axs=plt.subplots(len(members),2,figsize=(12,3*len(members)),squeeze=False,layout='constrained')
        for col,arm in enumerate(('c0','fitted_c')):
            for k,old in enumerate(lookup[name,'control',arm]['family_witnesses']):
                new=next(v for v in lookup[name,'target',arm]['family_witnesses'] if v['component']==old['component'])
                ax=axs[k,col]
                for v,color,label in [(old,'#999999','Control'),(new,'#0072b2','Target')]:ax.plot(v['times_s'],v['residual_hz'],'.-',ms=3,c=color,label=label+f" ({v['RMS_hz']:.1f} Hz)")
                ax.axhline(0,c='black',lw=.5);ax.grid(alpha=.2);ax.legend(fontsize=7);ax.set(title=arm+' / '+old['component'],xlabel='Time (s)',ylabel='Residual (Hz)')
        f=f'figures/{slug}_all_family.png';fig.savefig(out/f,dpi=120);plt.close(fig);gallery.append(f'![DS24-{slug}: all old family curves]({f})')
    (out/'family_gallery.md').write_text('# All existing curves of the adjusted families\n\n'+'\n\n'.join(gallery)+'\n')
    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger};queue=s/'systematic-annotation-v1';attempt=queue/'attempt-21';batch=[]
    load(attempt/'protocol.json')
    for q in load(attempt/'selected.json'):
        tid=q['track_id'];term=load(attempt/(tid+'-terminal.json'));r=dict(scan=q['label'],track_id=tid,status='execution_'+term['status'],norad=None)
        if term['status']=='complete':
            path=queue/tid/'result.json';a=load(path);vote=identity_consensus(a['folds'],score_name=a.get('identity_score_name','joint'))
            r.update(status=vote['status'],norad=vote['norad']);byid[tid].update(state=vote['status'],norad=vote['norad'],minimum_margin=vote.get('minimum_margin'),annotation_source=str(path),partition_policy='distinct timestamps',geometry_only_early_exit=a.get('geometry_only_early_exit',False),distinct_schedule_ready=not a.get('geometry_only_early_exit',False))
        else:byid[tid]['state']=r['status']
        batch.append(r)
    if len(ledger)!=1630 or len(byid)!=1630:raise ValueError('inventory changed')
    csvout('annotation_ledger.csv',ledger);csvout('annotation_batch.csv',batch)
    groot=s/'graph-inclusion-batch20-v1';gp=load(groot/'protocol.json');graph=[];gallery=[]
    for job in gp['jobs']:
        tid=job['track_id'];term=load(groot/(tid+'-terminal.json'))
        if term['status']!='complete':raise ValueError('incomplete graph inclusion')
        q=load(groot/tid/'target_0.json');control=load(groot/tid/'control.json');fig,axs=plt.subplots(2,2,figsize=(11,6),layout='constrained')
        for col,(arm,v) in enumerate(q['arms'].items()):
            t=v['targets'][0];graph.append(dict(scan=job['label'],track_id=tid,arm=arm,passes=q['paired_valid'],control_passes=control['paired_valid'],
                added=v['added_points'],lost=v['lost_points'],before_error_km=error(control['arms'][arm]),after_error_km=error(v)))
            axs[0,col].scatter(t['times_s'],np.array(t['CFO_hz'])/1000,s=9);axs[0,col].plot(t['times_s'],np.array(t['predicted_CFO_hz'])/1000)
            axs[1,col].plot(t['times_s'],t['residual_hz'],'.-',ms=3);axs[1,col].axhline(0,c='black',lw=.5)
            axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Residual (Hz)')
        fig.suptitle(f"{job['label']} / {tid} / paired pass {q['paired_valid']}");f=f'figures/{tid}_graph.png';fig.savefig(out/f,dpi=120);plt.close(fig);gallery.append(f"## {job['label']}\n\n![Graph trial]({f})")
    csvout('graph_trials.csv',graph);(out/'graph_gallery.md').write_text('# All 18 original-model graph trials\n\n'+'\n\n'.join(gallery)+'\n')
    ga=load(groot/'gate_audit.json');failures=[]
    for r in ga['results']:
        for role,key in [('curved','rows'),('predictive','linear_rows')]:
            for v in r[key]:
                if not v['compatible']:failures.append(dict(scan=r['scan'],track_id=r['track_id'],arm=r['arm'],role=role,target=v.get('target',False),component=v['component'],failures=';'.join(v['failures'])))
    csvout('graph_gate_failures.csv',failures)
    categories={}
    for row in failures:categories.setdefault(row['track_id'],set()).update(row['failures'].split(';'))
    counts=Counter('owner support' if x=={'multiple_orbital_owners_required'} else 'structured residual' for x in categories.values())
    fig,ax=plt.subplots(figsize=(7,4),layout='constrained');ax.bar(list(counts),list(counts.values()),color=['#d55e00','#777777']);ax.set(ylabel='Rejected paired trials',title='Why the 18 graph additions fail');ax.grid(axis='y',alpha=.2)
    fig.savefig(out/'figures/graph_failure_classes.png',dpi=145);plt.close(fig)
    result=dict(graph_assessed=sum(bool(r['annotation_source']) for r in ledger),graph_total=len(ledger),graph_annotation_outcomes=dict(Counter(r['status'] for r in batch)),
        graph_passing=sum(r['passes'] for r in graph if r['arm']=='c0'),graph_failure_classes=dict(counts),
        native_RF_passing_constrained_trials=sum(r['passes'] for r in paired if r['arm']=='c0' and r['constrained']),
        native_points_in_two_RF_passing_candidates=sum(r['added'] for r in paired if r['arm']=='c0' and r['constrained'] and r['passes']),
        original_cohort_policy_changed=False,production_changed=False)
    for name,value in [('summary.json',result),('sources.json',hashes)]:
        with (out/name).open('w' if args.refresh else 'x') as f:json.dump(value,f,indent=2,allow_nan=False)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f)
    (out/'README.md').write_text(f'''# Explicit shared phase: retaining native curves through position fitting

The constrained explicit-phase prototype retains DS24-0093's **49 native points** without losing any old association, and improves error relative to its matched no-addition control: **0.660 → 0.561 km (c=0)** and **0.731 → 0.572 km (fitted c)**. Exact orbit replay confirms every gate still passes. The unconstrained version fails the old RX1 CH4 T003 slope gate in both arms.

The contrast case prevents a general promotion: DS24-0063 retains **44 native points** and also passes exact gates, but worsens error relative to its matched control: **2.103 → 3.520 km (c=0)** and **1.401 → 2.115 km (fitted c)**. The same acceptance rule qualifies both cases. Selecting only the favorable GPS result would be evaluation leakage. Neither case changes the accepted cohort policy or production in this iteration.

This follows the [fixed-position shared-phase experiment](../2026_10_30_shared_phase_feasibility/README.md). DS24-0093 tests the identified optimizer limitation; DS24-0063 was chosen as the contrasting, previously investigated receiver/phase case before inspecting this trial's error.

## Matched results and point accounting

{table(paired,['scan','constrained','arm','passes','incumbent_error_km','control_error_km','target_error_km','position_shift_km','added','lost','before_associated_percent','after_associated_percent'])}

All rows retain the same causal identity hypotheses and original observations. Candidate counts in rejected unconstrained rows are provisional. The qualified constrained candidates change DS24-0093 from **4,030/4,680 (86.11%) to 4,079/4,680 (87.16%)**, and DS24-0063 from **909/1,426 (63.74%) to 953/1,426 (66.83%)**. These candidate points are not silently added to the retained research-policy totals. There were no earlier accepted native additions for these two scans in the latest 93-scan accounting. [Complete candidate IDs and ownership](candidate_memberships.json.gz) make the two proposals reviewable.

“Incumbent” is the previous accepted model. “Control” uses this new conditional model but adds no native observations. The distinction matters: changing the model alone moves DS24-0063 substantially. Comparing only the fitted-c incumbent (2.304 km) to the target (2.115 km) would conceal that adding the target actually worsens its matched 1.401 km control. Frequency fit and position accuracy are reported separately; there is no full-cohort performance claim from two cases.

![Position error comparison](figures/position_comparison.png)

## The model and what changed

The previous solver optimized position while setting satellite nuisance variables to posterior means. The new research solver exposes one **existing** shared satellite phase as a third optimizer coordinate, alongside east and north. It reconciles correlated existing fragment constants. Receiver coefficients, physical orbit coefficients and other satellites remain at their curved-data posterior means **at each position**. They can change as position changes, but native points do not directly recalibrate them at a fixed position. The independent exact replay reports receiver-coordinate changes of exactly zero.

Let `G` be the local curved-data Gaussian posterior precision, with Gamma noise precisions fixed at that position. Partition the free coordinates into phase `p` and this family's old fragment constants `B`, conditioning all remaining coordinates at their posterior means. Eliminating the correlated constants gives:

```text
Q = G_pp - G_pB inv(G_BB) G_Bp
delta_B = -inv(G_BB) G_Bp delta_p
-2 log phase_density = Q * delta_p^2 - log(Q) + log(2*pi)
```

The phase coordinate above is normalized by its existing prior scale. Predictive curves retain variance `2*sigma^2` and a correlated 300 Hz constant per curve. Their constants are integrated. The objective is the curved-data ELBO plus the **normalized conditional phase density** plus predictive density. Including `-log(Q)` matters because precision changes with position. A numerical integration test verifies that integrating the explicit phase recovers the matching conditional Gaussian predictive density.

This changes predictive uncertainty by conditioning excluded posterior coordinates rather than integrating them; it is an empirical conditional model, not the unchanged original Bayesian marginal likelihood. No prior widths, thresholds, polynomial degrees or orbital modes are added. Its scalar objective is authoritative; the legacy residual vector is explicitly not a factorization of that objective and is never used for Gauss–Newton optimization.

## Search, constraints and exact replay

Each control and target starts at the same accepted RF-only incumbent in the original 25 × 25 km box. A fixed 81-point phase initialization grid covers ±0.2 seconds around that incumbent phase, clipped to the existing ±15-second phase bounds. Both versions then use five phase-refresh rounds with at most 48 SLSQP iterations per round. Phase is scaled so the finite-difference step is 0.0001 seconds, while position steps are 0.001 km. This is a bounded local continuation, not a fresh cold-start catalogue or global localization search.

The constrained version includes every original profile, conditional-residual, alias, elevation, orbital-support and predictive gate. The unconstrained control uses the same objective and budgets without gate constraints. Final qualification additionally requires both c arms, phase-refresh agreement, exact shared-orbit replay and retention of every previously associated point. Objectives rebuild to 1e-5. A separate exact-orbit gate audit retains all fitted coefficients, substitutes the physical family orbit, and checks every gate again. The boundary passes remain narrow: this is mathematical compatibility under current checks, not proof of white noise or correct identity.

{table(trials,['scan','role','arm','paired_valid','error_km','native_RMS_hz','minimum_slack','exact_maximum_difference_hz','phase_refresh_change_s'])}

The table includes the unconstrained DS24-0093 run as well as both constrained cases; [trial CSV](trial_results.csv) retains the unambiguous run identifier. [All exact gate slacks](exact_gate_slacks.csv) preserve the rejected results too. Incumbent membership is independently rebuilt, and every old point's satellite ownership is compared. Both constrained candidates preserve all old owners. The rejected unconstrained DS24-0093 target loses valid satellite ownership for 15 old points in each c arm (NORAD 58189 to unassigned), despite retaining their IDs in provisional counts. Point-count retention alone would miss that loss; these rejected counts are not accepted associations.

## DS24-0093: an optimizer limitation with a useful recovery

The unconstrained objective prefers a phase just beyond the old T003 slope threshold. Allowing phase to move independently lets the constrained optimizer choose a nearby phase and position that retain both the original curve and the recovered 49-point curve. No points are truncated or discarded.

![DS24-0093 GLRT, orbit and residual](figures/0093_native.png)

![The old curve constraining the fit](figures/existing_curve_boundary.png)

The earlier randomized block experiment improved the native held RMS in six of six comparisons, but old same-family held RMS improved in only four. That experiment held position fixed after training-only calibration. It therefore does not independently validate the new three-coordinate position update or establish a false-association rate.

## DS24-0063: a passing recovery that pulls position the wrong way

The second case passes all current gates but makes a much larger position update and worsens error against its matched control. Its improved native fit is insufficient evidence that the added curve constrains the correct location. The causal ID remains a conditionally supported hypothesis; these results alone cannot distinguish residual orbital error, receiver-model error, a mistaken identity or biased nuisance/position tradeoffs.

![DS24-0063 GLRT, orbit and residual](figures/0063_native.png)

[All old family residuals](family_gallery.md) show what the two recoveries cost the existing curves. A large position displacement is a possible RF-only diagnostic to investigate, not a cutoff justified by these two GPS outcomes. Do not tune a rejection threshold to retain DS24-0093 and exclude DS24-0063.

## Inventory progress and every graph inclusion failure

The original graph inventory advances from **868 to {result['graph_assessed']}/1,630** assessed tracks. All 32 executions in this batch finish; classifications are `{result['graph_annotation_outcomes']}`. A supported identity here is conditional on the graph and candidate search, not verified satellite truth.

All 18 supported graph identities from the preceding batch receive matched original-model position trials. **None passes in both c arms.** Replayed failures classify as `{result['graph_failure_classes']}`. Residual-structure failures and missing independent receiver/channel support are distinct bottlenecks; neither is repaired by reporting a lower RMS alone. No graph points are counted as recovered in this batch.

![Graph failure classes](figures/graph_failure_classes.png)

[All 18 GLRT/orbit/residual plots](graph_gallery.md), [all graph trials](graph_trials.csv), [all gate failures](graph_gate_failures.csv), [updated ledger](annotation_ledger.csv), and [batch classifications](annotation_batch.csv).

## Next test and validation status

The next useful test is training-only position-and-phase fitting followed by prediction of withheld evidence from **other satellite families**, not merely the added curve at a fixed position. Keep random whole scan-wide blocks and guards, matched c arms, original priors, and every failed result. This tests whether a target-driven position change improves independent geometric evidence. Separately continue the inventory and causal identity alternatives for structured graph failures. No new ALGO promotion is justified by this two-case result.

Thirteen targeted tests pass for phase density normalization, exact Gaussian integration, conditional bias reconciliation, native position fitting and fixed-phase helpers. The on-disk endpoint audits cover all 12 control/target c-arm fits. GPS is evaluation-only; no future TLEs or RF collection are used. No production or retained cohort policy changes occur.

[Summary](summary.json), [source hashes](sources.json), [compact numerical evidence](evidence.json.gz).
''')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('study','previous','output'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--refresh',action='store_true',help='Regenerate this report directory from its recorded study inputs')
    run(p.parse_args())
