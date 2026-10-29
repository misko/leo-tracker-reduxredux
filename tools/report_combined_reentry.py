"""Evaluate sealed reentry experiments; GPS is used only in this report."""

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

from debug_fast_graph_unassociated import read, write
from report_graph_covariance_qualification import error_km, SITE

ARMS = ('c0', 'fitted_c')
METHODS = ('baseline', 'support', 'policy')
LABELS = ('Baseline', 'Support backoff', 'Combined reentry')
COLORS = ('#777777', '#0072b2', '#d55e00')


def stats(rows, cases, arm, method):
    selected = [r for r in rows if r['case'] in cases and r['arm'] == arm]
    errors = [r[method+'_error_km'] for r in selected]
    points = sum(r[method+'_points'] for r in selected)
    total = sum(r['total_GLRT'] for r in selected)
    return dict(n=len(errors), median_km=float(np.median(errors)), mean_km=float(np.mean(errors)),
                p90_km=float(np.percentile(errors, 90)), worst_km=max(errors),
                associated_points=points, total_GLRT=total, coverage_percent=100*points/total)


def audit_regressions(root, study):
    """Replay endpoints without optimizing or changing any decision."""
    from benchmark_graph_covariance import load_case
    from combined_family_reentry import build
    audits = {}
    for case in ('DS24-0079', 'DS24-0093', 'DS24-0099'):
        result = read(study/case/'result.json')
        assert result['support_status'] != 'accepted'
        d = load_case(root, case)
        k = result['proposal']['row']
        p, _ = d['problems']['c0']
        keep = d['keep'].copy(); keep[p.slices[k]] = True
        track = d['scan'].tracks[p.members[k]]
        item = dict(proposal=result['proposal'], times_s=track['times'], arms={})
        for arm in ARMS:
            stages = dict(support={key:result['support'][arm][key]
                for key in ('endpoint_east_north_km', 'endpoint_latlon')})
            for name in ('unconstrained', 'constrained'):
                r = read(study/case/(name+'.json'))[arm]
                q = build(d, keep, arm, np.array(r['phase_reference']), k, result['selected_sigma_hz'])
                c = q.calculate(np.array(r['endpoint_east_north_km']))
                delta = abs(c['negative_twice_elbo']-r['negative_twice_elbo'])
                assert delta < 1e-5, (case, arm, delta)
                gate = next(g for g in r['gates']['tracks'] if g['component'] == track['key'])
                stages[name] = dict(endpoint_east_north_km=r['endpoint_east_north_km'],
                    endpoint_latlon=r['endpoint_latlon'], score=r['negative_twice_elbo'],
                    conditional_residual_hz=c['conditional_residual_hz'][q.slices[k]],
                    target_gate={key:value for key,value in gate.items() if key != 'observation_ids'},
                    minimum_gate_slack=r.get('minimum_gate_slack'), replay_difference=delta)
            item['arms'][arm] = stages
        audits[case] = item
    return audits


def run(args):
    study = args.study; out = args.output; out.mkdir(parents=True, exist_ok=False)
    protocol = read(study/'protocol.json'); root = Path(protocol['root'])
    cohorts = dict(primary=protocol['primary_cases'], remaining=protocol['remaining_cases'])
    cohorts['all'] = sorted(cohorts['primary']+cohorts['remaining'])
    results = {c:read(study/c/'result.json') for c in cohorts['all']}
    rows = []
    for case,d in results.items():
        total = len(read(root/case/'observations.json'))
        for arm in ARMS:
            row = dict(case=case, cohort='primary' if case in cohorts['primary'] else 'remaining',
                       arm=arm, total_GLRT=total, status=d['status'], support_status=d['support_status'],
                       sigma_hz=d.get('selected_sigma_hz'), seconds=d['seconds'])
            for method in METHODS:
                r = d[method][arm]
                row.update({method+'_error_km':error_km(r['endpoint_latlon']),
                            method+'_points':r['proposed_associated_points'],
                            method+'_RMS_hz':r['RMS_hz'], method+'_score':r['negative_twice_elbo']})
            assert set(d['baseline'][arm]['proposed_associated_ids']) <= set(d['policy'][arm]['proposed_associated_ids'])
            rows.append(row)
    summary = {cohort:{arm:{m:stats(rows,cases,arm,m) for m in METHODS} for arm in ARMS}
               for cohort,cases in cohorts.items()}
    write(out/'summary.json', dict(statistics=summary, evaluation_site=SITE, rows=rows))
    with (out/'per_scan.csv').open('x', newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n'); w.writeheader(); w.writerows(rows)
    plt.rcParams.update({'font.size':10, 'axes.grid':True, 'grid.alpha':.25})
    fig, axes = plt.subplots(2,3,figsize=(15,8),layout='constrained')
    for j,(cohort,cases) in enumerate(cohorts.items()):
        for i,arm in enumerate(ARMS):
            rr=[r for r in rows if r['case'] in cases and r['arm']==arm]
            for m,label,color in zip(METHODS,LABELS,COLORS):
                y=np.sort([r[m+'_error_km'] for r in rr])
                axes[i,j].step(y,np.arange(1,len(y)+1)/len(y),where='post',label=label,color=color)
            axes[i,j].axvline(.5,color='black',ls=':',label='500 m goal')
            axes[i,j].set(title=f'{cohort}: {len(cases)} scans, {arm}',xlabel='Position error (km)',ylabel='Fraction of scans',ylim=(0,1.04))
            axes[i,j].legend(fontsize=8)
    fig.suptitle('More GLRT association does not guarantee better position: frozen decisions, evaluation afterward')
    fig.savefig(out/'position_distributions.png',dpi=160); plt.close(fig)

    fig,axes=plt.subplots(2,1,figsize=(15,8),layout='constrained')
    rr=[r for r in rows if r['arm']=='fitted_c'];x=np.arange(len(rr))
    for m,label,color in zip(METHODS,LABELS,COLORS):
        axes[0].plot(x,[r[m+'_error_km'] for r in rr],'o-',color=color,label=label)
    for j,(m,label,color) in enumerate(zip(METHODS,LABELS,COLORS)):
        axes[1].bar(x+(j-1)*.25,[100*r[m+'_points']/r['total_GLRT'] for r in rr],width=.25,color=color,label=label)
    for ax in axes:
        ax.set(xticks=x,xticklabels=[r['case'][-4:] for r in rr],xlabel='DS24 scan');ax.legend(ncol=3)
    axes[0].set(ylabel='Fitted-c error (km)');axes[0].axhline(.5,color='black',ls=':')
    axes[1].set(ylabel='Associated original GLRT winners (%)',ylim=(0,100))
    fig.savefig(out/'per_scan.png',dpi=160);plt.close(fig)

    audits=audit_regressions(root,study);write(out/'regression_audit.json',audits)
    fig,axes=plt.subplots(3,2,figsize=(13,12),layout='constrained')
    for i,(case,d) in enumerate(audits.items()):
        stages=d['arms']['fitted_c']; origin=np.array(stages['support']['endpoint_east_north_km'])
        xy=np.array([stages[m]['endpoint_east_north_km'] for m in ('support','unconstrained','constrained')])-origin
        axes[i,0].plot(xy[:,0],xy[:,1],':',color='#777777')
        for j,(name,marker,color) in enumerate(zip(('support','unconstrained','constrained'),('o','s','X'),COLORS)):
            er=error_km(stages[name]['endpoint_latlon'])
            axes[i,0].scatter(*xy[j],marker=marker,color=color,s=90,label=f'{name}: {er:.3f} km error')
        axes[i,0].set(title=f'{case}, NORAD {d["proposal"]["norad"]}',xlabel='East from preceding RF estimate (km)',ylabel='North from preceding RF estimate (km)')
        axes[i,0].axis('equal');axes[i,0].legend(fontsize=8)
        for name,color in [('unconstrained','#0072b2'),('constrained','#d55e00')]:
            r=stages[name];g=r['target_gate']['conditional_residual_gate']
            axes[i,1].plot(d['times_s'],r['conditional_residual_hz'],'o-',ms=3,color=color,label=f'{name}, RMS {g["rms_hz"]:.1f} Hz')
        axes[i,1].axhline(0,color='black',lw=.8);axes[i,1].set(xlabel='Scan time (s)',ylabel='Target conditional residual (Hz)');axes[i,1].legend(fontsize=8)
    fig.suptitle('Regressions: position moves while residual gates are forced to their acceptance boundary\nLines connect endpoints; they are not optimizer trajectories')
    fig.savefig(out/'regressions.png',dpi=160);plt.close(fig)

    sensitivity=[];base=results['DS24-0089']
    for folder,method in [('sensitivity','recovery'),('sensitivity-controls','control')]:
        for f in sorted((study/folder).glob('*/sensitivity.json')):
            d=read(f);ref=base['policy' if method=='recovery' else 'support']
            for arm in ARMS:
                delta=1000*(np.array(d['arms'][arm]['endpoint_east_north_km'])-ref[arm]['endpoint_east_north_km'])
                sensitivity.append(dict(trial=f.parent.name,method=method,arm=arm,accepted=d['accepted'],
                    displacement_m=float(np.linalg.norm(delta)),east_north_change_m=delta,
                    jitter_seed=d['jitter_seed']))
    write(out/'sensitivity_summary.json',sensitivity)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    starts=[r for r in sensitivity if r['trial'].startswith('start') and r['arm']=='fitted_c']
    axes[0].bar(np.arange(len(starts)),[r['displacement_m'] for r in starts],color='#0072b2')
    axes[0].set(xticks=np.arange(len(starts)),xticklabels=['−1 km E','+1 km E','−1 km N','+1 km N'],ylabel='Endpoint change (m)',title='Recovery: alternate starts, all four accepted')
    for j,(method,color) in enumerate([('control','#777777'),('recovery','#d55e00')]):
        ss=[r for r in sensitivity if r['method']==method and r['arm']=='fitted_c' and r['jitter_seed'] is not None]
        xx=np.array([r['jitter_seed'] for r in ss])+(j-.5)*.3
        axes[1].bar(xx,[r['displacement_m'] for r in ss],width=.3,color=color,label=method)
        for a,r in zip(xx,ss):
            if not r['accepted']:axes[1].text(a,r['displacement_m']+30,'REJECT',rotation=90,ha='center',va='bottom',fontsize=8)
    axes[1].set(xticks=range(4),xlabel='5 Hz independent jitter seed',ylabel='Endpoint change from own unperturbed fit (m)',title='Matched baseline controls also reject seed 2');axes[1].legend();axes[1].margins(y=.3)
    fig.suptitle('0089 conditional stability: fixed graph, identity, noise design and 1,000 Hz prior\nRejected endpoints shown diagnostically; they were not adopted')
    fig.savefig(out/'sensitivity.png',dpi=160);plt.close(fig)

    calibration=read(study/'correlation-0018/calibration.json');folds=[]
    for f in sorted((study/'correlation-0018').glob('*.json')):
        d=read(f)
        if 'predictions' not in d:continue
        for arm in ARMS:
            white=d['predictions']['white'][arm]['joint'];corr=d['predictions']['correlated'][arm]['joint']
            folds.append(dict(norad=d['norad'],arm=arm,points=d['held_points'],gain=white['objective']-corr['objective'],
                calibration_qualified=d['calibration']['qualified'],joint_noise_pass=corr['noise']['noise_screen_pass'],
                training_failed=[g['component'] for g in d['training_fold'][arm]['gates']['tracks']+d['training_fold'][arm]['linear_gates'] if not g['compatible']]))
    write(out/'correlation_summary.json',dict(null=calibration['null'],correlated=calibration['correlated'],qualified=calibration['qualified'],folds=folds))
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    origin=calibration['null']['selection_score'];corr=calibration['correlated']
    axes[0].bar([0,1,2],[0,corr['objective']-origin,corr['selection_score']-origin],color=['#777777','#009e73','#d55e00'])
    axes[0].axhline(0,color='black');axes[0].set(xticks=[0,1,2],xticklabels=['White','Correlated: raw','Correlated: penalized'],ylabel='Score difference from white (lower is better)',title='Other RX2 families do not justify extra complexity')
    norads=sorted({r['norad'] for r in folds})
    for j,arm in enumerate(ARMS):
        axes[1].bar(np.arange(len(norads))+(j-.5)*.35,[next(r['gain'] for r in folds if r['norad']==n and r['arm']==arm) for n in norads],width=.35,label=arm)
    axes[1].axhline(0,color='black');axes[1].set(xticks=np.arange(len(norads)),xticklabels=norads,xlabel='Entire satellite family withheld',ylabel='White − correlated predictive score (positive is better)',title='Whole-family prediction gains are mixed');axes[1].legend()
    fig.suptitle('0018: no independent justification for waiving the target correlation failure')
    fig.savefig(out/'correlation.png',dpi=160);plt.close(fig)

    def table(cohort):
        lines=['| Arm | Method | Associated / all GLRT | % | Median km | Mean km | P90 km | Worst km |','|---|---|---:|---:|---:|---:|---:|---:|']
        for arm in ARMS:
            for m,label in zip(METHODS,LABELS):
                s=summary[cohort][arm][m]
                lines.append(f'| {arm} | {label} | {s["associated_points"]:,} / {s["total_GLRT"]:,} | {s["coverage_percent"]:.2f} | {s["median_km"]:.3f} | {s["mean_km"]:.3f} | {s["p90_km"]:.3f} | {s["worst_km"]:.3f} |')
        return '\n'.join(lines)
    per=['| Scan | Support / reentry decision | Prior Hz | Extra points: support + reentry | c=0 baseline → support → combined km | Fitted-c baseline → support → combined km |','|---|---|---:|---:|---:|---:|']
    scores=['| Scan | Reentry points | Fitted-c RMS Hz: preceding → combined | Wider-prior held gain: c=0 / fitted-c |','|---|---:|---:|---:|']
    for case,d in results.items():
        rr={a:next(r for r in rows if r['case']==case and r['arm']==a) for a in ARMS};a=rr['c0']
        es=[' → '.join(f'{rr[arm][m+"_error_km"]:.3f}' for m in METHODS) for arm in ARMS]
        per.append(f'| {case} | {d["support_status"]} / {d["status"]} | {d.get("selected_sigma_hz","—")} | {a["support_points"]-a["baseline_points"]} + {a["policy_points"]-a["support_points"]} | {es[0]} | {es[1]} |')
        if d['status']=='accepted':
            gains=read(study/case/'prior_selection.json')['held_density_gains'];r=rr['fitted_c']
            scores.append(f'| {case} | {r["policy_points"]-r["support_points"]} | {r["support_RMS_hz"]:.2f} → {r["policy_RMS_hz"]:.2f} | {gains["c0"]:.3f} / {gains["fitted_c"]:.3f} |')
    gate_table=['| Scan | Gate | Unconstrained value → constrained | Threshold | Fitted-c error: preceding → unconstrained → constrained km |','|---|---|---:|---:|---:|']
    for case,key,threshold in [('DS24-0079','slope_z',3),('DS24-0093','lag1_acf',4/np.sqrt(44)),('DS24-0099','maximum_step_z',4)]:
        dd=audits[case]['arms']['fitted_c'];vv=[dd[m]['target_gate']['conditional_residual_gate']['diagnostics'][key] for m in ('unconstrained','constrained')]
        es=' → '.join(f'{error_km(dd[m]["endpoint_latlon"]):.3f}' for m in ('support','unconstrained','constrained'))
        gate_table.append(f'| {case} | {key} | {vv[0]:.6f} → {vv[1]:.6f} | {threshold:.6f} | {es} |')
    text=f'''# Removed-family recovery stacked on support backoff — 2026-10-29

**Do not promote the combined recovery rule.** It recovers 547 additional GLRT winners beyond support backoff across seven of 24 completed DS24 fast scans, but worsens localization. The three substantial regressions reproduce a specific failure mode: constrained position fitting can make residual gates pass at their boundary without establishing a correct position. The prior support-backoff candidate remains useful; production is unchanged.

## Full 24-scan result

{table('all')}

Support backoff alone recovers 534 points across five scans. Combined reentry adds another 547, totaling 1,081 beyond baseline. Counts deduplicate original winner observation IDs, including qualified post-fit extensions; they are not counts of polynomial samples. The 29-point difference between the two `c` arms already exists in baseline scan 0011 and is preserved. No rejected-proposal points are included.

![Position distributions](position_distributions.png)

![Every scan: error and GLRT association](per_scan.png)

## Frozen protocol and scope

The original random 12-scan cohort (seed 2026102903) was tested first, followed by the remaining 12 completed cases from the same cached corpus. The policy was frozen before new errors were evaluated and was not changed after observing the primary-cohort regression. These are previously studied, same-site completed cases, not unseen-location validation or a claim about all DS24 recordings.

Baseline is an exact numerical replay of production-equivalent ALGO02 causal signed phase priors and equal-prior family comparison. This experiment begins with cached GLRT winners, graph polynomials and initial family assignments; it does not rerun acquisition or graph construction. Existing ALGO contracts and production services are unchanged.

The regional search is the existing 25×25 km box centered at 37.906, −122.545, with cold start at its center. The evaluation coordinate **{SITE[0]}, {SITE[1]}** is used only after inference, in this report. Distances use a 6371 km spherical great-circle metric. No GPS scoring or post-observation TLE enters candidate selection, width selection, acceptance or optimization.

1. Replay baseline and apply the existing active orbital-support backoff, preserving every previously associated observation ID.
2. Nominate the largest wholly unassociated curved graph component with at least 20 points and 24 seconds. Its original family must have no retained curved or predictive evidence. Only one such proposal per scan is attempted; no observation may overlap the accepted set.
3. Screen the whole bounded causal catalogue at each arm's preceding RF position. Both arms must return the original nominee, RMS ≤450 Hz, absolute offset ≤3,000 Hz and nonnegative minimum elevation. **This nomination screen does not require white residuals.** Joint fitting and final gates were intended to resolve the remaining discrepancy; this proves too permissive here. The search is a bounded phase grid, not a guarantee of the global best satellite/orbit hypothesis.
4. Compare only the target curve's constant-frequency prior standard deviations, 300 and 1,000 Hz. Randomly hold out 12-second time blocks using seeds 20261029, 0, 1; deduplicate identical withheld block sets. Exclude held values from the normal equations, hold position at the preceding RF estimate, refresh nuisance phase five times, and evaluate held Gaussian predictive density including coefficient covariance. Choose 1,000 Hz only if its summed −2 log predictive-density gain exceeds 2 ln 2 in **each** arm and all training phase updates converge within 0.01 s.
5. Refit with all proposed observations using five phase-refresh rounds of at most 48 position iterations. If either arm fails, try five rounds of at most 20 constrained iterations from the unconstrained endpoints. Existing residual, alias, physical, phase-convergence and point-preservation checks must pass in both arms; otherwise retain support-backoff results.

The randomized folds overlap. Their summed score and 2 ln 2 penalty are an empirical selection heuristic, **not independent Bayes-factor evidence** or an identity probability. The fixed graph, candidate identity and preceding calibration are also conditional inputs. More predictive density at a fixed position does not validate the position after refitting.

Both `c=0` and fitted-`c` use the same input observations, causal catalogue, proposed prior, holdout seeds and optimization budgets. The target width is chosen jointly; GPS never breaks a tie. Each scan ran in an isolated process, four workers, 240-second cap, with qualified fallback saved before expensive work. All 24 completed; no timeout substitution was needed. Per-scan run times and full receipts are included.

## Original 12 scans

{table('primary')}

## Remaining 12 scans, unchanged policy

{table('remaining')}

## Every decision, including regressions

{chr(10).join(per)}

## Frequency fit is not position accuracy

{chr(10).join(scores)}

Aggregate RMS here is computed on each method's accepted evidence, so the observation set changes. It is descriptive, not a controlled likelihood comparison. The paired `c` arms within each proposal are controlled. Exact objective and RMS values, including rejected fits, are archived. The held-width scores compare the same withheld observations under the two candidate priors.

## Why 0079, 0093 and 0099 regress

{chr(10).join(gate_table)}

![Regressing track residuals and endpoint movement](regressions.png)

All three accept at an active residual boundary. For 0093, the fitted-c unconstrained solution has a 50.48 Hz target RMS and lag-one correlation 0.776575; the constraint moves the endpoint roughly one kilometer farther, reducing RMS to 32.57 Hz and correlation to 0.603022, just below 4/√44. Position error nevertheless rises to 2.272 km from 0.766 km before reentry. The same-evidence objective worsens from 38,990.04194 to 38,995.14008 under the constraint. Endpoint replay agrees within 1e-5.

0079 lands at slope z≈3; 0099 lands at step z≈4. Both selected the original 300 Hz prior, so widening the constant prior alone cannot explain the regressions. This is evidence against using constrained residual feasibility as sufficient evidence to accept a removed family. It does not by itself prove that any of these satellite identities is wrong, that a graph join is wrong, or that all residual discrepancy is orbital. Association ambiguity, residual covariance and model mismatch remain possible underlying causes.

The connecting lines in the left panels show baseline, unconstrained and constrained **endpoints**, not the optimizer's sampled trajectory. Residuals are conditional residuals at the saved endpoints; no new fit or retuned policy was used to produce this diagnostic.

## 0089: useful recovery, limited stability evidence

The general rule independently selects 1,000 Hz from held predictive gains of 10.122 (`c=0`) and 12.165 (fitted-`c`). It recovers 63 points, taking association from 3,703/4,759 (77.81%) to 3,766/4,759 (79.13%). Errors change from 2.188 to 2.079 km and 2.205 to 2.126 km respectively. This reproduces the earlier hand-selected prototype with a general prior selector.

![0089 sensitivity and matched baseline controls](sensitivity.png)

Four starts at ±1 km east/north all pass and return within 0.3 m of the unperturbed endpoint. Four independent 5 Hz perturbations of the graph observation values pass in three cases. A matched baseline-only replay also rejects the same seed 2. Thus the failure is shared numerical/model fragility, not evidence that recovery alone introduced it. Even accepted seed 3 moves the fitted-c endpoint by 807 m with recovery and 778 m in the control; passing gates does not establish stability. Large rejected diagnostic displacements are not adopted positions. The baseline controls were added after observing the failure to investigate attribution; they are separate from the frozen policy benchmark.

These tests keep graph membership, identity, noise design and the 1,000 Hz prior fixed. They do not rerun GLRT acquisition or prior selection, and four perturbations cannot estimate a reliable failure probability. Every occurrence of an observation ID receives the same perturbation, preventing inconsistent duplicated evidence. Both arms are reported in the machine-readable sensitivity summary.

## 0018: independent low-amplitude correlation audit

The 89-point RX2 CH3 target remains rejected. Its restored RMS is only about 26 Hz, but lag-one correlation still exceeds the unchanged 4/√89 screen. We investigated whether independent evidence justified a modest correlated-noise model rather than simply relaxing this gate.

Ten curves from six other RX2 families in the target interval ±12 seconds train the noise model; target family 56781 is excluded. The search includes white scales 10–120 Hz, correlation amplitudes 10–80 Hz, time scales 0.25–10 s, and receiver-shared versus family-specific correlation, with a 2 ln(n)+2 ln 2 complexity penalty and 300 Hz per-curve constants. Hyperparameters are learned in `c=0` and frozen for both arms.

The best white model has 20 Hz scale and score 3,048.900. The best correlated model has a 10 Hz family-specific amplitude and 10 s time scale: raw score 3,041.446, but penalized score 3,054.448. It fails the complexity criterion by 5.548.

![0018 training and whole-family predictive evidence](correlation.png)

The two largest independent training families were then removed entirely from RF calibration across receivers, including predictive tracks, before refitting. Their causal phase priors were restored, and noise was relearned excluding both target and held family. Whole-family prediction gains are +0.710/+0.823 for NORAD 69316 (129 points), but −2.790/−2.786 for NORAD 59304 (78 points), for `c=0`/fitted-`c`. Both remaining calibration fits have no residual gate failures and both held joint correlated screens pass, but neither fold qualifies the extra noise model by its training penalty. The fixed graph and identity remain assumptions. This is mixed evidence; no target recovery or covariance change is adopted.

## Decision and next experiment

Keep production unchanged. Do not publish a new ALGO number for combined reentry. The narrower support-backoff candidate has improved five scans in both arms and left nineteen unchanged on this 24-scan completed-case cohort; wider production qualification remains separate.

The next parsimonious experiment should separate **recognizing a plausible track** from **allowing it to move position**. Keep removed-family candidates as predictive-only evidence first. Test them against a leave-one-family-out receiver calibration with coefficient uncertainty, and require their inclusion to predict other independent satellite families consistently. Evaluate candidate identity alternatives and common residual patterns before adding any orbital or receiver correction. Learn any additional covariance or prior scale from independent families, rather than using the target's failure to justify it.

Freeze an RF-only comparison that ablates the constrained acceptance rescue against predictive-only retention, with unchanged gates and matched `c` arms. This should determine whether the shared regression mechanism can be avoided without discarding useful coverage. Choosing an endpoint because it is nearer GPS, selectively blacklisting the three scans, or increasing noise until a target passes would not establish a general improvement. Report both coverage and localization across the complete cohort, including lost recoveries and worsened cases, before promotion.

## Reproduction and artifacts

Source tools: `tools/combined_family_reentry.py`, `tools/run_combined_reentry.py`, `tools/study_low_amplitude_correlation.py`, and `tools/report_combined_reentry.py`. Original cached inputs are under `{root}`. Experiment receipts are under `{study}`. Commands below require the original scientific corpus and its read permissions; no new RF collection is involved.

```bash
export PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
.venv/bin/python tools/combined_family_reentry.py case --root /path/to/corpus --case DS24-0089 --output /new/output/DS24-0089
.venv/bin/python tools/combined_family_reentry.py sensitivity --root /path/to/corpus --case DS24-0089 --start 1 0 --output /new/output/start
.venv/bin/python tools/combined_family_reentry.py sensitivity-control --root /path/to/corpus --case DS24-0089 --jitter-seed 2 --output /new/output/control
.venv/bin/python tools/study_low_amplitude_correlation.py --root /path/to/corpus --output /new/output/correlation
.venv/bin/python tools/report_combined_reentry.py --study /path/to/sealed/study --output /new/report
```

See [per-scan CSV](per_scan.csv), [statistics](summary.json), [regression replay](regression_audit.json), [sensitivity](sensitivity_summary.json), [correlation summary](correlation_summary.json), [provenance](provenance.json) and [compressed receipts](receipts.json.gz). Observation hashes in receipts are losslessly interned: replace each `{{"$sha256": i}}` with `sha256_strings[i]`. Source JSON hashes permit verification against the original local outputs.

Previous context: [support-backoff qualification](../2026_10_29_ch78_qualification/README.md) and [priority-track investigation](../2026_10_29_ch78_qualification/priority_tracks/README.md).
'''
    (out/'README.md').write_text(text)
    files=[p for p in sorted(study.rglob('*.json')) if out not in p.parents and not any(x.startswith('publication') for x in p.relative_to(study).parts)]
    hashes={str(p.relative_to(study)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    strings=[];indices={}
    def intern(v):
        if isinstance(v,dict):return {k:intern(x) for k,x in v.items()}
        if isinstance(v,list):return [intern(x) for x in v]
        if isinstance(v,str) and v.startswith('sha256:') and len(v)==71:
            if v not in indices:indices[v]=len(strings);strings.append(v)
            return {'$sha256':indices[v]}
        return v
    records=intern({str(p.relative_to(study)):read(p) for p in files})
    with (out/'receipts.json.gz').open('xb') as f:
        with gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as gz:
            gz.write(json.dumps(dict(format='interned-sha256-strings-v1',sha256_strings=strings,records=records),separators=(',',':'),allow_nan=False).encode())
    names=['combined_family_reentry.py','run_combined_reentry.py','study_low_amplitude_correlation.py','report_combined_reentry.py']
    write(out/'provenance.json',dict(protocol=protocol,source_json_sha256=hashes,
        source_tools_sha256={n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest() for n in names},
        protocol_hash_note='The protocol source hash predates sensitivity-control and reporting additions; cohort acceptance code was not changed.'))
    print(json.dumps(summary['all'],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())
