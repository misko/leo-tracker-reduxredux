"""Report complete clean native-branch validation and bounded failure ablations."""
import argparse
from collections import Counter
import csv,gzip,hashlib,json,shutil
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


def label(job):return 'DS24-0103' if job['label']=='AUTO-bfc006db' else job['label']


def failures(row,target_names):
    kinds=[]
    if any(not q['compatible'] for q in row['targets']):kinds.append('target_residual')
    if any(not q['compatible'] for q in row['gates']['tracks']):kinds.append('original_curved_gate')
    if any(not q['compatible'] and q['component'] not in target_names for q in row['linear_gates']):kinds.append('original_predictive_gate')
    if row['final_phase_change_s']>.01:kinds.append('phase_convergence')
    if row['lost_points']:kinds.append('old_point_loss')
    if 'shared_satellite_replay' in row:
        q=row['shared_satellite_replay']
        if not q['phases_in_bounds'] or q['maximum_phase_linearization_error_hz']>1:kinds.append('exact_phase_replay')
    return ';'.join(kinds)


def run(args):
    s=args.study;sources={};evidence={}
    def load(p):
        p=Path(p);sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p);evidence[str(p)]=r;return r
    eligible=load(s/'omitted-branch-annotations-v1/protocol.json')['all_eligible'];byid={j['branch']['branch_id']:j for j in eligible}
    annotations=[];results={}
    for folder in sorted(s.glob('omitted-branch-annotations-v*')):
        pr=load(folder/'protocol.json')
        for j in pr['jobs']:
            bid=j['branch']['branch_id'];receipt=load(folder/(bid+'-terminal.json'));r=load(folder/bid/'result.json');load(folder/bid/'protocol.json')
            if bid in results:raise ValueError('native branch annotated twice')
            a=identity_consensus(r['folds'],score_name=r['identity_score_name']);results[bid]=r;b=j['branch']
            annotations.append(dict(branch_id=bid,scan=label(j['job']),job_id=j['job']['job_id'],points=b['points'],span_s=b['span_s'],
                receiver=b['receiver'],channel=b['channel'],status=a['status'],norad=a.get('norad'),minimum_margin=a.get('minimum_margin'),
                execution=receipt['status'],source=str(folder/bid),inclusion_status='not_eligible'))
    if set(results)!=set(byid):raise ValueError('all 72 frozen clean large branches must have terminal assessments')
    out=args.output;out.mkdir(parents=True,exist_ok=False);figs=out/'figures';figs.mkdir()
    def csvout(name,rows):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    fits=[];accepted=[];gallery=[];trials={};execution=[]
    for folder in sorted(s.glob('omitted-branch-inclusions-v*')):
        pr=load(folder/'protocol.json')
        for j in pr['jobs']:
            bid=j['branch']['branch_id'];rc=load(folder/(bid+'-terminal.json'));a=next(q for q in annotations if q['branch_id']==bid)
            execution.append(dict(branch_id=bid,scan=a['scan'],status=rc['status'],reason=rc.get('reason')))
            if rc['status']!='complete':a['inclusion_status']='execution_'+rc['status'];continue
            result=load(folder/bid/'target_0.json');control=load(folder/bid/'control.json');load(folder/bid/'protocol.json');trials[bid]=result
            a['inclusion_status']='passes' if result['paired_valid'] else 'rejected'
            inv=load(j['job']['inventory']);total=inv['summary'][0]['total_GLRT'];target_names={e['component'] for e in result['target_entries']}
            if result['paired_valid']:accepted.append((j,result,control))
            for arm,row in result['arms'].items():
                c=control['arms'][arm]
                fits.append(dict(branch_id=bid,scan=a['scan'],arm=arm,points=j['branch']['points'],norad=a['norad'],passes=result['paired_valid'],
                    control_passes=control['paired_valid'],control_error_km=error(c),trial_error_km=error(row),
                    added=row['added_points'],lost=row['lost_points'],control_percent=100*len(c['proposed_associated_ids'])/total,
                    proposed_percent=100*len(row['proposed_associated_ids'])/total,failures=failures(row,target_names),
                    target_RMS_hz=row['native_target_diagnostics'][0]['RMS_hz'],
                    control_objective=c['negative_twice_elbo'],trial_objective=row['negative_twice_elbo']))
            fig,axs=plt.subplots(2,2,figsize=(11,6),layout='constrained')
            for col,arm in enumerate(['c0','fitted_c']):
                d=result['arms'][arm]['native_target_diagnostics'][0];t=d['times_s']
                axs[0,col].scatter(t,np.array(d['CFO_hz'])/1000,s=12,label='Native GLRT + fixed alias')
                axs[0,col].plot(t,np.array(d['predicted_CFO_hz'])/1000,color='#cc3311',label='Shared causal prediction')
                axs[1,col].plot(t,d['residual_hz'],'.-');axs[1,col].axhline(0,color='black',lw=.5)
                axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Scan time (s)',ylabel='Residual (Hz)')
                for ax in axs[:,col]:ax.grid(alpha=.2)
                axs[0,col].legend(fontsize=7)
            fig.suptitle(f"{a['scan']} RX{a['receiver']} CH{a['channel']} — {a['points']} points / {a['norad']} / {a['inclusion_status']}\n{bid}; individual trial, no combined recovery claim")
            fig.savefig(figs/(bid+'.png'),dpi=125);plt.close(fig)
            gallery.append(f"## {a['scan']} — {bid}\n\n![Native branch and residual](figures/{bid}.png)\n")
    if any(a['status']=='conditionally_supported_identity' and a['inclusion_status']=='not_eligible' for a in annotations):raise ValueError('supported identity missing inclusion attempt')
    csvout('annotations.csv',annotations);csvout('position_trials.csv',fits);csvout('inclusion_execution.csv',execution)
    (out/'gallery.md').write_text('# All individual native inclusion trials\n\n'+'\n'.join(gallery))
    qualified_ids=set();conflicts=[]
    for j,r,c in accepted:
        points=set.intersection(*(set(v['proposed_associated_ids'])-set(c['arms'][a]['proposed_associated_ids']) for a,v in r['arms'].items()))
        qualified_ids.update((j['job']['job_id'],p) for p in points)
    for k,(j,r,c) in enumerate(accepted):
        for jj,rr,cc in accepted[k+1:]:
            if j['job']['job_id']!=jj['job']['job_id']:continue
            overlap=set(j['branch']['observation_ids'])&set(jj['branch']['observation_ids'])
            if overlap:conflicts.append(dict(scan=label(j['job']),branch_a=j['branch']['branch_id'],branch_b=jj['branch']['branch_id'],shared_points=len(overlap)))
    if conflicts:csvout('overlapping_qualified_alternatives.csv',conflicts)
    # Update the separate native proposal ledger, preserving the original graph inventory denominator.
    previous=Path(__file__).resolve().parents[1]/'reports/2026_10_29_omitted_native_branches/native_branch_ledger.csv'
    sources[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest();ledger=list(csv.DictReader(previous.open()))
    amap={a['branch_id']:a for a in annotations}
    for row in ledger:
        if row['branch_id'] in amap:
            a=amap[row['branch_id']];row.update(annotation=a['status'],norad=a['norad'],position_trial=a['inclusion_status'])
    csvout('native_branch_ledger.csv',ledger)
    ablations=[];ablation_sources=[('original','omitted-branch-inclusions-v1'),('fixed_noise','native-annotation-noise-ablation-v1'),
        ('causal_orbit_prior','native-target-orbit-prior-v1'),('satellite_moments','native-shared-satellite-refresh-v1')]
    focus=set(p.parent.name for p in (s/'native-residual-transfer-v1').glob('*/result.json'))
    for name,rootname in ablation_sources:
        root=s/rootname;load(root/'protocol.json')
        for bid in sorted(focus):
            r=load(root/bid/'target_0.json');c=load(root/bid/'control.json');load(root/bid/'protocol.json');load(root/(bid+'-terminal.json'))
            for arm,row in r['arms'].items():
                ablations.append(dict(scan=label(r['job']),variant=name,arm=arm,passes=r['paired_valid'],control_passes=c['paired_valid'],
                    before_km=error(c['arms'][arm]),after_km=error(row),RMS_hz=row['native_target_diagnostics'][0]['RMS_hz'],
                    target_passes=all(q['compatible'] for q in row['targets']),failures=failures(row,{e['component'] for e in r['target_entries']}),
                    receiver_change=row.get('shared_satellite_replay',{}).get('receiver_coefficient_change',row['linear_calibration_max_difference'])))
    csvout('failure_ablations.csv',ablations)
    transfers=[];witnesses=[];regional=[]
    for bid in sorted(focus):
        root=s/'native-residual-transfer-v1';r=load(root/bid/'result.json');load(root/bid/'protocol.json');load(root/(bid+'-terminal.json'))
        shutil.copy2(root/bid/'transfer.png',figs/(bid+'-transfer.png'));sources[str(root/bid/'transfer.png')]=hashlib.sha256((root/bid/'transfer.png').read_bytes()).hexdigest()
        for arm,v in r['arms'].items():
            transfers.append(dict(scan=label(r['job']),arm=arm,before_RMS_hz=v['target_before']['RMS_hz'],
                hypothetical_RMS_hz=v['target_after_diagnostic_conditioning']['RMS_hz'],posterior_shift=v['posterior_shift']['posterior_shift_mahalanobis'],
                covariance_screen=v['target_covariance_whitened_screen']['noise_screen_pass'],
                **{q['block']+'_shape_RMS_hz':q['centered_RMS_hz'] for q in v['contributions']}))
            for q in v['witnesses']:witnesses.append(dict(scan=label(r['job']),arm=arm,component=q['component'],norad=q['norad'],
                same_family=q['same_family'],same_receiver=q['same_receiver'],overlap_points=q['overlap_points'],
                before_RMS_hz=q['before']['RMS_hz'],hypothetical_RMS_hz=q['after_target_conditioning']['RMS_hz']))
        root=s/'native-regional-catalogue-v1';rr=load(root/bid/'result.json');load(root/bid/'native_protocol.json');load(root/(bid+'-terminal.json'))
        for arm,models in rr['tracks'][0]['trials'].items():
            for model,offers in models.items():
                for search in ['current','regional']:
                    rows=sorted([q for q in offers if q['search']==search],key=lambda q:q['cost']);seen=set()
                    for q in rows:
                        if q['norad'] in seen:continue
                        seen.add(q['norad']);regional.append(dict(scan=label(rr['job']),arm=arm,model=model,search=search,norad=q['norad'],
                            RMS_hz=q['rms_hz'],phase_s=q['phase_s'],bias_hz=q['offset_hz'],rate_hz_s=q['rate_hz_s'],cost=q['cost'],
                            shape_pass=q['shape_pass'],physical_screen_pass=q['physical_screen_pass'],position=q['position_east_north_km']))
    csvout('residual_transfer.csv',transfers);csvout('witness_transfer.csv',witnesses);csvout('regional_candidates.csv',regional)
    outcomes=Counter(a['status'] for a in annotations);passes=[r for r in fits if r['passes'] and r['arm']=='fitted_c']
    summary=dict(clean_large_proposals=len(eligible),annotations=len(annotations),annotation_outcomes=dict(outcomes),
        inclusion_attempts=len(execution),inclusion_execution=dict(Counter(r['status'] for r in execution)),
        individually_qualified_branches=len(accepted),qualified_scans=len({j['job']['job_id'] for j,_,_ in accepted}),
        unique_points_in_individually_qualified_trials=len(qualified_ids),overlapping_qualified_pairs=len(conflicts),
        fitted_c_improved=sum(r['trial_error_km']<r['control_error_km'] for r in passes),fitted_c_worsened=sum(r['trial_error_km']>r['control_error_km'] for r in passes),
        joint_inclusion_not_tested=True,no_production_change=True)
    write(out/'summary.json',summary)
    fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    names=list(outcomes);axs[0].barh(range(len(names)),[outcomes[n] for n in names]);axs[0].set(yticks=range(len(names)),yticklabels=[n.replace('_',' ') for n in names],xlabel='Native branch proposals')
    for i,n in enumerate(names):axs[0].text(outcomes[n],i,' '+str(outcomes[n]),va='center')
    for arm,color,marker in [('c0','#4477aa','o'),('fitted_c','#ee6677','s')]:
        rr=[r for r in fits if r['arm']==arm and r['passes']];axs[1].scatter([r['added'] for r in rr],[1000*(r['trial_error_km']-r['control_error_km']) for r in rr],c=color,marker=marker,alpha=.65,label=arm)
    axs[1].axhline(0,c='black',lw=.7);axs[1].set(xlabel='Proposed additional GLRT points',ylabel='Position error change (m); negative is better');axs[1].legend()
    for ax in axs:ax.grid(alpha=.2)
    fig.suptitle('Complete clean native proposal cohort; individual trials, not a joint dataset-wide algorithm');fig.savefig(figs/'cohort.png',dpi=145);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for ax,scan in zip(axs,['DS24-0090','DS24-0093'],strict=True):
        for arm,offset,color in [('c0',-.15,'#4477aa'),('fitted_c',.15,'#ee6677')]:
            rr=[r for r in ablations if r['scan']==scan and r['arm']==arm]
            for i,r in enumerate(rr):
                ax.plot([i+offset]*2,[r['before_km'],r['after_km']],c=color);ax.scatter(i+offset,r['before_km'],marker='_',s=100,c=color)
                ax.scatter(i+offset,r['after_km'],marker='o' if r['passes'] else 'x',c=color,label=arm if i==0 else None)
            ax.set(xticks=range(len(rr)),xticklabels=[r['variant'].replace('_','\n') for r in rr],title=scan,ylabel='Evaluation error (km)')
        ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Matched controls per model: bars control, crosses rejected target trials');fig.savefig(figs/'failure_ablations.png',dpi=145);plt.close(fig)
    write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f,separators=(',',':'))
    md=f"""# Native GLRT recovery: complete clean-proposal cohort and shared-model failures

This extends the [93-scan discovery report](../2026_10_29_omitted_native_branches/README.md). All **{len(annotations)} / {len(eligible)}** frozen clean large native proposals now have an explicit causal identity outcome. Their overlaps remain intact as alternatives. This does not complete the wider 1,630-track investigation or the 21 large native proposals with flagged polynomial residuals.

## Results and inventory

{table([dict(outcome=k,proposals=v) for k,v in outcomes.items()],['outcome','proposals'])}

All {len(execution)} conditionally supported identities received a matched original-model inclusion attempt. Execution outcomes: {summary['inclusion_execution']}. **{len(accepted)} proposals across {summary['qualified_scans']} scans pass individually**, covering **{len(qualified_ids)} distinct new point identities** in both c arms. There are **{len(conflicts)} overlapping pairs** among qualifying proposals. These cannot be summed or simultaneously inserted. We have not yet validated their joint inclusion, including disjoint proposals sharing a scan or satellite.

The 15 nonpassing trials have different causes: nine fail a new-target residual check in at least one c arm; three fail an existing predictive-track check; three DS24-0083 alternatives inherit an original curved-track failure already present in the matched c=0 control (RX1 CH8 T002). The last three are not evidence that the native targets themselves fit poorly. A blank per-arm failure column can mean that arm passes while the other c arm rejects the pair.

Among individually passing fitted-c trials, {summary['fitted_c_improved']} improve position error and {summary['fitted_c_worsened']} worsen it. This is an evidence-selected research cohort with repeated scans and overlapping alternatives, not a full-dataset performance distribution or an independent generalization test. Correct identity, inclusion compatibility, and useful position information remain separate questions.

![Cohort outcomes and accuracy changes](figures/cohort.png)

The [updated 813-proposal ledger](native_branch_ledger.csv), [72 identity outcomes](annotations.csv), [individual matched position trials](position_trials.csv), and [execution receipts](inclusion_execution.csv) include every outcome. [All orbit/CFO/residual figures](gallery.md) cover every completed inclusion trial. The original graph-track inventory remains 681/1,630 assessed as recorded in the preceding report; native alternatives do not change that denominator. DS24 coverage still means 93 available frozen exports; nine missing exports have not silently become evaluated scans.

## Protocol

Use original native GLRT measurements and fixed integer alias lifts; separate actual RF/RX/channel lanes. The frozen discovery algorithms and degree/complexity/noise screens are unchanged. Test all 72 clean large proposals, with unseen scans prioritized and largest proposals first. The final five same-scan alternatives run independently after all other scans have been assessed. Never select by GPS error.

Each annotation uses the full original causal nomination catalogue, three distinct timestamp-selected randomized 12-second block holdouts with two-second guards, the fixed validation noise policy, and 0.025-second phase quadrature where needed. Insufficient partition support remains explicit. Labels and calibration are conditional on the incumbent graph, and are not ground truth. Every supported identity is then tested with original noise/priors, matched c=0/fitted-c observations and candidates, five phase-refresh rounds and 48 position iterations per round from the 25×25 km regional center. Targets remain predictive-only. Old point ownership, old residual gates, target residual gates, phase convergence and regional bounds must all pass. All jobs are bounded to 600 seconds; at most eight per batch. No new RF collection.

Evaluation alone uses 37.849061591561885, -122.48574968092912. A better frequency fit is never treated as proof of better location. CSV objectives are separate; adding data changes their number of observations, so raw objective differences across control and target do not measure generalization.

## Why the two original supported branches still fail

The first batch's DS24-0090 (79 points, NORAD 69247) and DS24-0093 (49 points, NORAD 58189) were selected for debugging because their nominations were consistent but inclusion failed. The following tests use both cases, both c arms, causal inputs, and no error-driven acceptance.

1. **Match identity-validation noise in inclusion.** Use 150 Hz calibration noise, unit original-curve weights, and 150 Hz predictive base noise in both control and target. Both controls pass, but both targets still fail residual structure. Noise-policy mismatch changes inferred position substantially in DS24-0090, but does not explain away these failures.
2. **Retain causal physical orbit uncertainty.** Add the existing three-mode causal prior for each active target family even with one original curved owner. Native target observations still cannot calibrate it. DS24-0090 previously lacks these orbital modes; DS24-0093 already has them. Neither is rescued. The two run protocols contain an older broad `original_noise_weights_and_priors` flag; `target_orbit_prior=true` explicitly records the changed prior, and the tool now writes the broad flag correctly. Noise weights stay original.
3. **Check posterior uncertainty and transfer.** At the saved RF-only trial position, use the same local hierarchical Gaussian precision as the predictive likelihood. Condition its means on the native target for diagnosis only. This reduces RMS from roughly 95–105 to 61–62 Hz in DS24-0093, mostly through satellite phase. DS24-0090 falls from 140 to 70 Hz through a mixture of satellite phase and receiver terms; transferring that shift worsens a different-family RX1 CH2 track from about 58 to 87 Hz. Neither target passes the marginal covariance-whitened screen. This is a diagnostic, not an authorization to change receiver calibration. Other tracks are in-sample witnesses, not independent confirmation.
4. **Search the causal catalogue more broadly.** Repeat constant, small-rate (0.5 Hz/s prior), and loose-bias shape diagnostics at the two original RF endpoints plus a 3×3 regional grid at −10/0/+10 km. Refinement uses every target point, but receiver calibration stays frozen and the shortlist is finite: this is not a proof of global identifiability. Both searches continue to favor the same satellite. DS24-0093 fits about 62–64 Hz with phase roughly −0.05 to −0.07 s and clean residuals. DS24-0090 still has structure even at the best regional result (roughly 105–134 Hz depending on model/arm); its best distinct competitors are above 2 kHz RMS. No resulting single-track grid position is accepted as a location.
5. **Refresh only satellite posterior moments.** An opt-in prototype exposes the requested family's phase/orbit means already marginalized by the predictive likelihood, retains receiver means exactly, and relinearizes five times. All old gates remain. DS24-0093's new target now passes, but several old family tracks fail. DS24-0090's target still fails. Exact phase replay errors are below 0.001 Hz and receiver-coefficient changes are zero. Both prototypes are rejected. This is a partial posterior projection: original fragment-bias means stay fixed, and some old-curve failures are mean offsets induced by that projection. Those failures do not by themselves prove a wrong satellite. A coherent treatment of fragment biases and a shared feasible phase interval would need separate validation; do not solve this by dropping the old gates.

![Matched failure ablations](figures/failure_ablations.png)

{table(ablations,['scan','variant','arm','passes','control_passes','before_km','after_km','RMS_hz','target_passes'])}

Detailed evidence: [ablations](failure_ablations.csv), [parameter-block contributions](residual_transfer.csv), [witness transfer](witness_transfer.csv), [regional competitors](regional_candidates.csv). None of these diagnostic variants is selected for production based on its evaluation error.

![DS24-0090 transfer](figures/51ce702690bc7836176e-transfer.png)

![DS24-0093 transfer](figures/185ec6739ec0885db599-transfer.png)

## What this changes and what remains

We now have terminal outcomes for the entire clean native proposal cohort, instead of eight examples. The remaining work is explicit: resolve overlapping alternatives, test joint inclusion of nonoverlapping branches, examine flagged polynomial proposals without forcing joins, and continue the original graph-track identity ledger. Receiver/satellite model changes require independent transfer evidence and cohort-wide accuracy evaluation before promotion. More accepted points have not shown a uniform position benefit.

Reproduction: `run_native_branch_annotations.py` advances a frozen batch and preserves claims even if an earlier attempt is incomplete. `run_native_branch_inclusions.py` tests every supported identity from a batch. `probe_native_residual_transfer.py` reproduces the uncertainty audit. `diagnose_all_large_tracks.py one --native-branches ... --track ...` performs the regional causal search. `include_predictive_annotations.py` has opt-in `--noise-policy annotation_fixed`, `--target-orbit-prior`, and `--shared-satellite-refresh`; defaults preserve the original experiment. Exact commands, inputs and terminal receipts are in [compressed evidence](evidence.json.gz) with [source hashes](sources.json). Eighteen focused tests pass, including analytic Gaussian conditioning, unchanged receiver means and likelihood under the projection, orbital-support rules, native measurement ownership, and queue claims. These checks do not establish scientific correctness or promotion readiness.

No production change or new ALGO is promoted. No future TLE is used.
"""
    (out/'README.md').write_text(md);print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
