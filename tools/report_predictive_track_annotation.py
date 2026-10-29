"""Publish a reproducible snapshot of predictive-only annotations and trials."""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.grouped_prediction import identity_consensus
from report_inventory_experiments import error
from report_systematic_annotation import compact_evidence


def table(rows,columns):
    def fmt(v):
        return f'{v:.3f}' if isinstance(v,float) else str(v)
    return '\n'.join(['| '+' | '.join(columns)+' |','| '+' | '.join(['---']*len(columns))+' |']+
                     ['| '+' | '.join(fmt(r.get(k,'')) for k in columns)+' |' for r in rows])


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);figures=out/'figures';figures.mkdir()
    sources={};evidence={}
    def load(path):
        path=Path(path);sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return read(path)
    exact={};exact_rows=[]
    for p in sorted(s.glob('exact-uncalibrated-annotation-*-v1/result.json')):
        r=load(p);exact[r['track_id']]=(r,load(p.parent/'protocol.json'),str(p))
    queue=s/'systematic-annotation-v1';protocol=load(queue/'protocol.json');ledger=[];states={True:Counter(),False:Counter()}
    for row in protocol['rows']:
        entry=dict(row);folder=Path(row['known_validation']) if row['known_validation'] else queue/row['track_id']
        if (folder/'result.json').exists():
            r=load(folder/'result.json');annotation=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
            if r.get('annotation') and r['annotation']!=annotation:raise ValueError('annotation replay mismatch')
            entry.update(base_state=annotation['status'],base_norad=annotation['norad'])
            evidence[row['track_id']]=dict(result=r,protocol=load(folder/'protocol.json'))
            source=str(folder/'result.json')
            if row['track_id'] in exact:
                revised,pr,source=exact[row['track_id']];updated=identity_consensus(revised['folds'],score_name='conditional_target')
                exact_rows.append(dict(scan=row['label'],component=row['component'],original_norad=annotation['norad'],revised_norad=updated['norad'],
                    revised_status=updated['status'],minimum_margin=updated.get('minimum_margin')))
                evidence[row['track_id']]['exact_recheck']=dict(result=revised,protocol=pr);annotation=updated
            entry.update(state=annotation['status'],norad=annotation['norad'],minimum_margin=annotation.get('minimum_margin'),
                         score_name=r.get('identity_score_name','joint'),source=str(folder/'result.json'))
            entry['source']=source
        else:
            receipts=sorted(queue.glob('attempt-*/'+row['track_id']+'-terminal.json'))
            if receipts:entry['state']='execution_'+load(receipts[-1])['status']
        states[row['engine_member']][entry['state']]+=1;ledger.append(entry)
    assert len(ledger)==1630 and len({r['track_id'] for r in ledger})==1630
    keys=['track_id','job_id','label','component','points','span_s','engine_member','state','norad','minimum_margin','base_state','base_norad','score_name','source']
    with (out/'annotation_ledger.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows({k:r.get(k) for k in keys} for r in ledger)
    fits=[];trials={}
    folders=sorted(s.glob('predictive-only-inclusion-*-v1'))+sorted(s.glob('predictive-orphan-phase-*-v1'))+sorted(s.glob('predictive-orphan-orbit-*-v1'))
    folders+=[p.parent for p in sorted((s/'additional-predictive-inclusions-v1').glob('*/control.json'))]
    for folder in folders:
        if not (folder/'control.json').exists():continue
        control=load(folder/'control.json');pr=load(folder/'protocol.json')
        for p in sorted(folder.glob('*.json')):
            if p.stem=='protocol':continue
            d=load(p)
            if 'arms' not in d:continue
            trials[str(p)]=d
            for arm,v in d['arms'].items():
                fits.append(dict(scan=d['job']['label'],model='phase+orbit' if d.get('orphan_orbit_prior') else 'phase' if d.get('orphan_phase_refresh') else 'original',
                    variant=p.stem,arm=arm,qualified=d['paired_valid'],control_error_km=error(control['arms'][arm]),error_km=error(v),
                    added=v['added_points'],lost=v['lost_points'],curved_RMS_hz=v['RMS_hz'],
                    objective=v['negative_twice_elbo'],control_objective=control['arms'][arm]['negative_twice_elbo'],
                    target_components='; '.join(e['component'] for e in d.get('target_entries',[])),
                    failed_predictive='; '.join(g['component'] for g in v['linear_gates'] if not g['compatible']),source=str(p)))
    with (out/'inclusion_trials.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(fits[0]),lineterminator='\n');w.writeheader();w.writerows(fits)
    diagnostics={};gallery=[]
    for prefix in ['predictive-only-inclusion','predictive-orphan-phase','predictive-orphan-orbit']:
        folder=s/(prefix+'-diagnostics-v1')
        for p in sorted(folder.glob('*.json')):
            diagnostics[prefix+'/'+p.stem]=load(p)
            png=p.with_suffix('.png');dest=figures/(prefix+'-'+png.name);shutil.copy2(png,dest)
            gallery.append(f'### {prefix}: {p.stem}\n\n![CFO and residual diagnostics](figures/{dest.name})\n')
    # Overview distinguishes assessed identities from accepted position updates.
    order=['conditionally_supported_identity','ambiguous_identity','unstable_identity','prediction_mismatch','insufficient_partitions','queued']
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,role,title in [(axs[0],False,'274 tracks outside curved calibration'),(axs[1],True,'1,356 curved-model tracks')]:
        names=[n for n in order if states[role][n]];counts=[states[role][n] for n in names]
        ax.barh(range(len(names)),counts,color=['#228833' if n==order[0] else '#4477aa' for n in names]);ax.invert_yaxis()
        ax.set(yticks=range(len(names)),yticklabels=[n.replace('_',' ') for n in names],title=title,xlabel='Tracks')
        for i,n in enumerate(counts):ax.text(n,i,' '+str(n),va='center')
        ax.set_xlim(0,max(counts)*1.15);ax.grid(axis='x',alpha=.2)
    fig.suptitle('Satellite identity evidence — conditional support does not authorize inclusion')
    fig.savefig(figures/'annotation_coverage.png',dpi=145);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4),layout='constrained')
    for k,r in enumerate(exact_rows):
        entry=next(v for v in ledger if v['component']==r['component'] and v['label']==r['scan'])
        before=evidence[entry['track_id']]['result']['annotation']['minimum_margin']
        ax.bar(k-.18,before,.34,color='#4477aa',label='Original linearized family' if k==0 else None)
        ax.bar(k+.18,r['minimum_margin'],.34,color='#ee6677',label='Explicit causal phase integration' if k==0 else None)
    ax.axhline(10,c='black',ls='--',label='Required margin');ax.set(xticks=range(len(exact_rows)),
        xticklabels=[r['scan']+'\n'+str(r['original_norad'])+' → '+str(r['revised_norad']) for r in exact_rows],
        ylabel='Minimum conditional score advantage',title='Uncertainty-model sensitivity: V06 identity becomes ambiguous')
    ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2);fig.savefig(figures/'exact_phase_sensitivity.png',dpi=145);plt.close(fig)
    # Matched position effects for the three phase-refresh cases.
    fig,axs=plt.subplots(1,3,figsize=(14,4.5),layout='constrained')
    for ax,case,variant in zip(axs,['DS24-0077','DS24-0095','V06'],['target_0','target_0','target_1'],strict=True):
        models=['original','phase']+(['phase+orbit'] if case=='DS24-0077' else [])
        for arm,color,offset in [('c0','#4477aa',-.06),('fitted_c','#ee6677',.06)]:
            original=next(r for r in fits if r['scan']==case and r['model']=='original' and r['variant']==variant and r['arm']==arm)
            rr=[next(r for r in fits if r['scan']==case and r['model']==m and r['target_components']==original['target_components'] and r['arm']==arm) for m in models]
            ax.plot(np.arange(len(models))+offset,[r['error_km'] for r in rr],'s-',color=color,label=arm+' target included')
            ax.axhline(rr[0]['control_error_km'],color=color,ls='--',label=arm+' matched control')
        ax.set(xticks=range(len(models)),xticklabels=models,title=case,ylabel='Evaluation position error (km)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('All shown inclusion proposals rejected; error is evaluated after inference')
    fig.savefig(figures/'matched_position_errors.png',dpi=145);plt.close(fig)
    fig,axs=plt.subplots(2,3,figsize=(14,7),layout='constrained');root_rows=[]
    for col,(prefix,label) in enumerate([('predictive-only-inclusion','Original prediction'),('predictive-orphan-phase','Refresh uncalibrated phase'),('predictive-orphan-orbit','Phase + causal orbit prior')]):
        r=next(r for r in diagnostics[prefix+'/ds24-0077-target_0']['rows'] if r['arm']=='fitted_c' and 'CH5' in r['component'])
        root_rows.append(dict(model=label,bias_hz=r['profile_bias_hz'],RMS_hz=r['profile_RMS_hz'],slope_sigma=r['profile_noise']['slope_z'],step_sigma=r['profile_noise']['maximum_step_z'],acf=r['profile_noise']['lag1_acf']))
        t=r['times_s'];axs[0,col].scatter(t,np.array(r['CFO_hz'])/1000,s=18,label='Observed GLRT')
        axs[0,col].plot(t,np.array(r['prediction_CFO_hz'])/1000,c='#cc3311',label='Orbit + receiver prediction');axs[0,col].legend(fontsize=7)
        axs[0,col].set(title=label,ylabel='CFO (kHz)')
        residual=np.array(r['raw_residual_hz'])-r['profile_bias_hz'];axs[1,col].scatter(t,residual,s=18);axs[1,col].axhline(0,c='black',lw=.7)
        axs[1,col].set(title=f"Bias {r['profile_bias_hz']:.1f} Hz; RMS {r['profile_RMS_hz']:.1f} Hz",ylabel='Residual after bias profiling (Hz)')
    for ax in axs.flat:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2)
    fig.suptitle('DS24-0077 RX2 CH5 → candidate 58053: 39 points; fitted-c prototypes\nPanel scales differ; whole-scan inclusion remains rejected')
    fig.savefig(figures/'phase_model_root_cause.png',dpi=145);plt.close(fig)
    write(out/'results.json',dict(states={str(k):dict(v) for k,v in states.items()},ledger=ledger,inclusion_trials=fits,root_cause=root_rows,exact_phase_rechecks=exact_rows,
                                 no_production_change=True,goal_complete=False))
    write(out/'source_sha256.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(dict(annotations=evidence,trials=trials,diagnostics=diagnostics)),f,separators=(',',':'))
    (out/'GALLERY.md').write_text('# Predictive-track diagnostics\n\nRaw GLRT and fitted-c residual plots. These are diagnostic proposals, not deployed associations. The covariance-aware panel does not change acceptance.\n\n'+'\n'.join(gallery))
    assessed=len(evidence);pending=1630-assessed
    counts=[dict(status=k,predictive_only=states[False][k],curved_model=states[True][k]) for k in order if states[False][k] or states[True][k]]
    fit_table=[{k:r[k] for k in ['scan','model','variant','arm','control_error_km','error_km','added','lost','qualified']} for r in fits if r['variant']!='control']
    text=f'''# Systematic track annotation: predictive evidence and the missing satellite phase

The inventory contains **1,630 large unassociated graph tracks across 277 canonical recordings**. This snapshot has assessed **{assessed} tracks**, with **{pending} remaining**. All 274 tracks outside the curved calibration model now have a recorded disposition. The initial method supported 73 identities; an exact-phase sensitivity check revoked one, leaving **{states[False]['conditionally_supported_identity']} with conditional identity support**, {states[False]['ambiguous_identity']} ambiguous, 8 changing identity across partitions, 9 failing prediction adequacy, and 133 lacking enough independent partitions. None of the new predictive-only inclusion proposals qualifies for deployment.

The main new finding is a mismatch between prediction and full-fit residual checks for satellites with **zero active curved calibration observations**. Their phase uncertainty can explain held target points, while the original raw residual gate still evaluates the prior phase mean. On DS24-0077, exposing the target-supported phase and causal orbital posterior reduces the 39-point RX2 CH5 residual from **407 Hz to 25 Hz**. The candidate is 58053. The recovered target passes both c variants, but the whole-scan proposal remains rejected because a retained RX1 CH3 track fails in fitted-c.

![Annotation coverage](figures/annotation_coverage.png)

## Scope and interpretation

This extends the [previous 52-track report](../2026_10_29_systematic_track_annotation/README.md) and [inventory](../2026_10_29_all_large_track_inventory/README.md). Large means at least 20 unassociated points spanning at least 20 seconds in either c variant. The inventory is the union of both c variants, deduplicated by recording and track identity; it is not a count of all untracked RF curves. Nine DS24 inputs lack exports; one further scan has no qualifying large track. The previous inventory documents those exclusions. DS24 contributes 289 distinct large tracks in the c-arm union, versus 288 in the previous fitted-c table, across 93 qualified slots. Automatic-analysis and session-research recordings cover the wider scope.

[The complete ledger](annotation_ledger.csv) preserves every track, including unresolved rows. Annotation is a hypothesis test conditional on the frozen graph, incumbent identities, finite candidate search and nuisance model. A preferred candidate is not ground truth. Associated-point counts below are proposed memberships before whole-proposal acceptance; failed proposals add zero points to the deployed result. Added/lost counts include all postfit membership changes, so they need not equal the target track's point count.

{table(counts,['status','predictive_only','curved_model'])}

## Reconstructing the predictive-only annotation

1. Load the frozen graph and incumbent curved calibration mask. The target remains outside the receiver calibration normal equations.
2. Randomize scan-wide 12-second groups with seeds 20261029, 94721 and 4081, excluding a 2-second guard around held groups from training. The same time groups apply across receivers and channels. Require three usable partitions, at least eight target training points and four held points. The 133 insufficient cases are unresolved, not rejected identities.
3. Fit the curved training data from the regional center in a 25 × 25 km box, for both c=0 and fitted-c, using five phase refresh rounds and 48 position steps per round. Training fits use unit weights and a fixed 150 Hz annotation noise scale; held target points never affect those fits.
4. Nominate three distinct satellites from the full causal catalogue using target training points, both c variants and regional position probes. Freeze the alias from training under c=0 for both variants.
5. For a satellite already in model labels, propagate its shared coefficient covariance. For an absent family, integrate a causal phase prior on ±15 seconds at 0.1-second spacing and three physical orbital uncertainty modes. Propagate receiver uncertainty, a 300 Hz target bias prior and twice the fixed noise variance. Existing labels can include families with zero active observations: this is explicitly audited below.
6. Condition each target predictive distribution on its training subset, then evaluate the normalized Gaussian-mixture density on its held subset. Mixture weights and moments use training values only. Require the same winning identity across all three partitions and both c variants, a score margin of at least 10 over the runner-up, held RMS no greater than 450 Hz, visibility and phase-fit convergence. Scores are conditional predictive differences, not calibrated probabilities.

The curved annotation engine uses a joint held-data score; the predictive-only engine uses a conditional target score. Their numerical margins are not interchangeable. Tests establish the Gaussian conditioning formula, no effect of altered held values on predictions, exact receiver-design parity and unchanged receiver coordinates when only satellite parameters are exposed. Two new-family grid checks (DS24-0087 and V08) at 0.05 seconds retained identity decisions; maximum score changes were 8.54e-6 and 3.44e-5.

### Exact-phase sensitivity checks

For three families with no active curved evidence, an opt-in replay uses explicit causal phase integration and the physical orbital prior even when the family already appears in the label vector. Candidate nomination, random groups, c variants and search budgets stay matched. DS24-0077 and DS24-0095 retain their candidates. V06 RX2 CH1 T004 switches its preferred candidate from 64472 to 67307, but the minimum margin is only 1.624 against the required 10. Its status is therefore **ambiguous**, superseding the original conditional support. The ledger retains both the original and revised decisions. The other 271 predictive-only tracks have not received this sensitivity replay; their identities remain conditional on the original uncertainty model.

{table(exact_rows,['scan','component','original_norad','revised_norad','revised_status','minimum_margin'])}

![Identity sensitivity to phase integration](figures/exact_phase_sensitivity.png)

## Why annotation support did not automatically recover the tracks

The full inclusion trials restore the original scan noise, weights and priors, include every target point, preserve the old calibration mask, start at the regional center and use matched five × 48 search budgets. They preserve original residual checks and require no loss of old memberships in either c variant. Target data may affect position through their predictive likelihood but cannot alter receiver coefficient means at a fixed position. Initial trials with the original raw gate all failed. Position error sometimes improved and sometimes worsened; neither outcome determines acceptance.

Three investigated families were present in the label vector without active curved observations: DS24-0077/58053, DS24-0095/62530 and V06/64472. Their original raw target predictions showed large offsets. By contrast, V06/63594 already had 41 active curved points; its additional CH3 target failed residual structure despite only about 64 Hz RMS. Large residual offsets and small structured residuals therefore need different investigations.

The phase-refresh prototype exposes only the posterior phase of a family with no active curved support, then relinearizes the same causal orbit model. It keeps the receiver mean and curved likelihood unchanged at fixed position. The follow-up for DS24-0077 also exposes the existing three causal orbital-error coordinates under their original priors. This is target-informed satellite estimation; it is not receiver calibration. Earlier experiment receipts used the broader phrase `target_calibrates=False`; its precise meaning is no target-driven receiver or curved calibration update.

![DS24-0077 phase mismatch](figures/phase_model_root_cause.png)

{table(root_rows,['model','bias_hz','RMS_hz','slope_sigma','step_sigma','acf'])}

In the final DS24-0077 model the orphan phase is −2.108 seconds in fitted-c; orbital prior coordinates are approximately [0.952, −0.043, −0.021]. Exact nominal-phase replay differs from the final linearized phase model by less than 1e-6 Hz. Receiver coordinate change at fixed position is zero. This check does not validate nonlinear orbital-mode errors or establish that 58053 is the true transmitter.

The target passes with 24.83 Hz RMS, slope 1.05σ and lag-one correlation 0.144. The retained RX1 CH3 T004 → 58682 instead has a 3.005σ slope against the 3σ limit, 72.09 Hz RMS and correlation 0.395. The proposal is rejected despite that narrow failure. A near-threshold failure merits an uncertainty and repeated-testing audit, not a case-specific threshold relaxation.

## Matched position results

![Matched position errors](figures/matched_position_errors.png)

All target trials below are rejected by the paired acceptance policy. The V06 CH1 inclusion trials are historical tests of 64472; the subsequent exact-phase replay made that identity ambiguous, an additional reason not to include it. The evaluation site is 37.849061591561885, −122.48574968092912, used only after inference. All candidate selection, fitting and decisions use causal TLEs and scan evidence. A lower in-sample frequency objective is not evidence of lower localization error; [the numerical table](inclusion_trials.csv) records both separately. `curved_RMS_hz` in that file describes the retained curved data, not target RMS. Different models can have different marginal normalizations, so their objectives are not a standalone promotion criterion.

{table(fit_table,['scan','model','variant','arm','control_error_km','error_km','added','lost','qualified'])}

## What is established and what remains

* The missing phase update is a demonstrated mechanism for a large apparent discrepancy, and causal orbital uncertainty explains much of the remaining DS24-0077 target residual. It does not yet qualify a whole-scan recovery.
* Strong identity evidence does not guarantee useful positional information. Satellite, receiver and position uncertainty can absorb the same frequency changes. Uncertain tracks should contribute predictive likelihood with shared uncertainty, rather than act as new receiver calibration anchors.
* The 133 short-span cases need a separate reproducible group-support design or independently supported same-family evidence. They must not be forced through three near-duplicate partitions.
* New families absent from the existing label vector have an annotation implementation but not yet a full position-inclusion implementation. The inclusion tool rejects that unsupported path explicitly.
* The graph and incumbent identities were chosen before random partitioning. This validation is conditional on those choices, not a fully held-out end-to-end pipeline. Position and learned-noise uncertainty are not fully integrated. Candidate coverage, false-identity controls, wrong-join controls, orbital nonlinearities and prior calibration remain limitations.
* Continue the remaining curved-track queue, record every outcome, test the strongest new-family candidates with exact causal phase likelihood, and require broad paired-c localization validation before any new ALGO version. No production algorithm was changed by this iteration.

## Reproducibility and artifacts

Entry points: `tools/annotate_predictive_only.py`, `tools/run_annotation_inventory.py`, `tools/include_predictive_annotations.py`, `tools/predictive_orphan_phase.py`, `tools/diagnose_predictive_inclusion.py`, and `tools/report_predictive_track_annotation.py`. The queue records attempt claims and terminal receipts; existing, unfinished or running claims are not silently restarted. Workers are bounded to eight with a 600-second limit per annotation; there is no new RF collection.

Run the report with `PYTHONPATH=src:tools .venv/bin/python tools/report_predictive_track_annotation.py --study /srv/bulk/leo/research/ch78-qualified-cohort-20261029 --output NEW_DIRECTORY`. Corpus reads may require the `leo` account. Run annotation with `tools/run_annotation_inventory.py run --output STUDY/systematic-annotation-v1 --limit N`; add `--predictive-only` for the outside-calibration queue. Use `include_predictive_annotations.py --inventory INVENTORY --validation VALIDATION_DIR --output NEW_DIRECTORY`, optionally adding `--orphan-phase-refresh --orphan-orbit-prior` for the final prototype.

* [All diagnostic figures](GALLERY.md)
* [All 1,630 track dispositions](annotation_ledger.csv)
* [Every matched inclusion trial](inclusion_trials.csv)
* [Structured snapshot](results.json)
* [Compressed numerical evidence](evidence.json.gz), including random split assignments and model receipts; repeated observation-ID lists and optimizer histories are represented by counts and hashes.
* [Source file SHA-256 receipts](source_sha256.json)

The targeted component and integration suite passes 31 tests, including the residual diagnostic and track recovery components. No golden fixtures were changed. The inventory and full recovery objective remain incomplete. The next 64 curved-track jobs were launched as a bounded batch; the ledger is a snapshot, not a claim that pending work has finished.
'''
    (out/'README.md').write_text(text)
    print(json.dumps(dict(assessed=assessed,pending=pending,states={str(k):dict(v) for k,v in states.items()},trial_rows=len(fits))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
