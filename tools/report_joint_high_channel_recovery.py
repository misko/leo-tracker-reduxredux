"""Evaluate sealed joint attachment results, with GPS confined to this reporter."""
import argparse
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
from report_graph_covariance_qualification import error_km,SITE

METHODS=('baseline','white_existing','covariance_existing','covariance_physical')
LABELS=('Guarded baseline','Alternative identity + white','Covariance + existing tests','Covariance + physical tests')
COLORS=('#777777','#e69f00','#0072b2','#009e73')
ARMS=('c0','fitted_c')


def main(args):
    study=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False)
    cohort=study/'joint-attachment-cohort';execution=read(cohort/'execution.json');protocol=read(cohort/'protocol.json')
    assert len(execution)==len(protocol['cases'])==28
    rows=[];decisions=[]
    for item in protocol['cases']:
        case=item['case'];path=cohort/case
        terminal=next(t for t in execution if t['case']==case)
        d=read(path/'result.json') if (path/'result.json').exists() else read(path/'fallback.json')
        total=len(read(Path(item['root'])/case/'observations.json'))
        decision=dict(case=case,execution=terminal['status'],status=d['status'],variants={})
        for name in METHODS[1:]:
            if not (path/(name+'.json')).exists():continue
            v=read(path/(name+'.json'));failures=[]
            if not v['identity_pass']:failures.append('identity comparison')
            if name!='white_existing' and not v['calibration_qualified']:failures.append('covariance training penalty')
            if name!='white_existing' and not all(g>0 for g in v['held_density_gains'].values()):failures.append('held density')
            if not (all(q['compatible'] for q in v['physical'].values()) if name=='covariance_physical' else v['existing_screen_pass']):failures.append('initial structure')
            if not v['final_original_gates_pass']:failures.append('old track gates/convergence')
            if not (all(q['compatible'] for q in v['final_physical'].values()) if name=='covariance_physical' else v['final_existing_pass']):failures.append('final structure')
            if not v['preserves_old_points']:failures.append('old point preservation')
            if not all(r['target_min_elevation_deg']>=0 and all(abs(p['bias_hz'])<=3000 and p['raw_RMS_after_bias_hz']<=450 for p in r['physical_target_checks']) for r in v['proposal'].values()):failures.append('absolute RMS/offset/visibility')
            decision['variants'][name]=dict(accepted=v['accepted'],candidate=v['candidate'],reasons=failures,
                diagnostic_error_km={a:error_km(r['endpoint_latlon']) for a,r in v['proposal'].items()})
        decisions.append(decision)
        for arm in ARMS:
            row=dict(case=case,cohort='DS24 development' if case.startswith('DS24') else 'Separate four',arm=arm,total_GLRT=total)
            for name in METHODS:
                r=d['baseline'][arm] if name=='baseline' or name not in d['variants'] else d['variants'][name]['policy'][arm]
                row[name+'_error_km']=error_km(r['endpoint_latlon']);row[name+'_points']=r['proposed_associated_points']
                row[name+'_RMS_hz']=r['RMS_hz'];row[name+'_score']=r['negative_twice_elbo']
            rows.append(row)
    stats={}
    for cohort_name in ('DS24 development','Separate four'):
        stats[cohort_name]={}
        for arm in ARMS:
            rr=[r for r in rows if r['cohort']==cohort_name and r['arm']==arm];stats[cohort_name][arm]={}
            for m in METHODS:
                e=[r[m+'_error_km'] for r in rr];pts=sum(r[m+'_points'] for r in rr);total=sum(r['total_GLRT'] for r in rr)
                stats[cohort_name][arm][m]=dict(scans=len(rr),median_km=float(np.median(e)),mean_km=float(np.mean(e)),
                    worst_km=max(e),points=pts,total_GLRT=total,coverage_percent=100*pts/total)
    pilot=read(study/'joint-attachment-pilot/result.json')
    variants={m:read(study/'joint-attachment-pilot'/(m+'.json')) for m in METHODS[1:]}
    synthetic=read(study/'joint-attachment-synthetic/synthetic.json')
    robustness={p.parent.name:read(p) for p in sorted((study/'joint-attachment-robustness').glob('*/result.json'))}
    write(out/'summary.json',dict(statistics=stats,rows=rows,decisions=decisions,execution=execution,
        pilot={m:dict(accepted=v['accepted'],candidate=v['candidate'],points={a:v['policy'][a]['proposed_associated_points'] for a in ARMS},
            movement_m={a:v['proposal'][a]['displacement_from_CH1_m'] for a in ARMS},physical=v['physical'],final_physical=v['final_physical'],
            common_margin=v['common_margin'],split_margin=v['split_margin']) for m,v in variants.items()},
        synthetic=synthetic,evaluation_site=SITE,pilot_evaluation_site_verified=False,
        independent_family_confirmation=False))
    with (out/'per_scan.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    plt.rcParams.update({'font.size':10,'axes.grid':True,'grid.alpha':.2})
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for col,cohort_name in enumerate(stats):
        for row,arm in enumerate(ARMS):
            ax=axes[row,col];rr=[r for r in rows if r['cohort']==cohort_name and r['arm']==arm]
            for j,(m,label,color) in enumerate(zip(METHODS,LABELS,COLORS)):
                values=np.sort([r[m+'_error_km'] for r in rr]);ax.step(values,np.arange(1,len(values)+1)/len(values),where='post',color=color,label=label,ls=('-','--',':','-.')[j],lw=2.5-j*.3)
            ax.axvline(.5,color='black',ls=':');ax.set(title=f'{cohort_name}: {arm}',xlabel='Position error (km)',ylabel='Fraction of scans');ax.legend(fontsize=7)
    fig.suptitle('28 other scans: all policy distributions coincide; no extra proposal accepted')
    fig.savefig(out/'position_distributions.png',dpi=160);plt.close(fig)
    tracks={t['key']:t for t in read(args.pilot_root/'SCAN/tracks.json')}
    r=variants['covariance_physical']['proposal']['fitted_c'];t=np.asarray(r['target_times_s']);raw=np.asarray(r['target_raw_hz']);owner=np.asarray(r['target_owners'])
    from leo.analysis.research.retained_track_likelihood import PERIOD
    fig,axes=plt.subplots(2,2,figsize=(13,7),layout='constrained')
    for k,e in enumerate(variants['covariance_physical']['extras']):
        track=tracks[e['component']];use=owner==k;bias=r['physical_target_checks'][k]['bias_hz'];values=np.asarray(track['values'])+e['alias']*PERIOD
        axes[0,k].scatter(t[use],values/1000,s=12,color='#e69f00',label='Original GLRT')
        axes[0,k].plot(t[use],(values-raw[use]+bias)/1000,color='#0072b2',label='Orbit + receiver terms + curve offset')
        axes[1,k].plot(t[use],raw[use]-bias,'.-',color='#009e73');axes[1,k].axhline(0,color='black',lw=.8)
        axes[0,k].set(title=e['component'].split('-RF')[0],ylabel='Graph CFO + fixed alias (kHz)');axes[0,k].legend(fontsize=7)
        axes[1,k].set(xlabel='Time in scan (s)',ylabel='Residual after curve offset (Hz)')
    fig.suptitle('Pilot: all 58 CH7 and 55 CH8 points attached to causal family 57701\nResiduals remain correlated; they enter one joint predictive likelihood')
    fig.savefig(out/'pilot_tracks.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for i,a in enumerate(ARMS):
        counts=[pilot['baseline'][a]['proposed_associated_points']]+[variants[m]['policy'][a]['proposed_associated_points'] for m in METHODS[1:]]
        axes[0].bar(np.arange(4)+(i-.5)*.35,np.asarray(counts)/3283*100,width=.35,label=a)
    axes[0].set(xticks=range(4),xticklabels=['Baseline','White','Old tests','Physical tests'],ylabel='Pilot associated GLRT (%)',ylim=(70,85));axes[0].legend()
    for k,kind in enumerate(('white','correlated','interleaved')):
        selected=[v for v in synthetic['rows'] if v['geometry']==kind]
        axes[1].plot(range(5),[100*v['rate'] for v in selected],'o-',label=kind)
    axes[1].set(xticks=range(5),xticklabels=['Null','Offset','Slope','Curvature','Step'],ylabel='Synthetic rejection rate (%)');axes[1].legend(fontsize=8)
    fig.suptitle('Coverage gain is separated from independently calibrated test behavior')
    fig.savefig(out/'coverage_and_calibration.png',dpi=170);plt.close(fig)
    metrics=['| Cohort | Arm | All four policies: associated % | Mean km | Median km | Worst km |','|---|---|---:|---:|---:|---:|']
    for name,arms in stats.items():
        for a,s in arms.items():
            b=s['baseline'];metrics.append(f'| {name} | {a} | {b["coverage_percent"]:.2f} | {b["mean_km"]:.3f} | {b["median_km"]:.3f} | {b["worst_km"]:.3f} |')
    rejection=['| Scan | Nominee | Physical-variant rejection reasons |','|---|---:|---|']
    for d in decisions:
        v=d['variants'].get('covariance_physical')
        rejection.append(f'| {d["case"]} | {v["candidate"] if v else "—"} | {", ".join(v["reasons"]) if v else d["status"]} |')
    families=['| Held family | Valid training fits | Gain c=0 / fitted-c |','|---|---|---:|']
    for name,d in robustness.items():
        if name.startswith('family-prior') and 'gains' in d:families.append(f'| {d["norad"]} | {d["valid_training_fits"]} | {d["gains"]["c0"]:.3f} / {d["gains"]["fitted_c"]:.3f} |')
    text=f'''# Joint CH7/CH8 attachment with physical covariance tests — 2026-10-29

**The pilot recovers all 113 CH7/CH8 points under the new acceptance screen, preserving CH1. No further points qualify on the other 28 scans, and independent-family prediction is mixed. Keep this experimental; no new ALGO or production deployment is justified.**

Implemented all three proposed variants with matched causal catalogue search, observations, priors, five phase-refresh rounds and 48 position iterations per round, in both `c=0` and fitted-`c`. New code does not use evaluation GPS. The existing guarded recovery result is the baseline, not the older production-only point set.

## Pilot recovery and its limits

| Variant | Candidate | Adopted pilot GLRT | % | Outcome |
|---|---:|---:|---:|---|
| Guarded baseline | — | 2,590 | 78.89 | CH1 recovery retained |
| Alternative identity + independent noise + existing tests | 57701 | 2,590 | 78.89 | Residual structure fails |
| Alternative identity + covariance + existing tests | 57701 | 2,590 | 78.89 | Additional randomized partition fails |
| Alternative identity + covariance + physical tests | 57701 | **2,703** | **82.33** | **Passes frozen experimental screen** |

Both arms retain all 58 CH7 and 55 CH8 points as predictive evidence. They do not fit receiver calibration or orbital corrections. Curved likelihood remains 2,142 points, predictive likelihood rises from 440 to 553, and eight points remain post-fit-only. Every preceding associated observation is preserved. The exact original CH1 target remains in the curved likelihood.

![Pilot observations, orbit predictions and residuals](pilot_tracks.png)

The correlated variant reproduces the earlier covariance experiment's endpoint: displacement from the CH1 baseline is **52.99 m / 59.38 m**, for c=0 / fitted-c. These are displacements, not measured position-error reductions; this pilot has no verified site label in this study. The improvement here is a general alternative-identity path and a revised acceptance screen, not a new lower-residual endpoint compared with the earlier covariance prototype.

The same-family candidate beats other tested common identities by **676.09 / 671.08** score units and the penalized separate-identity alternative by **699.70 / 691.71**. These are conditional score margins, not calibrated identity probabilities. They depend on the shortlist, graph, aliases and current RF calibration.

![Pilot coverage and synthetic calibration](coverage_and_calibration.png)

## What the new residual screen computes

Let r be the predictive residual and C its full covariance. The physical mean statistic is `(1' C^-1 r) / sqrt(1' C^-1 1)`. Slope and quadratic contrasts use GLS after projecting out lower-order terms. Step contrasts search every allowed split with at least three points on each side, projecting out constant and linear terms. Both the residual and the physical test design are whitened. Tests cover the combined observations and individual channels.

An additional statistic measures adjacent physical-time residual products within each channel, subtracting their expectation under C. It avoids treating arbitrarily interleaved channels as a time series. Chi-square energy checks catch excessive residual magnitude relative to the model. The analysis includes full curves and all distinct randomized held-block partitions, seeds 20261029 and 0–7, sharing 12-second blocks across channels. Training points are excluded from held normal equations; held tests use the conditional covariance.

The maximum absolute GLS/adjacent-product statistic is calibrated using **4,096 simulations**, seed **82137**, with 0.5% nominal upper-tail allocation across all contrasts and partitions. Chi-square energy receives the remaining 0.5% through a Bonferroni bound. This is a fixed-covariance, conditional 1% screen; it is not a 1% guarantee after satellite/model selection, covariance estimation, both c arms and position optimization.

Synthetic validation used a separate seed **94721**, before real-target decisions: 1,000 trials each for white, correlated and interleaved-channel geometries. Correct-model rejection rates were **1.2%, 1.0%, 0.9%**. Large injected offsets (1,500 Hz), slopes (1,000 Hz end-to-end), quadratic structure and 700 Hz steps were rejected in **96.7–100%** of trials. These examples demonstrate sensitivity to large errors, not guaranteed detection of smaller or orbit-shaped mistakes. Tests also verify permutation invariance, direct GLS agreement, conditional masks and malformed-covariance rejection.

On the pilot, the physical screen's maximum statistic is **3.713 / 4.113**, below geometry-specific calibrated thresholds about **7.028**; the largest statistic is a held CH7 adjacent-product contrast. The corresponding simulated maximum-tail probabilities are **0.129 / 0.067**. This threshold is not a universal “7-sigma” mean gate: the maximum includes non-Gaussian quadratic statistics and searched contrasts. The implementation changes both the physical test geometry and multiple-testing calibration; this experiment does not isolate their contributions. A dedicated test-power comparison remains useful before promotion.

## Candidate search, covariance and acceptance

Select the largest wholly unassociated overlapping CH7/CH8 pair on one receiver, requiring at least 20 points and 24 s per curve and 20 s overlap. If no pair exists, test the largest eligible single high-channel curve. The shortlist combines original nominees and the active-family and bounded whole-causal-catalogue winners at each c-arm RF endpoint. Both arms must prefer the same identity with at least a 10-unit score margin. Pairs are also challenged by separate identities, charging `2 ln K` for the extra discrete choice. The unmatched outcome is rejection/fallback, **not** a calibrated clutter-density model. A new catalogue identity outside the existing prior design is recorded but not instantiated by this prototype.

Covariance parameters use the existing independent-family training grid and complexity penalty. Every candidate family is excluded from training. The selected law is fixed across c arms. The correlated model must beat white noise in training and have positive total held predictive-density improvement in both arms. The covariance includes curve constants and propagated calibration uncertainty; the receiver-process covariance is shared between new curves. As in the preceding prototype, it transfers the covariance law rather than jointly conditioning the receiver-process realization on incumbent observations. This conditional approximation remains a limitation.

All three variants receive the same bounded diagnostic position fit even when preliminary checks fail. Adoption requires prechecks, final target screens, every old curved/predictive gate, phase convergence, original-point preservation, elevation ≥0, absolute curve bias ≤3,000 Hz and raw residual RMS after curve offset ≤450 Hz. There is no constrained rescue, clipping, endpoint trimming, GPS-based selection or post-observation TLE.

## Other 28 scans: no accepted additional association or accuracy gain

All 28 jobs completed within their 240-second caps using four isolated workers. Fourteen had no eligible remaining high-channel proposal; fourteen were tested and rejected. The three variant policies therefore retain the preceding guarded baseline exactly on these scans.

{chr(10).join(metrics)}

![Position distributions: policies coincide](position_distributions.png)

This includes the 24 development scans and four disjoint later recordings. Rejected diagnostic endpoints and their errors are saved separately in `summary.json`; favorable errors never qualify a rejected proposal. Frequency RMS and scores are in `per_scan.csv`, separately from evaluation error. The reporting-only site is {SITE[0]}, {SITE[1]}. These same-site cohorts do not demonstrate generalization to new locations.

Three informative cases—0014, 0019 and 0099—pass the new covariance-aware structure tests but fail the absolute physical RMS gate, at approximately 3.4 kHz, 10.2 kHz and 714 Hz in fitted-c. Large predictive uncertainty can make standardized residuals look acceptable; retaining the absolute physical gate prevents those from becoming accepted associations. This is why a covariance-screen pass alone is insufficient.

{chr(10).join(rejection)}

## Starting positions and independent-family checks

Four starts at ±1 km east/north around the regional-box center all retain the pilot recovery and return within **0.005 m** of the original endpoint. This is numerical stability with fixed graph, candidate and noise law; it does not prove global convergence or physical accuracy.

Remove each held family everywhere from curved calibration and existing predictive entries, restore its causal phase prior, relearn covariance without it, and compare prediction of its complete eligible curves before and after adding the CH7/CH8 pair. The candidate 57701 is excluded from voting. Two other families occur among the three largest eligible families:

{chr(10).join(families)}

Both corrected deletion fits pass the retained-data gates; supplemental checks also confirm the independently learned covariance penalty, new target physical tests and absolute physical bounds in both folds and both arms. Gains are small and mixed; they **do not independently confirm improved localization**. A requirement for two positive paired witnesses would not accept this pilot addition.

The first deletion control retained nominal orbital support globally to preserve held-family uncertainty; that reintroduced the known unsupported CH1-owner failure. Those invalid control receipts remain archived. The corrected check keeps active support for training and adds the held family's original three-mode prior covariance only to its held predictive distribution, without fitting those modes. This preserves CH1 and gives valid training fits. The correction changes validation bookkeeping, not the frozen attachment algorithm or its acceptance decisions. A third requested family index initially exceeded the two available independent families; its explicit corrected receipt reports no additional eligible family rather than silently duplicating a witness.

## Decision and reproducibility

Keep the new branch experimental. It accounts for all pilot CH7/CH8 points without forcing the old identity, removing samples or fitting a free correction through them. However, it has no further accepted recovery on 28 other scans and mixed independent-family evidence. **Do not promote or deploy it as a demonstrated accuracy improvement.** Next, broaden independently nominated high-channel evidence and assess covariance-model uncertainty/test power; do not tune thresholds using these known position errors.

Source: `src/leo/analysis/research/covariance_structure.py`, `tools/test_joint_high_channel_recovery.py`, `tools/run_joint_high_channel_recovery.py`, `tools/check_joint_attachment_robustness.py`, and this reporter. Existing predictive-position helper gained opt-in starting position, problem factory and target-covariance capture; existing callers retain their defaults. **24 focused tests passed.** No scientific golden fixture, public persisted contract, RF acquisition or production service changed.

```bash
export PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python tools/test_joint_high_channel_recovery.py synthetic --output NEW_SYNTHETIC
python tools/test_joint_high_channel_recovery.py case --root INPUT_ROOT --case SCAN --source GUARDED_SOURCE --output NEW_PILOT
python tools/run_joint_high_channel_recovery.py --study COHORT_ROOT --output NEW_COHORT
python tools/report_joint_high_channel_recovery.py --study COHORT_ROOT --pilot-root PILOT/run/inference --output NEW_REPORT
```

See [summary and decisions](summary.json), [per-scan metrics](per_scan.csv), [provenance](provenance.json), and [compressed scientific receipts](receipts.json.gz). Repeated hash strings are losslessly interned: replace `{{"$sha256": i}}` with `sha256_strings[i]`. Previous [manual-recovery accounting](../2026_10_29_manual_recovery_accounting/README.md) identifies the original integration gaps.
'''
    (out/'README.md').write_text(text)
    roots=[study/n for n in ('joint-attachment-cohort','joint-attachment-pilot','joint-attachment-synthetic','joint-attachment-robustness')]
    files=[f for root in roots for f in sorted(root.rglob('*.json'))];strings=[];indices={}
    def intern(v):
        if isinstance(v,dict):return {k:intern(x) for k,x in v.items()}
        if isinstance(v,list):return [intern(x) for x in v]
        if isinstance(v,str) and v.startswith('sha256:') and len(v)==71:
            if v not in indices:indices[v]=len(strings);strings.append(v)
            return {'$sha256':indices[v]}
        return v
    records=intern({str(f.relative_to(study)):read(f) for f in files})
    with (out/'receipts.json.gz').open('xb') as f:
        with gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as gz:gz.write(json.dumps(dict(sha256_strings=strings,records=records),separators=(',',':'),allow_nan=False).encode())
    write(out/'provenance.json',dict(protocol=protocol,receipt_sha256={str(f.relative_to(study)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
        publication_source_sha256={str(p.relative_to(Path(__file__).parents[1])):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__),Path(__file__).parent/'check_joint_attachment_robustness.py')},
        evaluation_only_in_reporter=True))
    print(json.dumps(dict(statistics=stats,execution_count=len(execution),accepted={m:[d['case'] for d in decisions if d['variants'].get(m,{}).get('accepted')] for m in METHODS[1:]}),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','pilot-root','output'):p.add_argument('--'+name,type=Path,required=True)
    main(p.parse_args())
