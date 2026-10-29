"""Snapshot annotation coverage, predictive evidence, and inclusion controls."""
import argparse
import copy
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.grouped_prediction import identity_consensus,polynomial_reference,replay_split
from report_inventory_experiments import error

CORE=['ds24-0018','ds24-0099','v02','v08']


def compact_evidence(value):
    """Keep numerical evidence; hash repetitive IDs/optimizer traces for audit."""
    if isinstance(value,dict):
        result={}
        for key,v in value.items():
            if key in {'observation_ids','proposed_associated_ids','history'} and isinstance(v,list):
                result[key+'_receipt']=dict(count=len(v),sha256=hashlib.sha256(
                    json.dumps(v,separators=(',',':'),sort_keys=True).encode()).hexdigest())
            else:result[key]=compact_evidence(v)
        return result
    if isinstance(value,list):return [compact_evidence(v) for v in value]
    return value


def family_example(study,out):
    from annotate_track_predictively import prior_means
    from diagnose_all_large_tracks import context
    from ds23_frequency_events import make_event_problem,attach_event_predictive
    from probe_ds23_frequency_events import cached
    pair=read(study/'consensus-family-inclusion-v1/consensus_family_69713.json')
    controls={p.stem:read(p) for p in (study/'consensus-family-controls-v1').glob('*.json')}
    trials=dict(controls,both_tracks=pair);rows=[]
    for name,r in trials.items():
        for arm,v in r['arms'].items():
            rows.append(dict(trial=name,arm=arm,qualified=r['paired_valid'],error_km=error(v),
                added=v['added_points'],lost=v['lost_points'],RMS_hz=v['RMS_hz']))
    fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    names=['matched_no_target','ch2_only','ch5_only','both_tracks']
    for arm,offset,color in [('c0',-.16,'#4477aa'),('fitted_c',.16,'#ee6677')]:
        rr=[next(r for r in rows if r['trial']==name and r['arm']==arm) for name in names]
        axs[0].bar(np.arange(4)+offset,[r['error_km'] for r in rr],.3,color=color,label=arm)
        axs[1].bar(np.arange(4)+offset,[r['added'] for r in rr],.3,color=color,label=arm)
    for ax in axs:
        ax.set_xticks(range(4),['Matched control','CH2 only','CH5 only\nREJECTED','CH2 + CH5']);ax.grid(axis='y',alpha=.2);ax.legend()
    axs[0].set_ylabel('Evaluation error (km)');axs[1].set_ylabel('Proposed additional associated points')
    fig.suptitle('V06: two independently nominated tracks → 69713; no old point losses')
    fig.savefig(out/'figures/v06_family_ablation.png',dpi=145);plt.close(fig)
    inv=read(study/'all-large-track-recovery/0a6c35197cfa7afb/inventory.json');d=context(inv)
    p0,_=d['problems']['c0'];node=copy.deepcopy(d['node']);keep=d['keep'].copy();ks=[]
    v=pair['arms']['fitted_c']
    for component,norad in pair['proposal']['targets']:
        k=next(k for k,r in enumerate(p0.rows) if r['component']==component);ks.append(k)
        j=int(np.flatnonzero(d['scan'].norads==norad)[0]);node['seed']['rows'][k].update(candidate_index=j,candidate_norad=norad)
        # The full fit records physical phase and frequency. Recover its fixed
        # alias from the original nomination procedure, exactly as the trial did.
        from investigate_ds23_0268_remaining_tracks import family_frequency,corrected_observation
        from leo.analysis.research.retained_track_likelihood import profile
        i=p0.members[k];t=d['scan'].tracks[i];f,_=family_frequency(p0,d['problems']['c0'][1],j,times=t['times'])
        node['aliases'][k]=int(profile(corrected_observation(p0,d['problems']['c0'][1],i),t['rf_hz']/11.5e9*f,*d['scan'].white[i])['alias'][0])
        keep[p0.slices[k]]=True
    means,_=prior_means(d,node);kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
    p=make_event_problem(d['scan'],node,keep,'fitted_c',np.array(v['phase_reference']),d['powers'],means,d['model'],[],**kw)
    attach_event_predictive(p,d['entries'],d['powers']);cached(p);x=np.array(v['endpoint_east_north_km']);c=p.calculate(x)
    if not np.isclose(c['negative_twice_elbo'],v['negative_twice_elbo'],rtol=1e-10,atol=1e-5):raise ValueError('V06 full-fit replay mismatch')
    fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for col,k in enumerate(ks):
        t=p.scan.tracks[p.members[k]];sl=p.slices[k];r=c['conditional_residual_hz'][sl]
        axs[0,col].scatter(t['times'],p.values[sl]/1000,s=12,label='Original GLRT, fixed alias')
        axs[0,col].plot(t['times'],(p.values[sl]-r)/1000,color='#cc3311',label='69713 orbit + fitted receiver / priors')
        axs[0,col].set(title=f"RX{t['receiver']} CH{t['channel']} — {len(r)} points",ylabel='Unwrapped CFO (kHz)')
        axs[1,col].scatter(t['times'],r,s=12);axs[1,col].axhline(0,color='black',lw=.7)
        axs[1,col].set(title=f'Conditional residual RMS {np.sqrt(np.mean(r*r)):.1f} Hz',ylabel='Residual (Hz)')
    for ax in axs.flat:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2)
    for ax in axs[0]:ax.legend(fontsize=7)
    fig.suptitle('V06 recovered whole curves — fitted-c joint prototype, causal TLE only')
    fig.savefig(out/'figures/v06_recovered_curves.png',dpi=145);plt.close(fig)
    return rows,trials


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir()
    queue=args.study/'systematic-annotation-v1';protocol=read(queue/'protocol.json');ledger=[];completed={};folds=[]
    for row in protocol['rows']:
        path=Path(row['known_validation']) if row['known_validation'] else queue/row['track_id']
        entry=dict(row)
        if (path/'result.json').exists():
            result=read(path/'result.json');annotation=identity_consensus(result['folds']);completed[row['track_id']]=dict(result=result,annotation=annotation)
            entry.update(state=annotation['status'],norad=annotation['norad'],minimum_margin=annotation.get('minimum_margin'))
            for f in result['folds']:
                for q in f['proposals']:
                    for arm,r in q['arms'].items():
                        folds.append(dict(label=row['label'],component=row['component'],track_id=row['track_id'],seed=f['seed'],norad=q['norad'],arm=arm,
                            joint_score=r['scores']['joint']['negative_twice_log_density'],target_score=r['scores']['target']['negative_twice_log_density'],
                            existing_score=r['scores']['existing']['negative_twice_log_density'],target_RMS_hz=r['scores']['target']['rms_hz'],
                            final_phase_change_s=r['final_phase_change_s'],minimum_elevation_deg=r['minimum_target_elevation_deg']))
        else:
            receipts=list(queue.glob('attempt-*/'+row['track_id']+'-terminal.json'))
            if receipts:
                entry['execution']=read(receipts[-1]);entry['state']='execution_'+entry['execution']['status']
        ledger.append(entry)
    write(out/'execution_receipts.json',[read(p) for p in sorted(queue.glob('attempt-*/*-terminal.json'))])
    with (out/'annotation_ledger.csv').open('x') as f:
        keys=['track_id','label','component','points','state','norad','minimum_margin','engine_member']
        w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows({k:r.get(k) for k in keys} for r in ledger)
    with (out/'predictive_scores.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(folds[0]),lineterminator='\n');w.writeheader();w.writerows(folds)
    core={};fit_rows=[];poly=[]
    for case in CORE:
        r=read(args.study/f'predictive-annotation-{case}-v1/result.json');pr=read(args.study/f'predictive-annotation-{case}-v1/protocol.json')
        track=read(Path(pr['job']['root'])/pr['job']['case']/'tracks.json')[pr['target']['track_index']]
        annotation=identity_consensus(r['folds']);core[case]=dict(validation=r,protocol=pr,annotation=annotation,models={})
        for fold in r['folds']:
            train,held=replay_split(track['times'],fold['split']);ref=polynomial_reference(track['times'],track['values'],train,held)
            poly.append(dict(case=case,seed=fold['seed'],order=ref['order'],RMS_hz=ref['held']['rms_hz']))
        for model,stem,control_stem in [('original','predictive-inclusion','predictive-control'),
                ('all_active_prior','predictive-orbit','predictive-orbit-control'),('target_prior','predictive-target-orbit','predictive-control')]:
            for predictive in ['curved_only','with_predictive']:
                revision='v1' if model=='original' else 'v2'
                control_revision='v2' if model=='all_active_prior' else 'v1'
                fit=read(args.study/f'{stem}-{case}-{revision}'/f'{predictive}.json')
                control=read(args.study/f'{control_stem}-{case}-{control_revision}'/f'{predictive}.json')
                core[case]['models'][model+'_'+predictive]=dict(fit=fit,control=control)
                for arm in ['c0','fitted_c']:
                    v=fit['arms'][arm];c=control['arms'][arm]
                    fit_rows.append(dict(case=case,model=model,predictive=predictive,arm=arm,qualified=fit['paired_valid'],
                        original_error_km=error(fit['baseline'][arm]),control_error_km=error(c),target_error_km=error(v),
                        added=v['added_points'],lost=v['lost_points'],RMS_hz=v['RMS_hz'],control_qualified=control['paired_valid']))
    family_rows,family_trials=family_example(args.study,out)
    v02_trials={p.stem:read(p) for p in (args.study/'consensus-v02-inclusion-v1').glob('*.json')}
    v02_trials['ch4_65894']=read(args.study/'all-large-joint-v02/65894.json')
    v02_rows=[]
    for name,trial in v02_trials.items():
        for arm,v in trial['arms'].items():v02_rows.append(dict(trial=name,arm=arm,error_km=error(v),
            added=v['added_points'],lost=v['lost_points'],qualified=trial['paired_valid']))
    write(out/'results.json',dict(states=Counter(r['state'] for r in ledger),annotations=ledger,folds=folds,
        polynomial_references=poly,full_fit_comparisons=fit_rows,family_ablation=family_rows,v02_joint_replacements=v02_rows,
        remaining_goal='validate all identities and a generally useful inclusion rule'))
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(dict(completed=completed,core=core,family_trials=family_trials,v02_trials=v02_trials)),f,separators=(',',':'))
    fig,ax=plt.subplots(figsize=(8,4),layout='constrained');names=['ch3_61851','ch4_65894','ch3_61851_ch4_65894']
    for arm,offset,color in [('c0',-.16,'#4477aa'),('fitted_c',.16,'#ee6677')]:
        ax.bar(np.arange(3)+offset,[next(r['error_km'] for r in v02_rows if r['trial']==name and r['arm']==arm) for name in names],.3,color=color,label=arm)
    ax.set(xticks=range(3),xticklabels=['CH3 → 61851','CH4 → 65894','Both replacements'],ylabel='Evaluation error (km)',
        title='V02: simultaneous identity corrections — all proposals rejected');ax.legend();ax.grid(axis='y',alpha=.2)
    fig.savefig(out/'figures/v02_joint_replacements.png',dpi=145);plt.close(fig)
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for ax,case in zip(axs.flat,CORE):
        votes=core[case]['annotation']['votes']
        for arm,offset,color in [('c0',-.16,'#4477aa'),('fitted_c',.16,'#ee6677')]:
            v=[r for r in votes if r['arm']==arm];ax.bar(np.arange(len(v))+offset,[r['margin'] for r in v],.3,label=arm,color=color)
        ax.axhline(10,color='black',ls='--',lw=.7);ax.set(title=case+' → '+str(core[case]['annotation']['norad']),
            xticks=range(3),xticklabels=['20261029','94721','4081'],ylabel='Joint predictive advantage over runner-up',xlabel='Random partition seed');ax.legend();ax.grid(axis='y',alpha=.2)
    fig.suptitle('Identity evidence from withheld blocks; score difference, not a calibrated probability')
    fig.savefig(out/'figures/identity_evidence.png',dpi=145);plt.close(fig)
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for ax,case in zip(axs.flat,CORE):
        for arm,offset,color in [('c0',-.1,'#4477aa'),('fitted_c',.1,'#ee6677')]:
            rr=[r for r in fit_rows if r['case']==case and r['arm']==arm and r['predictive']=='with_predictive']
            ax.plot(np.arange(3)+offset,[r['control_error_km'] for r in rr],'o--',c=color,label=arm+' matched control')
            ax.plot(np.arange(3)+offset,[r['target_error_km'] for r in rr],'s-',c=color,label=arm+' plus target')
        ax.axhline(.5,color='gray',ls=':',lw=1);ax.set(title=case,xticks=range(3),xticklabels=['Existing orbit rule','All active prior','Target prior'],ylabel='Evaluation error (km)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('Position effect of inclusion: matched controls, same priors and predictive rows\nRejected proposals are shown diagnostically; none is deployed')
    fig.savefig(out/'figures/inclusion_errors.png',dpi=145);plt.close(fig)
    fig,axs=plt.subplots(4,1,figsize=(13,8),layout='constrained')
    for ax,case in zip(axs,CORE):
        pr=core[case]['protocol'];track=read(Path(pr['job']['root'])/pr['job']['case']/'tracks.json')[pr['target']['track_index']]
        for k,f in enumerate(core[case]['validation']['folds']):
            train,held=replay_split(track['times'],f['split']);t=np.array(track['times'])
            for mask,color,label in [(train,'#4477aa','Training'),(held,'#ee6677','Held'),(~train&~held,'0.7','Guard excluded')]:ax.scatter(t[mask],np.full(mask.sum(),k),s=8,color=color,label=label if k==0 else None)
        ax.set(title=case,yticks=range(3),yticklabels=['20261029','94721','4081'],xlabel='Track time (s)');ax.legend(ncol=3,fontsize=7);ax.grid(alpha=.15)
    fig.suptitle('Random scan-wide 12-second groups with 2-second guards; shared across RX/CH')
    fig.savefig(out/'figures/random_groups.png',dpi=145);plt.close(fig)
    unstable=[r for r in ledger if r['state']=='unstable_identity'][:4]
    if unstable:
        fig,axs=plt.subplots(1,len(unstable),figsize=(4*len(unstable),4),layout='constrained',squeeze=False)
        for ax,row in zip(axs.flat,unstable):
            rr=completed[row['track_id']]['result']['folds'];candidates=sorted({q['norad'] for f in rr for q in f['proposals']})
            matrix=np.full((len(rr),len(candidates)),np.nan)
            for k,f in enumerate(rr):
                values={q['norad']:q['arms']['fitted_c']['scores']['joint']['negative_twice_log_density'] for q in f['proposals']}
                best=min(values.values())
                for j,norad in enumerate(candidates):
                    if norad in values:matrix[k,j]=values[norad]-best
            ax.imshow(np.log1p(matrix),aspect='auto',cmap='Blues')
            for (i,j),value in np.ndenumerate(matrix):
                color='red' if value==0 else 'white' if value>20 else 'black'
                ax.text(j,i,'absent' if not np.isfinite(value) else f'{value:.1f}',ha='center',va='center',fontsize=8,color=color)
            ax.set(xticks=range(len(candidates)),xticklabels=candidates,yticks=range(len(rr)),
                yticklabels=[str(f['seed']) for f in rr],title=row['label']+'\n'+row['component'].split('-RF')[0],xlabel='Satellite NORAD')
            ax.tick_params(axis='x',labelrotation=45)
        fig.suptitle('Ambiguous evidence stays unresolved: fitted-c joint score above each partition winner\nZero/red = winner; color uses log(1 + score difference). No GPS used.')
        fig.savefig(out/'figures/unstable_identities.png',dpi=145);plt.close(fig)
    counts=Counter(r['state'] for r in ledger)
    family_table=['| Trial | c0 error km | Fitted-c error km | Added points (both arms) | Paired checks |','|---|---:|---:|---:|---|']
    for name in ['matched_no_target','ch2_only','ch5_only','both_tracks']:
        a,b=[next(r for r in family_rows if r['trial']==name and r['arm']==arm) for arm in ['c0','fitted_c']]
        family_table.append(f"| {name} | {a['error_km']:.3f} | {b['error_km']:.3f} | {a['added']} / {b['added']} | {'Pass' if a['qualified'] else 'Reject'} |")
    table=['| State | Tracks |','|---|---:|']+[f'| {k} | {v} |' for k,v in counts.items()]
    it=['| Track | NORAD | Minimum held-score margin |','|---|---:|---:|']
    for case in CORE:
        a=core[case]['annotation'];it.append(f"| {case} | {a['norad']} | {a['minimum_margin']:.1f} |")
    pos=['| Case | Model | c0 matched control → target km | Fitted-c matched control → target km | Paired qualification |','|---|---|---:|---:|---|']
    for case in CORE:
        for model in ['original','all_active_prior','target_prior']:
            rr=[r for r in fit_rows if r['case']==case and r['model']==model and r['predictive']=='with_predictive']
            a,b=rr;pos.append(f"| {case} | {model} | {a['control_error_km']:.3f} → {a['target_error_km']:.3f} | {b['control_error_km']:.3f} → {b['target_error_km']:.3f} | {'Pass' if a['qualified'] else 'Reject'} |")
    text=f'''# Systematic annotation: randomized joint prediction, then controlled inclusion

The [preceding inventory](../2026_10_29_all_large_track_inventory/README.md) found 1,630 large tracks in the union of c arms. This iteration adds a reusable annotation procedure, a queue that preserves every track, and controlled inclusion experiments. **The full goal is still active.** A conditionally supported identity is not a confirmed label or permission to use a track for position.

## Coverage at this snapshot

{chr(10).join(table)}

The [complete ledger](annotation_ledger.csv) includes every available inventoried track across 277 recordings. DS24 revision 2 contains 103 members: nine lack the exports needed for a GLRT inventory, and DS24-0056 / DS25-0037 has no active curvature (its four graph tracks also fail the large-track size threshold). These limitations are retained from the preceding inventory. Coherent points outside existing graph tracks remain a separate task.

The 274 tracks absent from the curved calibration design need a predictive-only implementation; they are not silently dropped or used to calibrate receivers. Queued tracks have not passed validation. [Execution receipts](execution_receipts.json) distinguish completed, failed and timed-out attempts. Counts are a snapshot, not a promise that an unobserved process is still running.

## Reproducible annotation procedure

1. Keep the graph, original point IDs and incumbent family hypotheses frozen. Remove the target from calibration. Partition the **entire scan** into randomly selected 12-second blocks, shared across receivers and channels. Ensure target training/held support, and purge training points within two seconds of held-block boundaries. Seeds are 20261029, 94721 and 4081.
2. Refit receiver, phase and position using training data only, starting at the regional center of the existing 25 × 25 km box. Use fixed 150 Hz measurement scales and unit family weights, so full-data RF confidence/noise selection does not enter the validation fit. Pre-scan TLE priors remain unchanged. Predictive linear rows are excluded from this first validation prototype.
3. Nominate satellites from the full existing causal bank using only training target points and training receiver correction. Search both training endpoints and a nine-point regional grid with phase ±15 s. Union nominations across c arms, retain three distinct candidates, and explicitly challenge against the incumbent nominee. Instantiate missing priors from the same pre-scan TLE mechanism.
4. Jointly refit each hypothesis on the same training observations with five phase-refresh rounds and 48 position steps per round. Fit aliases from training data and keep them matched across c arms. Score the same held target and existing curved points under their joint Gaussian predictive covariance. This propagates coefficient uncertainty; fitted position and learned noise precision remain plug-in approximations.
5. Annotate an identity as *conditionally supported* only if the same satellite wins every partition and both c arms, has a score margin ≥10 against the tested runner-up, predicts held target points within 450 Hz RMS, remains visible and converges in phase. Preserve ambiguous, unstable and mismatch states. These margins are **not calibrated probabilities**.
6. Refit all data separately to test inclusion. Report old-point losses, every residual gate, c=0/fitted-c, and position error separately. Compare against a no-target control with the same noise, weights, priors and predictive rows. Never select the model using evaluation coordinates.

![Random groups](figures/random_groups.png)

The graph and incumbent identities were constructed using the full recording. These are therefore conditional validation experiments, not a blind acquisition-to-position holdout. Random partitions overlap in information and are not independent datasets. Future validation needs withheld scans and synthetic false-identity/merge controls.

## Identity results

{chr(10).join(it)}

![Predictive identity evidence](figures/identity_evidence.png)

V02's large CH4 track supports 65894, absent from the old association model. On the first partition its held RMS is 140–144 Hz, versus about 28 kHz for 62750. Other cases support their existing candidate identities even though the full-data residual checks had rejected those curves. This separates an identity problem from a residual-model problem. [All fold/candidate scores](predictive_scores.csv) retain target and existing-evidence scores separately.

![Unstable identity evidence](figures/unstable_identities.png)

Several unresolved tracks change winners even though the same competitors were tested in every partition. They need stronger independent evidence or a better discrepancy model; forcing the most frequent winner would conceal this ambiguity. In DS24-0014's largest tested CH1 curve, two partitions strongly prefer 59733 but the third barely favors 69186 (less than one score unit). That is insufficient for the declared consensus rule.

## Inclusion is a separate problem

{chr(10).join(pos)}

![Matched position controls](figures/inclusion_errors.png)

With the existing orbital rule, DS24-0018 and DS24-0099 can pass the paired gates with their full tracks restored under the fixed-noise/unit-weight prototype. Nevertheless, their position errors worsen relative to matched controls. The apparent DS24-0018 improvement against the old production model disappears once the model-only change is controlled. This is why neither better coverage nor a better self-fit establishes better localization. Control qualification is recorded separately in the machine-readable results; a rejected control is diagnostic, not a deployable baseline.

V02's other retained-track failure is narrowly a step-statistic failure (roughly 4.0–4.1 versus the 4.0 cutoff), rather than a gross RMS discrepancy. V08 loses old postfit points from another satellite. A rule that checks only the newly added track would overlook these effects.

## Orbital-uncertainty ablation

The code previously omitted the three physical orbit-error modes when a family had only one owner. DS24-0018/56781 and DS24-0099/67921 were such families. A lack of multiple observations does not establish zero orbit error, so two opt-in hypotheses were tested: causal prior variance for all active families, and adding it only for the new target while preserving incumbent modes. Both use the existing pre-scan TLE difference scales, with no position-error tuning.

An initial evaluation mistakenly subjected newly added prior-only modes to the incumbent rule requiring two accepted receiver/channel owners. That rejects the single-owner experiment by construction. The corrected evaluation preserves the incumbent owner requirements and distinguishes added prior uncertainty from learned multi-owner support. It changes no numeric residual threshold. Every fit was replayed at its saved parameters, with RMS and objective equality checked; the table uses those corrected results. The `replayed_from` receipts preserve the initial failed evaluations.

DS24-0099 is a useful lead: target-only uncertainty passes the checks, adds 151 points without losses, and improves the matched fixed-noise control from 0.959 to 0.870 km in c0 and 0.939 to 0.819 km with fitted-c. Its old production fitted-c error was approximately 0.602 km, so this is **not an improvement over production**. DS24-0018 still worsens relative to its matched control. V02 and V08 remain rejected. These tests therefore do not establish a general inclusion rule. The engineering covariance scales are not calibrated forecasts; they were not widened based on GPS error.

## Independent cross-band nominations: V06

The 83-point RX2 CH2 and 85-point RX2 CH5 curves independently nominate **69713** under all three randomized partitions and both c arms, replacing their old 67664 hypotheses. Their joint full-data fit uses the original production noise/weights, with a matched no-target rerun and single-track ablations. The combined proposal adds 223 points: 168 target points plus 55 postfit associations. Association rises from 3,367 / 5,372 (**62.68%**) to 3,590 / 5,372 (**66.83%**) in each arm. It loses no old points and passes the existing checks. CH5 alone fails, so corroboration is useful here.

{chr(10).join(family_table)}

![V06 ablation](figures/v06_family_ablation.png)

![V06 GLRT and expected orbit](figures/v06_recovered_curves.png)

CH5 alone fails lag-one autocorrelation (0.468 in fitted-c versus 4/√85 ≈ 0.434), despite only 27 Hz RMS. Joint recovery reduces its RMS to 24 Hz and autocorrelation to 0.328, passing the unchanged criterion. The matched control exactly reproduces the original endpoint. Despite the recovered signal and lower frequency RMS, joint fitted-c position error rises from 0.265 to 0.405 km. Both are below 500 m in this scan, but the recovery is not a demonstrated accuracy gain. No promotion or deployment follows from these results.

## V02: two simultaneous corrections do not resolve the conflict

The new annotation queue also supports 61851 for the 81-point RX1 CH3 T001 curve. A bounded follow-up tested it alone and together with the 102-point CH4 → 65894 correction, using the original model, causal catalogue and identical c-arm budgets. Both remain rejected. The joint proposal would add 196 points but loses 12 old points; its fitted-c error is 3.189 km, versus 2.760 km for the earlier CH4-only proposal and 6.768 km for the incumbent.

![V02 simultaneous replacements](figures/v02_joint_replacements.png)

In the combined fit, the old retained CH5 family passes, but the new CH3 curve fails: 226 Hz RMS, slope 6.74σ, quadratic BIC gain 56.9, step 6.53σ and lag-one correlation 0.608. The target's identity evidence is therefore not a certificate that its full curve is modeled adequately. No points were trimmed or gates relaxed to rescue this result. This is a documented unresolved case; further work should compare shared receiver versus satellite-specific discrepancy, alongside progress on other queued tracks.

## Remaining work toward the full goal

- Complete annotation of all queued large tracks and implement predictive-only handling for the 274 tracks outside the calibration design.
- Validate identity confidence against incorrect satellites, merged curves, structured residuals and unused scans. The currently tested runner-ups do not exhaust every joint association configuration.
- Combine independently supported same-family tracks, then verify that joint inclusion preserves other evidence or identifies a demonstrably wrong incumbent association.
- Calibrate receiver/orbit model discrepancy without using location truth. Use the training-selected polynomial reference only to measure unexplained signal shape, never as a satellite identity or receiver calibration.
- Demonstrate position benefit on matched controls and broader datasets before promotion. Production remains unchanged.

The [results](results.json) and [compressed evidence](evidence.json.gz) contain failed and successful diagnostics. Repetitive observation-ID lists and optimizer histories are represented by count/SHA-256 receipts; complete original files remain in the recorded study paths. Research tools are `annotate_track_predictively.py` and `run_annotation_inventory.py`; the queue is `/srv/bulk/leo/research/ch78-qualified-cohort-20261029/systematic-annotation-v1`. Twenty-four focused numerical and policy tests passed, including actual retention of a clean prior-only curve and rejection of a 300 Hz step. The orbital gate replay verified identical fitted RMS/objectives before applying the corrected qualification rule. This report does not mark the goal complete.

## Reproduction

Run from the repository with `PYTHONPATH=src:tools`, `OPENBLAS_NUM_THREADS=1` and `OMP_NUM_THREADS=1`, using its virtual environment. Corpus access uses the read-authorized `leo` account. All output directories must be new; existing results are never overwritten.

- One annotation: `tools/annotate_track_predictively.py --inventory INVENTORY_JSON --track TRACK_ID --output NEW_DIRECTORY` (three partitions, three nominated competitors plus incumbent).
- Inclusion: the same command with `--validation ANNOTATION_DIRECTORY`; matched control: `--control`. Add `--orbital-policy active_uncertainty` or `--orbital-policy target_uncertainty` for the controlled prior hypotheses.
- Resume a bounded queue batch: `tools/run_annotation_inventory.py run --output QUEUE_DIRECTORY --limit 16`. Eight workers, 600-second cap per track, terminal receipts; failed attempts require diagnosis before rerunning.
- Report: `tools/report_systematic_annotation.py --study STUDY_DIRECTORY --output NEW_REPORT_DIRECTORY`. Evaluation coordinates enter only reporting code.
- Tests: `pytest tests/analysis/test_grouped_prediction.py tests/analysis/test_orbital_support.py tests/analysis/test_track_recovery_diagnostics.py tests/analysis/test_polynomial_satellite_diagnostics.py tests/analysis/test_algo02_scan_tool.py`.
'''
    (out/'README.md').write_text(text)
    sources=['src/leo/analysis/research/grouped_prediction.py','src/leo/analysis/research/orbital_support.py',
        'tools/annotate_track_predictively.py','tools/run_annotation_inventory.py','tools/probe_ds23_history_calibrated_phase.py',
        'tools/audit_ds23_algo01_coverage.py','tools/replay_annotation_orbital_gates.py',__file__]
    write(out/'source_sha256.json',{str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources})
    print(counts,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())
