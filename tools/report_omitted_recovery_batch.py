"""Report a bounded omitted-curve batch while preserving prior review reversals."""
import argparse,csv,gzip,hashlib,json
from collections import Counter,defaultdict
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


def reviewed_points(series):
    owners={}
    for row in series:
        if not row['reviewed_candidate']:continue
        for oid in row['observation_ids']:
            if oid in owners and owners[oid]!=row['norad']:raise ValueError('conflicting satellite owners in cumulative candidates')
            owners[oid]=row['norad']
    return set(owners)


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();hashes={};evidence={}
    def load(path,compact=True):
        d=read(path);hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        if compact:evidence[str(path)]=compact_replays(compact_evidence(d))
        return d
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=140);plt.close(fig)
    pr=load(args.batch/'protocol.json');execution=load(args.batch/'execution.json');retries=load(args.retry/'execution.json');load(args.retry/'protocol.json')
    results={r['job']['track_id']:r for r in execution};followups={r['job']['track_id']:r for r in retries}
    if set(results)!={j['track_id'] for j in pr['jobs']}:raise ValueError('missing terminal execution')
    ledgerpath=args.previous/'annotation_ledger.csv';ledger=list(csv.DictReader(ledgerpath.open()));hashes[str(ledgerpath)]=hashlib.sha256(ledgerpath.read_bytes()).hexdigest();byid={r['track_id']:r for r in ledger}
    pending=load(args.previous/'remaining_omitted_candidates.json');remaining=[r for r in pending if r['track_id'] not in results]
    if len(pending)-len(remaining)!=len(results):raise ValueError('batch not contained in previous remaining manifest')
    series=load(args.previous/'series_qualified_trials.json');prior_ids=reviewed_points(series)
    annotations=[];partitions=[];positions=[];final=[];gallery=[];executions=[];current_ids=set()
    for job in pr['jobs']:
        tid=job['track_id'];rec=results[tid];root=args.retry if tid in followups else args.batch;last=followups.get(tid,rec)
        inv=load(Path(job['inventory']));target=next(t for t in inv['tracks'] if t['track_id']==tid);source=Path(inv['job']['root'])/inv['job']['case']
        track=load(source/'tracks.json',False)[target['track_index']];metadata=load(source/'tracking.json',False)['source'];times=np.asarray(track['times'])
        validation=args.batch/tid/'annotation';ann=load(validation/'result.json');annpr=load(validation/'protocol.json');a=ann['annotation'];supported=a['status']=='conditionally_supported_identity'
        signatures=[]
        for f in ann['folds']:
            train,held=replay_split(times,f['split']);sig=tuple(np.flatnonzero(held));signatures.append(sig)
            partitions.append(dict(track_id=tid,scan=job['label'],seed=f['seed'],train_points=int(train.sum()),held_points=int(held.sum()),held_indices=' '.join(map(str,sig))))
        if supported:require_distinct_annotation(ann,annpr);assert len(set(signatures))==3
        annotations.append(dict(track_id=tid,scan=job['label'],points=job['points'],component=job['component'],status=a['status'],norad=a['norad'],
            minimum_margin=a.get('minimum_margin'),distinct_holdouts=len(set(signatures)),capture_mode=metadata['capture_mode'],sample_rate_hz=metadata['sample_rate_hz']))
        byid[tid].update(predictive_recheck_source=str(validation/'result.json'),predictive_recheck_state=a['status'],predictive_recheck_minimum_margin=a.get('minimum_margin'),
            annotation_likelihood_role='predictive_only; distinct timestamp-selected random partitions')
        row=dict(scan=job['label'],job_id=job['job_id'],track_id=tid,norad=a['norad'],points=job['points'],qualified=False,status=last['status'],
            c0_before_km=None,c0_after_km=None,fitted_c_before_km=None,fitted_c_after_km=None,final_trial='',capture_mode=metadata['capture_mode'],sample_rate_hz=metadata['sample_rate_hz'])
        plot=None
        for kind,where,r in [('distinct',args.batch,rec)]+([('numerical_followup',args.retry,followups[tid])] if tid in followups else []):
            load(where/(tid+'-terminal.json'));executions.extend(dict(scan=job['label'],iteration=kind,**st) for st in r['stages'])
            if r['status'] not in ('RF_verified_research_candidate','inclusion_rejected'):continue
            p=where/tid/'trial';tp=load(p/'protocol.json');c=load(p/'control.json');v=load(p/('target_0.json' if r['shared_family'] else 'new_family.json'));audit=load(p/'exact_owner_replay.json')
            for name,digest in audit['source_hashes'].items():
                if (hashes.get(name) or hashlib.sha256(Path(name).read_bytes()).hexdigest())!=digest:raise ValueError('changed replay source')
            passed=c['paired_valid'] and v['paired_valid'] and audit['all_verified'];assert passed==(r['status']=='RF_verified_research_candidate')
            is_final=where==root;ids=set(o for t in tp['targets'] for o in t['observation_ids'])
            for arm,z in v['arms'].items():
                d=target_diagnostic(z);noise={k:value[0].item() for k,value in batch_noise_screen(np.asarray(d['residual_hz'])[None],np.asarray(d['times_s'])).items()}
                old=set(c['arms'][arm]['proposed_associated_ids']);new=set(z['proposed_associated_ids'])
                if passed:assert new-old==ids and not old-new
                positions.append(dict(scan=job['label'],track_id=tid,norad=a['norad'],iteration=kind,final_variant=is_final,qualified=is_final and passed,arm=arm,
                    control_error_km=error(c['arms'][arm]),addition_error_km=error(z),baseline_points=len(old),proposed_points=len(new),
                    baseline_percent=100*len(old)/inv['summary'][0]['total_GLRT'],proposed_percent=100*len(new)/inv['summary'][0]['total_GLRT'],
                    credited_points=len(ids) if is_final and passed else 0,RMS_hz=d['RMS_hz'],control_pair_pass=c['paired_valid'],addition_pair_pass=v['paired_valid'],
                    exact_replay_pass=audit['all_verified'],optimizer_success=z['history'][-1].get('success'),phase_change_s=z['final_phase_change_s'],
                    control_objective=c['arms'][arm]['negative_twice_elbo'],addition_objective=z['negative_twice_elbo'],**noise))
            if is_final:
                plot=v;row.update(qualified=passed,final_trial=str(p),c0_before_km=error(c['arms']['c0']),c0_after_km=error(v['arms']['c0']),
                    fitted_c_before_km=error(c['arms']['fitted_c']),fitted_c_after_km=error(v['arms']['fitted_c']))
                if passed:
                    current_ids.update(ids);series.append(dict(track_id=tid,scan=job['label'],job_id=job['job_id'],norad=a['norad'],source_trial=str(p),
                        observation_ids=sorted(ids),iteration=args.batch.name,reviewed_candidate=True))
        byid[tid].update(predictive_inclusion_source=row['final_trial'],predictive_research_inclusion=last['status']+'; not production promoted')
        final.append(row);gallery.append((job,track,a['status'],plot,row['qualified']))
    cumulative=reviewed_points(series);groups=defaultdict(list)
    for row in series:
        if not row['reviewed_candidate']:continue
        p=load(Path(row['source_trial'])/'protocol.json');row['job_id']=p['job']['job_id'];groups[(row['job_id'],row['norad'])].append(row)
    joint_work=[]
    for key,rows in groups.items():
        if len(rows)<2:continue
        sources={byid[r['track_id']].get('same_family_joint_source','') for r in rows}
        checked=len(sources)==1 and '' not in sources and all(byid[r['track_id']].get('same_family_joint_status')=='RF_verified_joint_candidate' for r in rows)
        joint_work.append(dict(scan=rows[0]['scan'],job_id=key[0],norad=key[1],track_ids=[r['track_id'] for r in rows],already_joint_checked=checked))
    write(out/'joint_family_work.json',joint_work);write(out/'series_qualified_trials.json',series);write(out/'remaining_omitted_candidates.json',remaining)
    for name,rows in [('annotations.csv',annotations),('partitions.csv',partitions),('all_position_trials.csv',positions),('final_positions.csv',final),('annotation_ledger.csv',ledger),('executions.csv',executions)]:csvout(name,rows)
    summary=dict(batch=str(args.batch),selected=len(results),annotation_states=dict(Counter(r['status'] for r in annotations)),final_states=dict(Counter(r['status'] for r in final)),
        qualified_tracks=sum(r['qualified'] for r in final),qualified_points=len(current_ids),new_points=len(current_ids-prior_ids),
        prior_reviewed_points=len(prior_ids),cumulative_reviewed_points=len(cumulative),remaining=len(remaining),
        capture_modes=dict(Counter(r['capture_mode'] for r in annotations)),pending_same_family_joint_groups=sum(not r['already_joint_checked'] for r in joint_work),
        production_changed=False,full_goal_complete=False)
    write(out/'summary.json',summary)
    tested=[r for r in final if r['final_trial']];fig,axs=plt.subplots(1,2,figsize=(14,max(5,len(tested)*.45)),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        x=np.arange(len(tested));ax.barh(x-.16,[r[arm+'_before_km'] for r in tested],.32,color='#999');ax.barh(x+.16,[r[arm+'_after_km'] for r in tested],.32,color=['#009e73' if r['qualified'] else '#d55e00' for r in tested])
        ax.set(yticks=x,yticklabels=[r['scan']+' / '+str(r['norad']) for r in tested],xlabel='Evaluation position error (km)',title=arm);ax.invert_yaxis();ax.grid(axis='x',alpha=.2)
        ax.legend(handles=[Patch(color=c,label=n) for c,n in [('#999','Matched control'),('#009e73','Qualified candidate'),('#d55e00','Rejected addition')]],fontsize=8)
    save(fig,'position_comparison.png');pages=[]
    for page,start in enumerate(range(0,len(gallery),4),1):
        group=gallery[start:start+4];fig,axs=plt.subplots(len(group),2,figsize=(14,3.2*len(group)),layout='constrained',squeeze=False)
        for axes,(j,t,status,v,passed) in zip(axs,group,strict=True):
            axes[0].plot(t['times'],np.asarray(t['values'])/1000,'.',label='Native graph GLRT')
            if v:
                d=target_diagnostic(v['arms']['fitted_c']);axes[0].plot(d['times_s'],np.asarray(d['predicted_CFO_hz'])/1000,'k-',lw=.8,label='Causal prediction + nuisance terms')
                for arm,color in [('c0','#0072b2'),('fitted_c','#d55e00')]:
                    d=target_diagnostic(v['arms'][arm]);axes[1].plot(d['times_s'],d['residual_hz'],'.-',lw=.6,c=color,label=arm)
                axes[1].axhline(0,c='k',lw=.5);axes[1].set_ylabel('Residual (Hz)');axes[1].legend(fontsize=8)
            else:axes[1].text(.5,.5,status.replace('_',' ')+'\nNo inclusion authorized',ha='center',transform=axes[1].transAxes);axes[1].set_axis_off()
            axes[0].set(title=j['label']+' / '+j['component'].split('-RF')[0]+' / '+('QUALIFIED' if passed else 'UNRESOLVED'),ylabel='CFO (kHz)');axes[0].legend(fontsize=7)
            for ax in axes:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2)
        name=f'curves_{page}.png';save(fig,name);pages.append(f'![Curves {page}](figures/{name})')
    influence_text=''
    if args.influence:
        influence=load(args.influence/'result.json');receipt=load(args.influence.parent/(args.influence.name+'-terminal.json'))
        if receipt['status']!='complete':raise ValueError('influence diagnostic incomplete')
        for name,digest in influence['source_hashes'].items():
            if (hashes.get(name) or hashlib.sha256(Path(name).read_bytes()).hexdigest())!=digest:raise ValueError('changed influence source')
        ir=[];fig,axs=plt.subplots(2,2,figsize=(14,8),layout='constrained');resfig,resaxs=plt.subplots(1,2,figsize=(13,4),layout='constrained')
        for col,(arm,v) in enumerate(influence['arms'].items()):
            before=v['control'];after=v['with_target'];line=v['line'];xx=np.array([r['fraction']*v['position_shift_km'] for r in line])
            for key,label in [('incumbent_objective','Incumbent evidence'),('target_objective','Added family'),('joint_objective','Joint objective')]:
                axs[0,col].plot(xx,[r[key]-before[key] for r in line],'.-',label=label)
            for key,label in [('target_objective','Causal phase prior'),('uniform_phase_target_objective','Uniform phase prior diagnostic')]:
                axs[1,col].plot(xx,[r[key]-before[key] for r in line],'.-',label=label)
            for ax in axs[:,col]:
                ax.axvline(0,c='k',ls=':',lw=.8);ax.axvline(v['position_shift_km'],c='k',ls='--',lw=.8);ax.set(xlabel='Distance along control → addition direction (km)',ylabel='Objective change from control',title=arm);ax.grid(alpha=.2);ax.legend(fontsize=8)
            for key,label in [('control','At incumbent position'),('with_target','At updated position')]:
                d=v[key]['diagnostics'][0];resaxs[col].plot(d['times_s'],np.array(d['raw_residual_hz'])-d['profile_bias_hz'],'.-',lw=.7,label=label)
            resaxs[col].axhline(0,c='k',lw=.5);resaxs[col].set(title=arm,xlabel='Scan time (s)',ylabel='Target residual (Hz)');resaxs[col].legend(fontsize=8);resaxs[col].grid(alpha=.2)
            ir.append(dict(arm=arm,position_shift_km=v['position_shift_km'],weak_axis_alignment=v['direction_overlap_with_weak_axis'],
                incumbent_objective_change=after['incumbent_objective']-before['incumbent_objective'],target_objective_change=after['target_objective']-before['target_objective'],
                joint_objective_change=after['joint_objective']-before['joint_objective'],uniform_phase_target_change=after['uniform_phase_target_objective']-before['uniform_phase_target_objective'],
                local_curvature_long_axis_km=v['local_Gaussian_sigma_axes_km'][0],local_curvature_short_axis_km=v['local_Gaussian_sigma_axes_km'][1],
                endpoint_objective_replay_difference=v['endpoint_joint_difference_from_saved']))
        csvout('influence.csv',ir);save(fig,'influence_objective.png');save(resfig,'influence_residuals.png')
        influence_text=f'''## A passing association can still worsen the location estimate

AUTO-c1258263 / 60342 passes identity, residual and exact-orbit checks, yet fitted-c evaluation error increases from roughly **0.090 to 0.937 km**. The c=0 arm also worsens. This is a substantial adverse result, retained rather than removed through GPS-based selection. It blocks treating the present RF acceptance tests as sufficient for production promotion. A passing satellite label and a useful, correctly weighted position constraint are different claims.

We decomposed the objective along the control-to-addition direction and used a centered 25 m finite-difference stencil at the control. Both c arms use the trial's actual 0.025 s phase grid, the same causal physical uncertainty model, and phase-reference closure checks. The endpoint objectives replay within about four millionths. This diagnostic does not optimize at the evaluation GPS position or refit a position with a different prior.

{table(ir,['arm','position_shift_km','incumbent_objective_change','target_objective_change','joint_objective_change','uniform_phase_target_change'])}

![Objective decomposition](figures/influence_objective.png)

For fitted-c, the approximately **0.894 km** displacement costs the incumbent evidence only **1.041 objective units** while improving the added-family term by **2.751**, so the joint score prefers it by **1.710**. The displacement aligns about 0.814 with the weaker local curvature direction. The local curvature scales are about **0.987 and 0.666 km**; these are conditional diagnostics, not calibrated confidence intervals. The near-true original point estimate does not imply that the incumbent RF likelihood tightly fixes position.

Replacing only the added family's causal phase prior with a uniform prior in a fixed-position diagnostic retains **2.641** of the 2.751 target score improvement. Therefore the phase prior alone is not the main driver. This does not rule out other prior or receiver/orbit-model errors, nor prove the satellite identity wrong. It shows a modest target-frequency preference moving a position estimate through weakly constrained RF geometry.

![Target residual change](figures/influence_residuals.png)

At the incumbent position, the fitted-c target slope statistic is about **3.05**, just beyond the unchanged limit of 3; at the updated position it is about **1.89**. Target RMS falls from roughly **117 to 105 Hz** while location error grows. This illustrates why residual improvement alone cannot establish localization improvement. The next discriminating evidence is whether independent satellite families support the same displacement, and whether receiver-model discrepancies recur across families. A general influence or uncertainty rule must be evaluated across the cohort; it must not be tuned to retain this scan's fortunate baseline GPS error.

'''
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    coverage=[r for r in positions if r['final_variant'] and r['arm']=='fitted_c']
    text=f'''# Continuing omitted-track predictive recovery

This batch processes **{len(results)}** candidates from the previous immutable remaining manifest. **{summary['qualified_tracks']} tracks / {len(current_ids)} distinct points** qualify under the current predictive checks; **{len(current_ids-prior_ids)} points** are additional to the prior reviewed set. **{len(remaining)} candidates remain** in this omitted-curve queue. The full 1,630-curve objective and the larger calibration-participating annotation backlog remain unfinished.

## Validation, scope and model

Selection is by descending point count, without GPS error or satellite labels. Every supported identity is revalidated using three distinct timestamp-selected random scanwide 12-second holdouts and two-second guards. The report replays the held point sets and requires three distinct sets. Targets remain predictive evidence and do not calibrate receiver offsets or drift. Causal TLEs, physical nuisance priors, the 25 × 25 km regional start, and matched c=0/fitted-c data and budgets are retained. Evaluation GPS is used only to report error.

Annotation outcomes: **{summary['annotation_states']}**. Capture modes from raw tracking metadata: **{summary['capture_modes']}**. Filenames and inherited sample-rate fields are not used as capture-mode evidence. [annotations.csv](annotations.csv) records the mode, sample rate, identity and validation state for every curve. Insufficient partitions mean unavailable validation evidence, not a noise classification.

## Position inclusion and retained failures

New-family trials integrate causal phase at 0.025-second spacing and orbital/receiver uncertainty. Shared-family trials use existing family evidence. Controls and additions start at the same regional center. Only numerical-only failures passing physical, phase, ownership and exact-orbit checks receive a separate matched Powell retry in both c arms. The residual limits remain unchanged. Every original and retry result is retained in [all_position_trials.csv](all_position_trials.csv), with objectives, position errors and residual diagnostics reported separately.

{table(final,['scan','norad','points','qualified','status','c0_before_km','c0_after_km','fitted_c_before_km','fitted_c_after_km'])}

![Position comparisons](figures/position_comparison.png)

{table(coverage,['scan','qualified','baseline_percent','proposed_percent','credited_points'])}

Proposed coverage is shown for rejected trials but receives no credited points. Passing trials preserve all incumbent IDs and owners in exact orbit replay. More associated points do not necessarily improve location; evaluation error never selects a recovery or relaxes a gate. Scores for different observation counts are not directly comparable accuracy measures.

## Native curves and residuals

{chr(10).join(pages)}

Every selected curve is shown, including unresolved cases. No fitted satellite orbit is shown when refreshed identity validation does not authorize inclusion. Low RMS alone is insufficient; residual mean, slope, quadratic structure, steps and serial correlation remain checked.

{influence_text}

## Cumulative state and simultaneous-fit limits

The omitted-curve series contains **{len(cumulative)} distinct reviewed candidate points** after this batch, compared with {len(prior_ids)} before. Earlier review reversals are preserved: the two 67653 curves with a common residual bend remain withheld. The cumulative union rejects conflicting satellite ownership and avoids duplicate credit. It is an inventory of per-curve research candidates, **not a single simultaneous solution or dataset-wide location-accuracy result**.

[joint_family_work.json](joint_family_work.json) records same-scan/same-satellite groups and whether they already have an approved common-residual joint audit. **{summary['pending_same_family_joint_groups']} groups in this series still need such a joint check**. Different recovered families within a scan also require a simultaneous treatment of shared receiver uncertainty before a final combined scan result can be claimed. No earlier partial qualification is silently promoted.

The [updated 1,630-row ledger](annotation_ledger.csv), [remaining candidate manifest](remaining_omitted_candidates.json), and [reviewed series](series_qualified_trials.json) retain the next work and its provenance. [Execution receipts](executions.csv), exact-replay source hashes and compact evidence accompany the results. Production is unchanged; no future TLE, new RF acquisition, threshold relaxation or ALGO promotion is introduced.
'''
    (out/'README.md').write_text(text)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('batch','retry','previous','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--influence',type=Path,help='Optional completed fixed-position influence diagnostic')
    run(p.parse_args())
