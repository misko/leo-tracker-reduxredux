"""Publish the second omitted-curve batch and shared-family joint checks."""
import argparse,csv,gzip,hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from debug_fast_graph_unassociated import read,write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays
from report_omitted_predictive_recovery import target_diagnostic
from annotation_partition_plan import require_distinct_annotation
from leo.analysis.research.grouped_prediction import replay_split
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();hashes={};evidence={}
    def load(p,compact=True):
        d=read(p);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        if compact:evidence[str(p)]=compact_replays(compact_evidence(d))
        return d
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=140);plt.close(fig)
    root=s/'omitted-predictive-distinct-inclusion-v2';retry=s/'omitted-predictive-numerical-followup-v2';joint=s/'omitted-predictive-same-family-joint-v1'
    pr=load(root/'protocol.json');execution=load(root/'execution.json');followups=load(retry/'execution.json');load(retry/'protocol.json')
    group_jobs=load(joint/'protocol.json')['jobs'];group_execution=load(joint/'execution.json')
    assert len(execution)==16 and len(group_execution)==2
    assert all(r['status'] not in ('execution_failed','annotation_execution_failed') for r in execution+followups+group_execution)
    newer={r['job']['track_id']:r for r in followups};records={r['job']['track_id']:r for r in execution}
    ledgerfile=args.previous/'annotation_ledger.csv';ledger=list(csv.DictReader(ledgerfile.open()));hashes[str(ledgerfile)]=hashlib.sha256(ledgerfile.read_bytes()).hexdigest();lookup={r['track_id']:r for r in ledger}
    old_pending=load(args.previous/'remaining_omitted_candidates.json');remaining=[r for r in old_pending if r['track_id'] not in records]
    assert len(remaining)==29;write(out/'remaining_omitted_candidates.json',remaining)
    annotations=[];partitions=[];positions=[];final=[];galleries=[];terminal=[];trials_byid={};qualified_ids=set();prior_ids=set()
    prior_positions=list(csv.DictReader((args.previous/'final_positions.csv').open()));series=[]
    for row in prior_positions:
        if row['qualified']!='True':continue
        p=load(Path(row['final_trial'])/'protocol.json');ids=set(o for t in p['targets'] for o in t['observation_ids']);prior_ids.update(ids)
        series.append(dict(track_id=row['track_id'],scan=row['scan'],norad=int(row['norad']),source_trial=row['final_trial'],observation_ids=sorted(ids),iteration='first omitted batch'))
    def load_trial(folder,shared):
        p=load(folder/'protocol.json');c=load(folder/'control.json');a=load(folder/('target_0.json' if shared else 'new_family.json'));r=load(folder/'exact_owner_replay.json')
        for name,digest in r['source_hashes'].items():
            if (hashes.get(name) or hashlib.sha256(Path(name).read_bytes()).hexdigest())!=digest:raise ValueError('changed exact replay source')
        return p,c,a,r
    for j in pr['jobs']:
        tid=j['track_id'];receipt=records[tid];val=root/tid/'annotation';ann=load(val/'result.json');ap=load(val/'protocol.json')
        inv=load(Path(j['inventory']));target=next(t for t in inv['tracks'] if t['track_id']==tid)
        base=Path(inv['job']['root'])/inv['job']['case'];track=load(base/'tracks.json',False)[target['track_index']];native=load(base/'tracking.json',False)['source']
        times=np.asarray(track['times']);old=load(Path(j['validation'])/'result.json');counts={}
        for kind,r in [('old',old),('refreshed',ann)]:
            sets=[]
            for fold in r['folds']:
                train,held=replay_split(times,fold['split']);signature=tuple(np.flatnonzero(held));sets.append(signature)
                partitions.append(dict(track_id=tid,scan=j['label'],kind=kind,seed=fold['seed'],train_points=int(train.sum()),held_points=int(held.sum()),held_indices=' '.join(map(str,signature))))
            counts[kind]=len(set(sets))
        supported=ann['annotation']['status']=='conditionally_supported_identity'
        if supported:require_distinct_annotation(ann,ap);assert counts['refreshed']==3
        annotations.append(dict(track_id=tid,scan=j['label'],points=j['points'],component=j['component'],capture_mode=native['capture_mode'],sample_rate_hz=native['sample_rate_hz'],
            inventory_sample_rate_hz=inv['job']['sample_rate_hz'],old_distinct=counts['old'],new_distinct=counts['refreshed'],status=ann['annotation']['status'],
            old_norad=j['annotation']['norad'],new_norad=ann['annotation']['norad'],minimum_margin=ann['annotation'].get('minimum_margin')))
        lookup[tid].update(predictive_recheck_source=str(val/'result.json'),predictive_recheck_state=ann['annotation']['status'],
            predictive_recheck_minimum_margin=ann['annotation'].get('minimum_margin'),annotation_likelihood_role='predictive_only; distinct timestamp-selected random partitions')
        finalreceipt=newer.get(tid,receipt);finalroot=retry if tid in newer else root;folder=finalroot/tid/'trial'
        row=dict(scan=j['label'],track_id=tid,norad=ann['annotation']['norad'],points=j['points'],qualified=False,status=finalreceipt['status'],
            c0_before_km=None,c0_after_km=None,fitted_c_before_km=None,fitted_c_after_km=None,final_trial='',capture_mode=native['capture_mode'],sample_rate_hz=native['sample_rate_hz'])
        plot_trial=None
        for name,where,rec in [('distinct',root,receipt)]+([('numerical_followup',retry,newer[tid])] if tid in newer else []):
            load(where/(tid+'-terminal.json'));terminal.extend(dict(scan=j['label'],iteration=name,**r) for r in rec['stages'])
            if rec['status']=='refreshed_identity_not_supported':continue
            p,c,a,r=load_trial(where/tid/'trial',rec['shared_family']);passed=c['paired_valid'] and a['paired_valid'] and r['all_verified'];is_final=where==finalroot
            for arm,z in a['arms'].items():
                d=target_diagnostic(z);noise={k:v[0].item() for k,v in batch_noise_screen(np.asarray(d['residual_hz'])[None],np.asarray(d['times_s'])).items()}
                ci=set(c['arms'][arm]['proposed_associated_ids']);ai=set(z['proposed_associated_ids']);ti=set(o for t in p['targets'] for o in t['observation_ids'])
                if passed:assert ai-ci==ti and not ci-ai
                positions.append(dict(track_id=tid,scan=j['label'],iteration=name,final_variant=is_final,arm=arm,qualified=bool(is_final and passed),
                    control_error_km=error(c['arms'][arm]),addition_error_km=error(z),RMS_hz=d['RMS_hz'],
                    baseline_points=len(ci),proposed_points=len(ai),credited_points=len(ai-ci) if is_final and passed else 0,
                    baseline_percent=100*len(ci)/inv['summary'][0]['total_GLRT'],proposed_percent=100*len(ai)/inv['summary'][0]['total_GLRT'],
                    control_objective=c['arms'][arm]['negative_twice_elbo'],addition_objective=z['negative_twice_elbo'],
                    control_pair_pass=c['paired_valid'],addition_pair_pass=a['paired_valid'],exact_replay_pass=r['all_verified'],
                    optimizer_success=z['history'][-1].get('success'),final_phase_change_s=z['final_phase_change_s'],
                    quadrature_pass=z.get('phase_resolution_audit',{}).get('local_agreement'),**noise))
            if is_final:
                assert passed==(rec['status']=='RF_verified_research_candidate');row.update(qualified=passed,final_trial=str(folder),
                    c0_before_km=error(c['arms']['c0']),c0_after_km=error(a['arms']['c0']),fitted_c_before_km=error(c['arms']['fitted_c']),fitted_c_after_km=error(a['arms']['fitted_c']))
                plot_trial=a;trials_byid[tid]=a
                if passed:
                    qualified_ids.update(ti);series.append(dict(track_id=tid,scan=j['label'],norad=row['norad'],source_trial=str(folder),observation_ids=sorted(ti),iteration='second omitted batch'))
        lookup[tid].update(predictive_research_inclusion=finalreceipt['status']+'; not production promoted',predictive_inclusion_source=row['final_trial'])
        final.append(row);galleries.append((j,track,ann['annotation']['status'],plot_trial,row['qualified']))
    group_rows=[];group_plots=[];common_rows=[];withheld=set()
    for rec in group_execution:
        job=rec['job'];folder=joint/job['name']/'trial';p,c,a,r=load_trial(folder,False);load(joint/(job['name']+'-terminal.json'))
        raw_pass=c['paired_valid'] and a['paired_valid'] and r['all_verified'];assert raw_pass==(rec['status']=='RF_verified_joint_candidate')
        common=load(folder/'common_residual_audit.json');passed=raw_pass and common['reviewed_joint_candidate']
        for source,digest in common['source_hashes'].items():
            if (hashes.get(source) or hashlib.sha256(Path(source).read_bytes()).hexdigest())!=digest:raise ValueError('changed common-audit source')
        common_rows.extend(dict(scan=job['job']['label'],norad=job['norad'],**{k:v for k,v in row.items() if k not in ('times_s','residual_hz','noise')},**row['noise']) for row in common['rows'])
        if not passed:withheld.update(m['track_id'] for m in job['members'])
        ti=set(o for t in p['targets'] for o in t['observation_ids']);terminal.extend(dict(scan=job['job']['label'],iteration='same-family joint',**st) for st in rec['stages'])
        for arm,z in a['arms'].items():
            ci=set(c['arms'][arm]['proposed_associated_ids']);ai=set(z['proposed_associated_ids'])
            if passed:assert ai-ci==ti and not ci-ai
            group_rows.append(dict(scan=job['job']['label'],norad=job['norad'],arm=arm,points=len(ti),qualified=passed,
                original_joint_gate_pass=raw_pass,common_residual_pass=common['common_residual_pass'],
                control_error_km=error(c['arms'][arm]),addition_error_km=error(z),
                overlap_with_individual_qualified_points=len(ti&(prior_ids|qualified_ids)),new_points_beyond_individual_trials=len(ti-(prior_ids|qualified_ids)) if passed else 0,
                control_pair_pass=c['paired_valid'],addition_pair_pass=a['paired_valid'],exact_replay_pass=r['all_verified']))
        group_plots.append((job,a,passed))
        for m in job['members']:
            lookup[m['track_id']].update(same_family_joint_source=str(folder),same_family_joint_status='RF_verified_joint_candidate' if passed else 'joint_common_residual_rejected',same_family_joint_norad=job['norad'])
    raw_qualified_points=len(qualified_ids);raw_qualified_tracks=sum(r['qualified'] for r in final)
    for r in final:
        r['individual_gate_pass']=r['qualified']
        if r['track_id'] in withheld:r.update(qualified=False,status='withheld_common_family_residual')
    for r in positions:
        r['individual_gate_pass']=r['qualified']
        if r['track_id'] in withheld:r.update(qualified=False,credited_points=0)
    for row in series:row['reviewed_candidate']=row['track_id'] not in withheld
    qualified_ids=set(o for row in series if row['iteration']=='second omitted batch' and row['reviewed_candidate'] for o in row['observation_ids'])
    reviewed_series_ids=set(o for row in series if row['reviewed_candidate'] for o in row['observation_ids'])
    for tid in withheld:lookup[tid]['predictive_research_inclusion']='individual_pass_but_common_family_residual_unresolved; not production promoted'
    galleries=[(j,t,a,v,passed and j['track_id'] not in withheld) for j,t,a,v,passed in galleries]
    for name,rows in [('annotations.csv',annotations),('partitions.csv',partitions),('all_position_trials.csv',positions),('final_positions.csv',final),
        ('joint_positions.csv',group_rows),('joint_common_residuals.csv',common_rows),('annotation_ledger.csv',ledger),('executions.csv',terminal)]:csvout(name,rows)
    write(out/'series_qualified_trials.json',series)
    summary=dict(annotation_states=dict(Counter(r['status'] for r in annotations)),individual_statuses=dict(Counter(r['status'] for r in final)),
        original_joint_statuses=dict(Counter(r['status'] for r in group_execution)),reviewed_joint_candidates=sum(passed for _,_,passed in group_plots),qualified_tracks=sum(r['qualified'] for r in final),
        individual_gate_passing_tracks=raw_qualified_tracks,individual_gate_passing_points=raw_qualified_points,withheld_track_ids=sorted(withheld),
        qualified_points=len(qualified_ids),overlap_with_first_batch=len(qualified_ids&prior_ids),new_points_relative_to_first_batch=len(qualified_ids-prior_ids),
        omitted_series_reviewed_points=len(reviewed_series_ids),remaining_candidates=len(remaining),
        capture_modes=dict(Counter(r['capture_mode'] for r in annotations)),production_changed=False,full_goal_complete=False)
    write(out/'summary.json',summary)
    tested=[r for r in final if r['final_trial']];fig,axs=plt.subplots(1,2,figsize=(15,8),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        x=np.arange(len(tested));ax.barh(x-.16,[r[arm+'_before_km'] for r in tested],.32,color='#999');ax.barh(x+.16,[r[arm+'_after_km'] for r in tested],.32,color=['#009e73' if r['qualified'] else '#d55e00' for r in tested])
        ax.set(yticks=x,yticklabels=[r['scan']+' / '+str(r['norad']) for r in tested],xlabel='Evaluation position error (km)',title=arm);ax.invert_yaxis();ax.grid(axis='x',alpha=.2)
        ax.legend(handles=[Patch(color=c,label=n) for c,n in [('#999','Matched control'),('#009e73','Qualified addition'),('#d55e00','Rejected addition')]],fontsize=8)
    save(fig,'position_comparison.png')
    for page in range(4):
        fig,axs=plt.subplots(4,2,figsize=(14,13),layout='constrained')
        for axes,(j,t,status,a,passed) in zip(axs,galleries[page*4:page*4+4],strict=True):
            axes[0].plot(t['times'],np.asarray(t['values'])/1000,'.',label='Native graph GLRT')
            if a:
                d=target_diagnostic(a['arms']['fitted_c']);axes[0].plot(d['times_s'],np.asarray(d['predicted_CFO_hz'])/1000,c='k',lw=.8,label='Causal prediction + nuisance terms')
                for arm,color in [('c0','#0072b2'),('fitted_c','#d55e00')]:
                    d=target_diagnostic(a['arms'][arm]);axes[1].plot(d['times_s'],d['residual_hz'],'.-',lw=.6,c=color,label=arm)
                axes[1].axhline(0,c='k',lw=.5);axes[1].set_ylabel('Residual (Hz)');axes[1].legend(fontsize=8)
            else:axes[1].text(.5,.5,status.replace('_',' ')+'\nNo position inclusion authorized',ha='center',transform=axes[1].transAxes);axes[1].set_axis_off()
            axes[0].set(title=j['label']+' / '+j['component'].split('-RF')[0]+' / '+('QUALIFIED' if passed else 'UNRESOLVED'),ylabel='CFO (kHz)');axes[0].legend(fontsize=7)
            for ax in axes:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2)
        save(fig,f'curves_{page+1}.png')
    fig,axs=plt.subplots(2,2,figsize=(14,8),layout='constrained')
    for axes,(j,a,passed) in zip(axs,group_plots,strict=True):
        for k,d in enumerate(a['arms']['fitted_c']['family']['diagnostics']):
            axes[0].plot(d['times_s'],np.asarray(d['CFO_hz'])/1000,'.',label=d['component'].split('-RF')[0]);axes[1].plot(d['times_s'],np.asarray(d['raw_residual_hz'])-d['profile_bias_hz'],'.-',lw=.6,label=f'Track {k+1}')
        axes[0].set(title=j['job']['label']+' / '+str(j['norad'])+' / '+('QUALIFIED' if passed else 'REJECTED'),ylabel='Native CFO (kHz)')
        axes[1].set(title='One shared satellite phase/orbit, separate track biases',ylabel='Residual (Hz)');axes[1].axhline(0,c='k',lw=.5)
        for ax in axes:ax.set_xlabel('Scan time (s)');ax.legend(fontsize=7);ax.grid(alpha=.2)
    save(fig,'joint_family_residuals.png')
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    qualified=[r for r in final if r['qualified']]
    coverage=[r for r in positions if r['final_variant'] and r['arm']=='fitted_c']
    text=f'''# Second omitted-curve batch and simultaneous same-satellite inclusion

This iteration assesses the next **16 of 45** pending omitted curves. **{raw_qualified_tracks} pass individual inclusion gates ({raw_qualified_points} points)**, but joint residual review reveals a common discrepancy in one family. After withholding that family's current 39-point curve, **{len(qualified)} current candidates remain ({len(qualified_ids)} points)**. Its earlier 45-point recovery is also flagged for review; neither is presently counted as ready for inclusion. Across the two omitted-curve batches, **{len(reviewed_series_ids)} points remain research candidates after this review**. **29 candidates remain** in the pending queue. The full 1,630-curve objective is incomplete.

## Validation and coverage of the work

The same causal predictive-only method is used. Targets cannot calibrate receiver offsets or drifts. Every supported identity must survive three distinct timestamp-selected random scanwide 12-second holdouts with two-second guards. Both c arms retain matched candidates, priors, observations and search budgets. GPS is only used for reporting error; the regional start is the 25 × 25 km box centered at 37.906, −122.545.

Fresh annotation outcomes are **{dict(Counter(r['status'] for r in annotations))}**. A previously supported label can become prediction mismatch or lack enough distinct partitions. Insufficient partitions mean validation is unavailable, not that the detected curve is noise. Such cases receive no position inclusion. The [partition table](partitions.csv) records actual held indices and the [annotation table](annotations.csv) records all outcomes and margins.

Capture modes are **{dict(Counter(r['capture_mode'] for r in annotations))}**, obtained from raw tracking metadata rather than filenames or inherited inventory fields. Actual and inventory sample rates are both recorded. These results must not be presented as a DS24-fast validation cohort.

## Individual position trials

All supported identities receive matched regional control/addition trials. New-family likelihoods integrate phase at 0.025 seconds and physical orbital/receiver uncertainty. Exact orbit replay, incumbent ownership, target residual and numerical checks remain unchanged. Only cases passing all physical/exact checks but failing optimizer completion receive a matched Powell retry for both controls and additions, both c arms, with five phase rounds and 48 iterations / 240 evaluations. Retry selection never uses GPS error.

{table(final,['scan','norad','points','individual_gate_pass','qualified','status','c0_before_km','c0_after_km','fitted_c_before_km','fitted_c_after_km'])}

![Matched position comparisons](figures/position_comparison.png)

The two AUTO-e32d57a7 curves assigned to 64044 each improve position when added alone; they are two measurements in the **same scan**, not two independent location experiments. AUTO-03f9876c remains a large position-error case despite recovering evidence. Rejected trials may also reduce evaluation error; that does not override their RF failures. Objective values and accuracy are reported separately in [all_position_trials.csv](all_position_trials.csv). Objectives with different observation counts are not comparable measures of localization quality.

{table(coverage,['scan','track_id','qualified','baseline_percent','proposed_percent','credited_points'])}

Proposed coverage is shown for transparency; rejected additions receive zero credited points. Qualified trials preserve all incumbent observation IDs and owners. Point sets are compared with the first omitted batch to avoid duplicate credit. Per-curve location improvements cannot be summed or treated as a dataset-wide error distribution, especially where multiple curves come from one scan.

## Joint inclusion: one satellite correction shared across tracks

Two pairs have independently validated identities for the same satellite in the same immutable scan: AUTO-afec5a1f / 67653 (the earlier 45-point CH8 recovery and a 39-point CH6 curve), and AUTO-e32d57a7 / 64044 (37-point CH2 and 36-point CH4 curves). We test each pair simultaneously, using one shared satellite phase/orbit distribution and the receiver uncertainty once. Each graph track retains its own 300 Hz bias prior. This is not a geometric merge and not a sum of independently marginalized likelihoods.

Both joint controls/additions use matched Powell fits, the same physical priors and 0.025-second phase integration. Every constituent target must pass nominal and continuously refined residual checks in both c arms; exact incumbent ownership is preserved. Satellite labels come from independent causal nomination, not a manual catalogue restriction. The grouping helper rejects repeated curves and never shares satellite corrections across different scans.

{table(group_rows,['scan','norad','arm','points','original_joint_gate_pass','common_residual_pass','qualified','control_error_km','addition_error_km'])}

![Joint-family residuals](figures/joint_family_residuals.png)

Visual inspection exposed a gap in the original joint acceptance rule: it checked each track separately but did not check common structure across their combined residuals. The added audit pools the same receiver's disjoint timestamps **without refitting biases**, in both Hz and RF-normalized units, using nominal and continuously refined predictions in both c arms. AUTO-afec5a1f / 67653 fails: normalized quadratic BIC gain is approximately **15.5–17.3** (limit 10), and step z is approximately **4.73–4.86** (limit 4). Both individual tracks had passed. Its apparent **0.564 → 0.502 km** location improvement therefore remains a rejected joint diagnostic, not an accepted 500 m result. The earlier 45-point and current 39-point individual passes remain preserved as historical results, but both are now withheld from inclusion pending explanation of their common bend.

AUTO-e32d57a7 / 64044 passes the combined audit and retains the 73-point joint recovery, with fitted-c error **2.478 → 1.744 km**. [joint_common_residuals.csv](joint_common_residuals.csv) records all checks. This additional check is a common-structure diagnostic, not a calibrated family-wise false-alarm probability: channels may carry correlated noise. It is sufficient reason to withhold a model with unexplained common structure; it does not establish that either satellite identity is wrong. Independent evidence from another satellite on this receiver, or this satellite on another receiver, is needed to distinguish receiver error from satellite-model error.

The new audit is now part of the joint runner. Original trial outputs and terminal receipts remain unchanged; this report distinguishes their original passes from reviewed qualification. Point overlap is explicit and no duplicate credit is awarded. These tests do not yet jointly combine different recovered satellite families in a scan, including the earlier 67634 recovery in AUTO-e32d57a7. That broader simultaneous inclusion remains necessary before claiming a final scan-wide recovered solution.

## GLRT curves and residual evidence for every case

![Curves 1](figures/curves_1.png)
![Curves 2](figures/curves_2.png)
![Curves 3](figures/curves_3.png)
![Curves 4](figures/curves_4.png)

Every selected curve appears, including unresolved identities. Residual panels use the final tested physical model. No fitted orbit is presented for a curve without an authorized identity. The saved per-arm table includes mean, slope, quadratic, step and serial-correlation diagnostics alongside RMS, phase closure and numerical status. Low RMS alone does not authorize inclusion.

The three physical rejections have specific remaining discrepancies. AUTO-a1e93bc4 / 61964 retains a fitted-c slope z of about 3.21 (limit 3), despite a passing c=0 slope. AUTO-64e97379 / 58239 is close to the trend boundary in both arms (about 3.03 and 3.07); its roughly 0.97 km evaluation-error reduction cannot override that failure. AUTO-b6178909 / 67639 retains both a trend (z ≈ 3.47) and a step (z ≈ 5.09, limit 4), despite only about 96 Hz RMS. These thresholds are unchanged. No independent receiver-event evidence was established in this batch, so these discrepancies are not converted into new drift parameters or automatic retries.

## State and next batch

The [updated 1,630-row ledger](annotation_ledger.csv) links fresh identities, individual trials and separate joint-family outcomes. [remaining_omitted_candidates.json](remaining_omitted_candidates.json) contains the next **29** unchanged candidates. [series_qualified_trials.json](series_qualified_trials.json) preserves individual gate-passing point sets and explicitly marks each with `reviewed_candidate`; the two withheld 67653 members have this flag false. It is not a production association catalogue or a list of simultaneous solutions. The larger older calibration-participating annotation workstream remains outstanding.

Position and annotation stages have terminal receipts in [executions.csv](executions.csv); the additional common audits have completed result artifacts in the compact evidence. Exact-replay and common-audit source hashes are verified. Every failed trial is retained. No future TLE, RF acquisition, relaxation of residual thresholds, GPS-based candidate selection or production deployment is introduced.

The targeted regression suite passed 16 tests, including unchanged pending-manifest selection, duplicate-curve and cross-scan protection, distinct holdouts, numerical-retry eligibility, and a synthetic common bend that passes individual screens but fails the combined screen.
'''
    (out/'README.md').write_text(text)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('study','previous','output'):p.add_argument('--'+n,type=Path,required=True)
    run(p.parse_args())
