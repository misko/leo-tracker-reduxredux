"""Figures and evaluation-only reporting for the sealed priority-track trials."""

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from debug_fast_graph_unassociated import read,write
from report_graph_covariance_qualification import error_km

CASES=('DS24-0018','DS24-0089')
ARMS=('c0','fitted_c')


def run(args):
    root=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False)
    diagnostics={c:read(root/c/'diagnostic.json') for c in CASES}
    recoveries={c:read(root/(c+'-recovery')/'recovery.json') for c in CASES}
    origins={c:read(root/(c+'-origin-v2')/'origin.json') for c in CASES}
    qualified=read(root/'DS24-0089-bias-constrained/constrained.json')
    assert qualified['accepted'] and qualified['preserves_original_points']
    rows=[]
    for c in CASES:
        variants={'baseline':recoveries[c]['baseline'],
            'whole_curve_300Hz':recoveries[c]['trials']['nominal']['arms']}
        statuses={'baseline':'existing policy','whole_curve_300Hz':'rejected'}
        if c=='DS24-0089':
            prior=read(root/(c+'-priors')/'prior_ablation.json')
            for name,v in prior['trials'].items():variants[name]=v['arms'];statuses[name]='rejected'
            variants['constrained_300Hz']=read(root/(c+'-constrained')/'constrained.json')['arms'];statuses['constrained_300Hz']='rejected'
            variants['new_bias1000Hz']=read(root/(c+'-bias')/'bias_ablation.json')['arms'];statuses['new_bias1000Hz']='rejected'
            variants['bias1000Hz_constrained']=qualified['arms'];statuses['bias1000Hz_constrained']='qualified prototype'
        for name,pair in variants.items():
            for arm,r in pair.items():
                row=dict(case=c,method=name,arm=arm,status=statuses[name],
                    position_error_km=error_km(r['endpoint_latlon']),RMS_hz=r['RMS_hz'],
                    negative_twice_elbo=r['negative_twice_elbo'],proposed_associated_points=r['proposed_associated_points'],
                    failed_tracks=[g['component'] for g in r['gates']['tracks']+r['linear_gates'] if not g['compatible']])
                if 'target_prediction' in r:row['target_RMS_hz']=r['target_prediction']['rms_hz']
                rows.append(row)
    write(out/'evaluation.json',rows)
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (out/'evaluation.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
    plt.rcParams.update({'font.size':10,'axes.grid':True,'grid.alpha':.2})
    fig,axes=plt.subplots(2,2,figsize=(14,9),layout='constrained')
    for k,c in enumerate(CASES):
        d=diagnostics[c];t=d['target'];times=np.array(t['times']);values=np.array(t['values'])
        obs=read(args.source/c/'observations.json');lookup={o['observation_id']:o for o in obs}
        native=np.array([lookup[o]['measured_cfo_hz'] for o in t['observation_ids']]);a=d['arms']['fitted_c']
        axes[k,0].scatter(times,native/1000,c='crimson',s=22,label='Unassociated GLRT target')
        for name,label,color in [('original','Original candidate, frozen phase','#888888'),('catalogue','Causal orbit, diagnostic phase','#0072b2')]:
            r=a[name];prediction=native-np.array(r['residual_hz'])
            axes[k,0].plot(times,prediction/1000,color=color,label=label)
            axes[k,1].plot(times,r['residual_hz'],'.-',color=color,label=f"{label}: {r['rms_hz']:.1f} Hz")
        z=recoveries[c]['trials']['nominal']['arms']['fitted_c']['target_prediction']
        axes[k,1].plot(times,z['residual_hz'],'.-',color='#e69f00',label=f"Joint reentry, 300 Hz prior: {z['rms_hz']:.1f} Hz")
        if c=='DS24-0089':
            z=qualified['arms']['fitted_c']['target_prediction'];axes[k,1].plot(times,z['residual_hz'],'.-',color='#009e73',label=f"Qualified prototype: {z['rms_hz']:.1f} Hz")
            axes[k,1].axvspan(130.8606529,times.max(),color='red',alpha=.08,label='Last 6 points: strongest split test')
        axes[k,0].set(title=f"{c}: NORAD {d['original_row']['candidate_norad']} · {len(times)} points",xlabel='Time (s)',ylabel='Native CFO (kHz)')
        axes[k,1].set(title='Residuals after permitted alias and constant profile',xlabel='Time (s)',ylabel='Residual (Hz)')
        axes[k,1].axhline(0,color='black',lw=.8)
        for ax in axes[k]:ax.legend(fontsize=8)
    fig.suptitle('Same original satellite candidates reappear in the causal catalogue search\nOrbit overlays include profiled constants; diagnostic phase search is not acceptance')
    fig.savefig(out/'orbits_and_residuals.png',dpi=150);plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(13,4.5),layout='constrained')
    for ax,c in zip(axes,CASES):
        t=diagnostics[c]['target'];key=t['key'];n=len(t['times'])
        names=['Mean','Slope','Quadratic','Step','Lag-one'];keys=['mean_z','slope_z','quadratic_bic_gain','maximum_step_z','lag1_acf'];limits=np.array([3,3,10,4,4/np.sqrt(n)])
        for k,arm in enumerate(ARMS):
            r=next(g for g in recoveries[c]['trials']['nominal']['arms'][arm]['gates']['tracks'] if g['component']==key)
            noise=r['conditional_residual_gate']['diagnostics'];values=np.array([noise[z] for z in keys]);values[-1]=abs(values[-1]);values=np.maximum(values,0)/limits
            ax.bar(np.arange(5)+(k-.5)*.35,values,.35,label=arm)
        ax.axhline(1,color='crimson',ls='--',label='Failure threshold');ax.set(xticks=np.arange(5),xticklabels=names,ylabel='Statistic / acceptance limit',title=c+' whole-curve reentry');ax.legend(fontsize=8)
    fig.suptitle('Unchanged conditional residual gates: low RMS alone is insufficient')
    fig.savefig(out/'failing_gates.png',dpi=160);plt.close(fig)

    fig,axes=plt.subplots(2,1,figsize=(12,8),layout='constrained')
    for ax,c in zip(axes,CASES):
        methods=list(dict.fromkeys(r['method'] for r in rows if r['case']==c))
        for k,arm in enumerate(ARMS):
            vals=[next(r for r in rows if (r['case'],r['method'],r['arm'])==(c,m,arm)) for m in methods]
            bars=ax.bar(np.arange(len(methods))+(k-.5)*.35,[r['position_error_km'] for r in vals],.35,label=arm)
            for bar,r in zip(bars,vals):
                if r['status']=='rejected':bar.set_alpha(.35);bar.set_hatch('//')
        ax.set(xticks=np.arange(len(methods)),xticklabels=[m.replace('_','\n') for m in methods],ylabel='Evaluation position error (km)',title=c);ax.legend()
    fig.suptitle('Position error is evaluated after inference\nHatched bars are rejected diagnostics; only the final 0089 prototype passes all checks')
    fig.savefig(out/'position_trials.png',dpi=160);plt.close(fig)

    # Detail at the scale where low-amplitude correlation is visible.
    d=diagnostics['DS24-0018'];t=d['target'];tt=np.array(t['times']);y=np.array(t['values']);piece=t['pieces'][0]
    polynomial=np.polynomial.legendre.legval((tt-piece['reference_time_s'])/piece['time_scale_s'],piece['coefficients_hz'])
    orbit=recoveries['DS24-0018']['trials']['nominal']['arms']['fitted_c']['target_prediction']['residual_hz']
    fig,ax=plt.subplots(figsize=(12,4),layout='constrained')
    ax.plot(tt,y-polynomial,'.-',label='Graph polynomial residual (already correlation-flagged)',alpha=.8)
    ax.plot(tt,orbit,'.-',label='Joint orbital residual',alpha=.8);ax.axhline(0,color='black',lw=.8)
    ax.set(title='DS24-0018: correlated tens-of-Hz residuals precede satellite recovery',xlabel='Time (s)',ylabel='Residual (Hz)');ax.legend()
    fig.savefig(out/'0018_correlation.png',dpi=160);plt.close(fig)

    tables=['| Scan | Method | Decision | c=0 error km | Fitted-c error km |','|---|---|---|---:|---:|']
    for c in CASES:
        for method in dict.fromkeys(r['method'] for r in rows if r['case']==c):
            pair=[r for r in rows if r['case']==c and r['method']==method]
            tables.append(f"| {c} | {method} | {pair[0]['status']} | {pair[0]['position_error_km']:.3f} | {pair[1]['position_error_km']:.3f} |")
    receipts={str(p.relative_to(root)):read(p) for p in root.rglob('*.json') if args.output not in p.parents}
    # Full raw records retained locally; compact archival membership lists as
    # count + digest, retaining all numeric diagnostics and fit histories.
    def compact(v):
        if isinstance(v,dict):return {k:compact(z) for k,z in v.items()}
        if isinstance(v,list):
            if v and all(isinstance(z,str) and z.startswith('sha256:') for z in v):
                return dict(observation_ids_count=len(v),ordered_ids_sha256=hashlib.sha256(json.dumps(v).encode()).hexdigest())
            return [compact(z) for z in v]
        return v
    with (out/'diagnostic_receipts.json.gz').open('xb') as f:
        with gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as g:g.write(json.dumps(compact(receipts),separators=(',',':')).encode())
    write(out/'provenance.json',dict(raw_record_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.json') if args.output not in p.parents},
        tools_sha256={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ['investigate_cohort_priority_tracks.py','report_priority_track_investigation.py']},
        constrained_0018_status='180 s cap reached; c0 finished infeasible, no completed paired result',
        original_origin_attempts='Serialization schema mismatch after successful numerical replay; corrected and rerun under origin-v2',
        production_unchanged=True))
    text=f'''# Two large unassociated tracks: cause, recovery experiments and position effects

The causal catalogue supports the **same satellite candidates already nominated by the pipeline**: 56781 for DS24-0018 RX2 CH3 T000 and 66815 for DS24-0089 RX1 CH3 T001. This investigation found a family-reentry gap and different residual-model failures, rather than evidence requiring different satellite identities.

**One bounded prototype recovers all 63 points of the 0089 track**, preserves every previously associated point and passes all existing gates in both `c` arms. Fitted-`c` error changes **2.205 → 2.126 km**; association increases **3,703/4,759 (77.81%) → 3,766/4,759 (79.13%)**. The 89-point 0018 track remains unqualified. Production is unchanged; this is not a new ALGO release.

## Where the tracks were lost

Both complete tracks were initially accepted. Replaying ALGO02's first gate round reproduces exactly the archived rejected-component lists for both scans. During its changed prior/weight fit:

- 0018: fitted-`c` lag-one correlation moves from **0.3913** (initially passing) to **0.4480**, exceeding the **0.4240** limit.
- 0089: fitted-`c` maximum step statistic moves from **3.334** to **4.696**, exceeding the **4.0** limit.

Each target is its satellite's only curved component. Rejecting it removes all retained evidence for that family. Its phase then returns to the causal prior mean: −0.0491 s for 56781 and −0.6813 s for 66815. The frozen-calibration extension considers only families with accepted curved tracks, so it cannot rediscover either removed family. This explains why clear graph evidence remains stranded.

The previous support-backoff experiment specifically required nominal multi-owner orbital-correction support. Neither singleton has that support, so neither was offered by that recovery rule. The high-channel covariance experiment also does not target these CH3 tracks.

## Catalogue and shape checks

At the existing estimated position, search the causal catalogue over ±15 s phase on a 1 s coarse grid, retaining 12 candidate identities and refining ±1 s in 0.1 s steps. This is a bounded diagnostic search, not a proof of unique identity or a full position refit. No GPS or future TLE enters it.

| Track | Candidate | Frozen phase RMS, fitted c | Diagnostic phase | Diagnostic RMS | Diagnostic gate result |
|---|---:|---:|---:|---:|---|
| 0018 RX2 CH3 T000 | 56781 | 100.1 Hz | −0.3 s | 30.7 Hz | correlation fails |
| 0089 RX1 CH3 T001 | 66815 | 882.8 Hz | +0.9 s | 103.4 Hz | passes |

Both graphs have **one polynomial piece**, dense sampling, and substantial non-linear shape; the selected integer alias stays unchanged (0 and 1 respectively). There is no evidence here requiring a multi-piece join or alias repair. A single piece does not mathematically prove every point has one physical source.

![Causal orbit overlays and residuals](orbits_and_residuals.png)

## 0018: genuine low-amplitude correlation, not a missing visible curve

Restoring all 89 points and refitting with unchanged priors yields RMS **25.68 / 25.64 Hz**, phases **−0.2824 / −0.2806 s**, and lag-one correlation **0.4347 / 0.4325** (`c=0` / fitted `c`). Mean, slope, quadratic and step checks pass. The correlation excess is small but real under the frozen screen.

The graph polynomial itself has RMS 26.98 Hz and adjacent residual correlation **0.4543**, explicitly recorded as `structure_flagged` before orbital recovery. Thus the earlier visual description “clean” meant a clear low-RMS curve, not independent white residuals. This supports investigating measurement correlation or a shared small residual process; it does not prove a receiver-specific physical cause or exclude orbit/model contributions.

![Correlation already present in the graph residuals](0018_correlation.png)

A constrained position-only search with unchanged gates reached its **180 s cap**. Its completed `c=0` arm was still infeasible; there is no completed paired qualification. We did not relax the correlation threshold, drop points, or continue an unbounded search. The unconstrained diagnostic moves position slightly farther from evaluation truth, but that was not used as its rejection criterion.

## 0089: a curve-constant prior distorts the phase/shape compromise

Whole-curve reentry with the original 300 Hz curve-constant prior produces about 100 Hz RMS but fails the step check at **4.675 / 4.694**. In fitted `c`, the strongest split isolates the last six points beginning **130.861 s**; their mean differs from the earlier points by approximately **204 Hz**. The test compares two sample means; this alone is not evidence of a literal receiver jump or a bad join.

The causal phase prior has mean −0.6813 s and width 1.6941 s. Reflecting its mean or setting it to zero, while preserving widths, observations and search budgets, does not repair the target. The target likelihood power remains 0.2. This argues against blaming only the prior's sign.

Widening **only the new curve's constant-frequency prior from 300 to 1,000 Hz** makes the target pass in both arms; all existing curve priors remain unchanged. Its fitted constant is approximately 859 / 921 Hz in the final constrained result. The narrower constant prior encourages phase to compensate for part of that offset, changing the residual shape. This controlled ablation supports that mechanism, but 1,000 Hz is not yet independently calibrated as a general prior for new tracks.

The unconstrained wider-prior result still narrowly fails an existing CH1 track in fitted `c` (step 4.0085; lag-one correlation also narrowly fails). A small constrained refinement, using unchanged RF gates and no evaluation position, produces a complete paired result:

- All 63 target points retained; every previously associated point preserved.
- Target RMS **96.59 / 96.24 Hz**, step **3.910 / 3.882**, lag-one correlation **0.268 / 0.264**.
- All original curved and predictive gates pass; refreshed phase changes are below 1e-7 s.
- The fitted-`c` solution has a minimum normalized gate slack of only **1.04e-6**. This is a boundary solution, so robustness validation is needed before adoption.

![Gate failures before the wider-prior constrained prototype](failing_gates.png)

## Position effects and rejected controls

The evaluation site is used only by this reporter, after inference: 37.849061591561885, −122.48574968092912. Distances use the same 6371 km sphere as the cohort report. No experiment selects a prior, candidate or endpoint by position error. Both arms have matched observations, candidate identities, priors and search budgets for each method.

{chr(10).join(tables)}

![Position errors for all completed prototypes](position_trials.png)

The nominal and active orbital-support reentry controls are numerically identical here; neither singleton has the multi-owner orbital correction that support backoff removes. Unconstrained refits use five phase rounds ×48 steps, cold-started at the declared 25×25 km regional box center. Constrained refinements use five rounds ×40 steps from their corresponding RF-only endpoints. The 0089 original-prior constrained search remained infeasible. Rejected controls are included as diagnostics, never adopted because of a favorable position error.

`evaluation.csv` separately records frequency RMS, objective, proposed point count, position error and failed tracks. Proposed counts on rejected fits are not accepted associations. Objective changes across different observation sets or priors are not position-accuracy evidence.

## Recommendation

1. Add a bounded **removed-family reentry pass** after calibration stabilizes, so credible whole curved tracks can nominate dormant catalogue families again. Reapply priors, complexity penalties, visibility and all residual gates before adoption.
2. Test the wider new-curve constant prior and constrained retention together on the frozen cohort, with original-point preservation and both `c` arms. Do not promote from this selected scan; the current fitted-`c` solution lies very close to a gate boundary.
3. For 0018, estimate measurement correlation from independent curves/receivers and evaluate covariance-aware residual tests on whole-family holdouts. Do not simply raise the lag-one limit to accommodate this track.

The recovered 0089 track reduces fitted-`c` error by only about **79 m**, leaving **2.126 km**. This is a real coverage gain and a useful causal diagnosis, but it does not resolve the scan's remaining localization bias or meet the 500 m goal.

## Artifacts and reproduction

Run `tools/investigate_cohort_priority_tracks.py` against `/srv/bulk/leo/research/ds25-20261024` with `--case DS24-0018` or `DS24-0089` and a fresh `--output`. Default mode performs the catalogue diagnosis; `--recover`, `--origin`, `--prior-ablation`, and `--bias-ablation` select the recorded experiments. `--constrained --parent PRIOR_OUTPUT` refines recovery endpoints; add `--constant-sigma 1000` with a bias-ablation parent for the qualified 0089 prototype. Use `PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` and the project virtual environment. Jobs were bounded to 120–180 s.

The first origin-report attempts failed while reading an older JSON schema after numerical replay. They were corrected and rerun as `origin-v2`; both failed-component lists match the archive. This changed reporting only, not the fits.

`diagnostic_receipts.json.gz` retains numeric diagnostics and histories; repeated observation-ID lists are represented by counts and ordered-list hashes. Full records remain under `/srv/bulk/leo/research/ch78-qualified-cohort-20261029/priority-tracks`; input/output hashes and explicit timeout status are in `provenance.json`. No new recordings, post-scan TLEs, production changes or golden-fixture changes. Fourteen focused acceptance/control tests passed.
'''
    (out/'README.md').write_text(text)
    print('Published local report',out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())
