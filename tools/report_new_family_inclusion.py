"""Report exact new-family likelihood, phase audits and complete track ledger."""
import argparse
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
from leo.analysis.research.grouped_prediction import identity_consensus
from report_inventory_experiments import error
from report_systematic_annotation import compact_evidence
from report_predictive_track_annotation import table


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);figures=out/'figures';figures.mkdir();sources={};evidence={}
    def load(p):
        p=Path(p);sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();return read(p)
    rechecks={};audit=[];q=s/'systematic-annotation-v1';protocol=load(q/'protocol.json')
    paths=sorted(s.glob('exact-uncalibrated-annotation-*-v1/result.json'))+sorted((s/'exact-uncalibrated-cohort-v1').glob('*/result.json'))
    paths+=sorted((s/'new-family-cohort-v1').glob('*/*/result.json'))
    for p in paths:
        r=load(p)
        if 'track_id' not in r:continue
        a=identity_consensus(r['folds'],score_name='conditional_target');old=load(q/r['track_id']/'result.json')['annotation']
        rechecks[r['track_id']]=(r,a,str(p));evidence[str(p)]=r
        audit.append(dict(track_id=r['track_id'],scan=r['job']['label'],component=r['component'],original=old['norad'],revised=a['norad'],
                          original_status=old['status'],status=a['status'],margin=a.get('minimum_margin'),source=str(p)))
    folders=sorted(s.glob('new-family-inclusion-*-v1'))+[p.parent for p in sorted((s/'new-family-cohort-v1').glob('*/inclusion/new_family.json'))]
    fits=[];trials={};included={};gallery=[]
    for folder in folders:
        if not (folder/'new_family.json').exists():continue
        pr=load(folder/'protocol.json');control=load(folder/'control.json');trial=load(folder/'new_family.json')
        inv=load(s/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');tag=folder.parent.name if folder.name=='inclusion' else folder.name
        trials[tag]=dict(protocol=pr,control=control,trial=trial)
        for arm,v in trial['arms'].items():
            c=control['arms'][arm];n=next(r['total_GLRT'] for r in inv['summary'] if r['arm']==arm)
            fits.append(dict(scan=pr['job']['label'],norad=pr['targets'][0]['norad'],arm=arm,qualified=trial['paired_valid'],control_qualified=control['paired_valid'],
                original_error_km=error(inv['policy'][arm]),control_error_km=error(c),target_error_km=error(v),
                added=v['added_points'],lost=v['lost_points'],control_association_percent=100*len(c['proposed_associated_ids'])/n,
                target_association_percent=100*len(v['proposed_associated_ids'])/n,
                incumbent_objective_control=c['negative_twice_elbo'],incumbent_objective_target=v['incumbent_objective'],
                target_predictive_objective=v['family']['negative_twice_log_density'],
                target_RMS_hz=max(r['profile_RMS_hz'] for r in v['family']['diagnostics']),phase_s=v['family']['phase_map_s'],
                phase_sigma_s=v['family']['phase_sigma_s'],orbital_prior_norm=float(np.linalg.norm(v['family']['orbital_posterior_mean'])),source=str(folder)))
        for entry in pr['targets']:
            included[pr['job']['job_id'],entry['component']]=dict(research_inclusion='passes_paired_checks' if trial['paired_valid'] else 'rejected',inclusion_source=str(folder))
        rr=trial['arms']['fitted_c']['family']['diagnostics'];fig,axs=plt.subplots(3,len(rr),figsize=(7*len(rr),9),squeeze=False,layout='constrained')
        for col,r in enumerate(rr):
            t=np.array(r['times_s']);raw=np.array(r['raw_residual_hz']);residual=raw-r['profile_bias_hz']
            axs[0,col].scatter(t,np.array(r['CFO_hz'])/1000,s=18,label='GLRT');axs[0,col].plot(t,np.array(r['prediction_CFO_hz'])/1000,c='#cc3311',label='Causal orbit + original receiver + orbit posterior')
            axs[0,col].set(title=r['component'].split('-RF')[0],ylabel='CFO (kHz)');axs[0,col].legend(fontsize=7)
            axs[1,col].scatter(t,residual,s=18);axs[1,col].axhline(0,c='black',lw=.7)
            axs[1,col].set(ylabel='Residual after bias profiling (Hz)',title=f"RMS {r['profile_RMS_hz']:.1f} Hz; lag-one correlation {r['noise']['lag1_acf']:.3f}")
            axs[2,col].scatter(residual[:-1],residual[1:],c=np.diff(t),cmap='viridis',s=20)
            axs[2,col].set(xlabel='Residual at point i (Hz)',ylabel='Residual at point i+1 (Hz)',title='Lagged residuals; darker pairs are closer in time')
            for ax in axs[:2,col]:ax.set_xlabel('Scan time (s)')
        for ax in axs.flat:ax.grid(alpha=.2)
        fig.suptitle(f"{pr['job']['label']} → {pr['targets'][0]['norad']} | paired checks: {trial['paired_valid']} | research only")
        name=tag+'.png';fig.savefig(figures/name,dpi=140);plt.close(fig);gallery.append(f"### {pr['job']['label']} → {pr['targets'][0]['norad']}\n\n![Track and residuals](figures/{name})\n")
    previous=Path(__file__).resolve().parents[1]/'reports/2026_10_29_predictive_track_annotation/annotation_ledger.csv'
    published={r['track_id'] for r in csv.DictReader(previous.open()) if r['source']}
    sources[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest();ledger=[]
    for row in protocol['rows']:
        r=dict(row);folder=Path(row['known_validation']) if row['known_validation'] else q/row['track_id'];p=folder/'result.json'
        if p.exists():
            result=load(p);annotation=identity_consensus(result['folds'],score_name=result.get('identity_score_name','joint'));source=str(p)
            if row['track_id'] not in published:evidence[str(p)]=result
            if row['track_id'] in rechecks:result,annotation,source=rechecks[row['track_id']]
            r.update(state=annotation['status'],norad=annotation['norad'],minimum_margin=annotation.get('minimum_margin'),annotation_source=source)
        else:
            receipts=sorted(q.glob('attempt-*/'+row['track_id']+'-terminal.json'))
            if receipts:r['state']='execution_'+load(receipts[-1])['status']
        r.update(included.get((row['job_id'],row['component']),dict(research_inclusion='not_tested_this_iteration')));ledger.append(r)
    def csvfile(name,rows,keys):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows({k:r.get(k) for k in keys} for r in rows)
    csvfile('annotation_ledger.csv',ledger,['track_id','job_id','label','component','points','span_s','state','norad','minimum_margin','annotation_source','research_inclusion','inclusion_source'])
    csvfile('phase_audit.csv',audit,list(audit[0]));csvfile('position_trials.csv',fits,list(fits[0]))
    # Each family gets a matched comparison; never mix new-family likelihood
    # normalizing constants into an old-observation score improvement claim.
    groups=list(dict.fromkeys((r['scan'],r['norad']) for r in fits));fig,axs=plt.subplots(2,1,figsize=(max(10,len(groups)*1.15),8),layout='constrained')
    for arm,color,offset in [('c0','#4477aa',-.12),('fitted_c','#ee6677',.12)]:
        rr=[next(r for r in fits if (r['scan'],r['norad'])==g and r['arm']==arm) for g in groups]
        x=np.arange(len(rr))+offset
        axs[0].scatter(x,[r['control_error_km'] for r in rr],marker='o',facecolors='none',edgecolors=color,label=arm+' control')
        axs[0].scatter(x,[r['target_error_km'] for r in rr],marker='x',color=color,label=arm+' plus family')
        for xx,r in zip(x,rr,strict=True):axs[0].plot([xx,xx],[r['control_error_km'],r['target_error_km']],c=color,alpha=.5)
        axs[1].bar(x,[r['added'] for r in rr],.22,color=color,label=arm)
    for ax in axs:
        ax.set_xticks(range(len(groups)),[f'{a}\n{b}' for a,b in groups]);ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    axs[0].set_ylabel('Evaluation position error (km)');axs[1].set_ylabel('Proposed added points, before acceptance')
    fig.suptitle('Exact new-family inclusion: all passing and failing trials shown')
    fig.savefig(figures/'matched_results.png',dpi=145);plt.close(fig)
    replay={}
    for p in sorted(s.glob('new-family-phase-replay-*-v1/result.json')):replay[p.parent.name]=load(p)
    phase_rows=[]
    for name,r in replay.items():
        for arm,v in r['arms'].items():
            for mode,d in v.items():
                for track in d['diagnostics']:phase_rows.append(dict(scan=r['job']['label'],arm=arm,mode=mode,phase_s=d['phase_map_s'],
                    RMS_hz=track['profile_RMS_hz'],ACF=track['noise']['lag1_acf'],noise_pass=track['noise']['noise_screen_pass']))
    influence=load(s/'new-family-influence-ds24-0047-v2/result.json');influence_rows=[]
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,(arm,r) in zip(axs,influence['arms'].items(),strict=True):
        b,e=r['control'],r['with_target'];distance=r['position_shift_km']
        x=[z['fraction']*distance for z in r['line']]
        for key,label,color in [('incumbent_objective','Existing data','#4477aa'),('target_objective','New family, causal phase prior','#ee6677'),
                               ('joint_objective','Joint objective','#228833'),('uniform_phase_target_objective','New family, uniform phase diagnostic','#aa3377')]:
            ax.plot(x,[z[key]-b[key] for z in r['line']],label=label,c=color)
        ax.axvline(distance,c='black',ls='--',lw=.7,label='Saved target-fit endpoint');ax.axhline(0,c='gray',lw=.6)
        ax.set(title=arm,xlabel='Distance along control → target-fit direction (km)',ylabel='Objective change from matched control location');ax.grid(alpha=.2);ax.legend(fontsize=7)
        influence_rows.append(dict(arm=arm,shift_km=distance,weak_axis_overlap=r['direction_overlap_with_weak_axis'],
            weak_axis_local_scale_km=r['local_Gaussian_sigma_axes_km'][0],incumbent_cost_change=e['incumbent_objective']-b['incumbent_objective'],
            target_cost_change=e['target_objective']-b['target_objective'],uniform_phase_target_change=e['uniform_phase_target_objective']-b['uniform_phase_target_objective']))
    fig.suptitle('DS24-0047: a modest new-family preference moves a weak position direction')
    fig.savefig(figures/'ds24_0047_influence.png',dpi=145);plt.close(fig)
    counts=Counter(r['state'] for r in ledger);assessed=sum(bool(r.get('annotation_source')) for r in ledger)
    write(out/'results.json',dict(states=counts,assessed=assessed,ledger=ledger,phase_audit=audit,position_trials=fits,phase_gate_replays=phase_rows,
                                 influence=influence,execution_receipts=[load(p) for p in sorted(q.glob('attempt-*/*-terminal.json'))],no_production_change=True,goal_complete=False))
    write(out/'source_sha256.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(dict(annotation_evidence=evidence,trials=trials,phase_replays=replay,influence=influence)),f,separators=(',',':'))
    (out/'GALLERY.md').write_text('# New-family track diagnostics\n\nAll figures show fitted-c. The numerical artifacts retain both c variants. These are research proposals; no production memberships were changed.\n\n'+'\n'.join(gallery))
    completed=len(list((s/'new-family-cohort-v1').glob('*-terminal.json')));selected=len(load(s/'new-family-cohort-v1/protocol.json')['jobs'])
    pilot=[r for r in fits if r['scan'] in ('V08','DS24-0087')]
    text=f'''# Exact predictive inclusion of previously absent satellite families

The new likelihood can use a track whose satellite is absent from the calibration model. It integrates causal phase and orbital uncertainty and preserves the correlation with existing predictive tracks. **V08 RX2 CH6 → candidate 58385 adds 43 points, loses none, and passes all paired c checks.** This is a research recovery, not a new ALGO promotion: localization error increases slightly, from 163 to 190 m in c0 and 194 to 199 m in fitted-c. The target was previously unreachable by the inclusion tool despite strong randomized prediction evidence.

DS24-0087 RX2 CH1 → 57710 remains rejected. Its fit has only about 27 Hz RMS, but residual correlation persists. Fitted-c error improves from 1.625 to 1.267 km in the matched experiment, which does not override the failed residual gate or the control optimizer's unsuccessful termination.

The inventory snapshot now contains **{assessed} assessed tracks out of 1,630**, with {1630-assessed} still lacking a completed annotation. The full [ledger](annotation_ledger.csv) includes unresolved identities and research inclusion status. The previous 64-track curved batch finished with 63 completed assessments and one 600-second timeout (V05, track f4160fbfe073535e44c2); that timeout remains explicit and has not been silently restarted. A further 64-track batch has started. These batches are independent of the exact-phase audit and the new-family position trials. This report follows the [predictive annotation report](../2026_10_29_predictive_track_annotation/README.md).

## Pilot results

{table(pilot,['scan','norad','arm','control_error_km','target_error_km','added','lost','control_association_percent','target_association_percent','qualified'])}

Percentages and added/lost counts describe proposed whole-scan memberships, including postfit extensions. Rejected trials do not change production associations. The V08 gain is 3,687 → 3,730 of 5,476 GLRT points, **67.33% → 68.12%**. The original deployment and the matched scalar-objective controls agree within 0.4 m on these pilots; this does not erase the optimizer termination warning on DS24-0087 fitted-c.

![Matched position and association results](figures/matched_results.png)

## Mathematical model and implementation

Let a and C be the coefficient mean and covariance from the curved-data calibration at a proposed position x. Existing predictive observations use design Hₒ and noise Nₒ, including one 300 Hz bias prior per track. Their predictive likelihood remains in the old objective. To add a new satellite family, first form conditional predictive moments:

    Cₒ = C − C Hₒᵀ (Nₒ + Hₒ C Hₒᵀ)⁻¹ Hₒ C
    aₒ = a + C Hₒᵀ (Nₒ + Hₒ C Hₒᵀ)⁻¹ (yₒ − μₒ)

These are temporary predictive moments. The receiver calibration coefficients exposed by the scan model remain a. No target observations enter the curved calibration normal equations.

For each satellite phase φ in the causal ±15-second grid, the new family has mean Hₙ aₒ + f(x, φ) and covariance Nₙ + Hₙ Cₒ Hₙᵀ + U(x, φ)U(x, φ)ᵀ. U contains the same three physical orbital-error modes derived from causal TLE history. All tracks from that family share one phase and three modes; track bias priors remain separate. The position objective adds the log-sum-exp of the normalized Gaussian likelihoods weighted by the causal phase prior. This is a likelihood contribution conditioned on existing predictive observations, so their shared receiver uncertainty is not counted twice.

The implementation evaluates the phase grid in batches and uses a small orbital-coordinate solve per phase. Invisible phases contribute zero likelihood; their prior mass is not renormalized away. The phase prior is normalized inside the declared ±15-second box, with its untruncated prior mass recorded. Original scan noise is used, with the existing unseen-noise variance multiplier of two. There is no new free receiver offset, drift, channel correction or target-specific orbital scale.

Five phase-refresh rounds fit the existing curved model. In each round, both the matched control and target experiment minimize the normalized objective with L-BFGS-B, at most 48 iterations and 240 function evaluations. The regional box is 25 × 25 km centered at **37.906, −122.545**, and every fit starts at its center. The new family's phase is integrated explicitly, not held at a reference value. Both c=0 and fitted-c use identical target observations, aliases, candidate identity, causal priors and search budgets. GPS is used only afterward to report error at 37.849061591561885, −122.48574968092912.

At the endpoint, residual checks use the original receiver mean plus the new family's phase and orbital posterior. They do not use a target-adjusted receiver solution. Qualification requires existing and new tracks to pass the original gates, no lost incumbent memberships, both c variants, phase convergence, successful final optimizer termination, and less than 1% posterior mass within 0.1 seconds of the phase boundary. These remain research checks conditional on the annotation and nuisance model; they are not a calibrated probability of correct association.

## Uncalibrated-family identity audit

All 28 initially supported shared-family identities were rechecked with explicit phase integration whenever a family had no active curved evidence; two new-family pilots were also rechecked. **Only V06 RX2 CH1 changed disposition:** 64472 no longer has conditional support; 67307 is preferred but its margin is too small, so the result remains ambiguous. The other 29 of those 30 cases preserve support. Additional cases in the bounded new-family cohort use this same validation before inclusion. [Every audit result](phase_audit.csv) includes the original and revised identity, margin and source.

This is sensitivity validation against one corrected uncertainty representation, not independent satellite ground truth. Other possible transmitters outside the finite shortlist and an incorrect incumbent model remain risks. The finite phase grid agrees with the earlier finer-grid checks for the two pilots.

## Why the DS24-0087 rejection survives phase refinement

The 0.1-second grid accurately integrates the pilot phase likelihood, but rounding the diagnostic phase mode could still affect residual shape. A continuous, prior-penalized refinement was therefore run at each saved endpoint, leaving position and integrated likelihood unchanged. DS24-0087's correlation rises slightly to about 0.65 rather than disappearing. V08 stays compatible, with roughly 17 Hz RMS after refinement. Thus the DS24-0087 residual pattern is not removed by this discretization correction.

{table(phase_rows,['scan','arm','mode','phase_s','RMS_hz','ACF','noise_pass'])}

The next diagnostic should distinguish within-dwell correlated CFO error from an across-dwell satellite/receiver discrepancy using raw observation timing and independently estimated noise. We have not widened covariance or loosened a gate to make this particular track pass. The DS24-0087 fitted-c control reports an abnormal line-search termination; the final location is within 0.4 m of the previous method, but this remains a limitation on the controlled comparison.

## Broader cohort and all numerical results

Eight further family groups were frozen by DS24/session scope and descending point count, without consulting position error. Each receives a fresh randomized identity check with explicit uncalibrated phase integration before any position trial. At snapshot time, **{completed} of {selected} cohort jobs are terminal**. All completed position comparisons, including failures, appear below. The [CSV](position_trials.csv) separately records the incumbent-observation objective and new-family predictive objective; scores with different observation sets must not be interpreted as fit improvements by subtraction.

{table(fits,['scan','norad','arm','control_error_km','target_error_km','added','lost','target_RMS_hz','qualified','control_qualified'])}

Three of the ten position proposals pass their target-fit paired checks: V08/58385, DS24-0095/59746 and DS24-0047/66861. The DS24-0095 matched control has an optimizer termination warning. All three worsen evaluation error in both c variants, despite adding points and preserving incumbents. Some rejected proposals improve error. This is direct evidence against promoting this method based on association coverage or residual compatibility alone. Optimizer warnings remain rejections in the recorded experiments; they have not been reclassified as successful convergence because their positions look reasonable.

## DS24-0047: weak information, not evidence of a trapped optimizer

The accepted research proposal for 66861 moves fitted-c position by 1.364 km and increases evaluation error from 1.331 to 2.420 km. To diagnose the pull, both objective terms were replayed along the line from the matched control to the target-fit endpoint, refreshing the existing satellite phases at each fixed position. This diagnostic uses no GPS and performs no position optimization. Finite differences of the incumbent objective use 25 m steps.

![Position influence decomposition](figures/ds24_0047_influence.png)

{table(influence_rows,['arm','shift_km','weak_axis_overlap','weak_axis_local_scale_km','incumbent_cost_change','target_cost_change','uniform_phase_target_change'])}

In fitted-c, the shift aligns with the old fit's weakest direction with cosine 0.971. Along this direction, a 1.364 km shift costs the old data only 0.882 objective units; the target gains 1.875. The local Gaussian curvature scale is about 1.49 km on the weak axis. This is conditional objective curvature under the current nuisance model, **not calibrated position confidence**.

The target's continuous-phase residual RMS improves only from about 156.5 to 148.0 Hz along that move. Its causal phase changes from −1.085 to −0.958 seconds; the prior mean is −0.069 seconds with scale 0.567 seconds and three Student degrees of freedom. A uniform-phase diagnostic on the same ±15-second interval still favors the displaced endpoint by 1.360 objective units. The causal phase prior strengthens the pull by about 0.515 units, but does not create it by itself. The uniform prior was not used for acceptance or the position fits.

These measurements do not establish that 66861 is the true satellite, nor that the incumbent position is intrinsically correct. They establish that a weakly constrained old solution can move substantially in response to a modest new-track likelihood preference. The next general safeguard should evaluate predictive consistency across independent satellite families and calibrated positional influence, rather than equating more associated points with better localization or rejecting every statistically plausible position move. Recovering independent directional information remains necessary for the 500 m objective.

## Tests, artifacts and remaining work

The focused suite passes **35 tests**. New tests compare low-rank phase integration against dense Gaussian calculations, verify exact sequential-vs-joint likelihood equality for correlated old/new evidence, check visibility-mass penalties, and compare a two-track shared-family batched calculation with scalar phase/orbit calculations. Calibration inputs remain unchanged. Real-data replay verifies saved pilot likelihoods before continuous-phase diagnostics.

* [All track and residual figures](GALLERY.md)
* [Complete 1,630-track ledger](annotation_ledger.csv)
* [Phase sensitivity audit](phase_audit.csv)
* [Matched position and association trials](position_trials.csv)
* [Structured results](results.json), [compressed numerical evidence](evidence.json.gz), and [source SHA-256 receipts](source_sha256.json)

Implementation: `src/leo/analysis/research/predictive_track.py`, `tools/predictive_new_family.py`, `tools/include_new_predictive_family.py`, `tools/replay_new_family_phase.py`, `tools/recheck_predictive_phase.py`, `tools/batch_new_family_inclusion.py`, and this report generator. Run tools with `PYTHONPATH=src:tools`; corpus access may require the leo account. Phase audit outputs are under `exact-uncalibrated-cohort-v1`, new-family pilots under `new-family-inclusion-*-v1`, and the bounded cohort under `new-family-cohort-v1` in the existing study directory.

The full recovery objective is still open. Many curved tracks remain unassessed; 133 predictive-only tracks still lack enough independent random partitions; ambiguous identities must remain ambiguous. This implementation integrates one new family at a time, with shared uncertainty across its tracks. Simultaneous integration of several new families requires retaining their common receiver covariance, not summing independent per-family likelihoods. Broad position benefit, false-identity controls and orbital nonlinear-model checks remain necessary before a production promotion.
'''
    (out/'README.md').write_text(text)
    print(json.dumps(dict(assessed=assessed,states=counts,completed_cohort=completed,position_pairs=len(fits)//2,passing_pairs=sum(r['qualified'] for r in fits)//2)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
