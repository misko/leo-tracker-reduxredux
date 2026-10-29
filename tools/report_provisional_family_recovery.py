"""Evaluate sealed provisional-recovery decisions; GPS is reporting-only."""
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

METHODS=('baseline','support','unguarded','preconstraint','witness','combined')
LABELS=('Baseline','Support backoff','Unguarded recovery','Target gate guard','Family confirmation','Both guards')
COLORS=('#888888','#0072b2','#d55e00','#009e73','#cc79a7','#000000')
ARMS=('c0','fitted_c')


def run(args):
    study=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False)
    protocol=read(study/'protocol.json');source=Path(protocol['source_study']);root=Path(protocol['root'])
    rows=[];decisions={};fold_rows=[]
    for case in protocol['cases']:
        d=read(source/case/'result.json');path=study/case/'result.json'
        receipt=read(path) if path.exists() else read(study/case/'fallback.json')
        decisions[case]=receipt;total=len(read(root/case/'observations.json'))
        for arm in ARMS:
            row=dict(case=case,arm=arm,total_GLRT=total,status=receipt['status'])
            for m in METHODS:
                r=d[m][arm] if m in ('baseline','support') else d['policy'][arm] if m=='unguarded' or receipt['decisions'][m] else d['support'][arm]
                row[m+'_error_km']=error_km(r['endpoint_latlon']);row[m+'_points']=r['proposed_associated_points']
                row[m+'_RMS_hz']=r['RMS_hz'];row[m+'_score']=r['negative_twice_elbo']
                row[m+'_provisional_points']=len(receipt.get('provisional_observation_ids',[])) if m in receipt['decisions'] and not receipt['decisions'][m] else 0
                assert set(d['support'][arm]['proposed_associated_ids'])<=set(r['proposed_associated_ids']) or m=='baseline'
            rows.append(row)
        for f in sorted((study/case).glob('*.json')):
            if not f.stem.isdigit():continue
            fold=read(f)
            def failures(method):
                return {a:[g['component'] for g in fold[method][a]['gates']['tracks']+fold[method][a]['linear_gates'] if not g['compatible']] for a in ARMS}
            fold_rows.append(dict(case=case,norad=fold['norad'],valid=fold['valid'],held_points=fold['held_points'],
                gains=fold['gains'],before_failures=failures('before'),after_failures=failures('after'),
                selected_sigma_hz=fold['prior_selection']['selected_sigma_hz'],
                phases={m:{a:fold[m][a]['final_phase_change_s'] for a in ARMS} for m in ('before','after')}))
    stats={}
    for arm in ARMS:
        rr=[r for r in rows if r['arm']==arm];stats[arm]={}
        for m in METHODS:
            err=[r[m+'_error_km'] for r in rr];points=sum(r[m+'_points'] for r in rr);den=sum(r['total_GLRT'] for r in rr)
            stats[arm][m]=dict(mean_km=float(np.mean(err)),median_km=float(np.median(err)),p90_km=float(np.percentile(err,90)),
                worst_km=max(err),associated_points=points,total_GLRT=den,coverage_percent=100*points/den,
                provisional_points=sum(r[m+'_provisional_points'] for r in rr))
    write(out/'summary.json',dict(statistics=stats,decisions=decisions,folds=fold_rows,rows=rows,evaluation_site=SITE))
    with (out/'per_scan.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    plt.rcParams.update({'font.size':10,'axes.grid':True,'grid.alpha':.25})
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,arm in zip(axes,ARMS):
        rr=[r for r in rows if r['arm']==arm]
        for m,label,color in zip(METHODS,LABELS,COLORS):
            values=np.sort([r[m+'_error_km'] for r in rr])
            ax.step(values,np.arange(1,len(values)+1)/len(values),where='post',label=label,color=color,ls='--' if m in ('witness','combined') else '-')
        ax.axvline(.5,color='black',ls=':');ax.set(xlabel='Position error (km)',ylabel='Fraction of scans',title=arm);ax.legend(fontsize=8)
    fig.suptitle('24 development scans: provisional tracks do not move position unless a guard accepts')
    fig.savefig(out/'distributions.png',dpi=160);plt.close(fig)
    targets=[c for c,d in decisions.items() if 'preconstraint_target_pass' in d];fig,axes=plt.subplots(2,1,figsize=(13,8),layout='constrained');x=np.arange(len(targets))
    rr=[next(r for r in rows if r['case']==c and r['arm']=='fitted_c') for c in targets]
    for m,label,color in zip(METHODS[1:],LABELS[1:],COLORS[1:]):
        axes[0].plot(x,[r[m+'_error_km'] for r in rr],'o--' if m in ('combined','witness') else 'o-',label=label,color=color)
    for j,m in enumerate(('support','unguarded','preconstraint','witness','combined')):
        axes[1].bar(x+(j-2)*.15,[r[m+'_points']-r['support_points'] for r in rr],width=.15,label=LABELS[METHODS.index(m)],color=COLORS[METHODS.index(m)])
    for ax in axes:ax.set(xticks=x,xticklabels=[c[-4:] for c in targets],xlabel='DS24 scan');ax.legend(fontsize=8,ncol=3)
    axes[0].set(ylabel='Fitted-c position error (km)');axes[1].set(ylabel='Confirmed extra GLRT points over support')
    fig.suptitle('Seven originally accepted recoveries: accuracy and confirmed coverage kept separate')
    fig.savefig(out/'recoveries.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(13,5),layout='constrained')
    for k,arm in enumerate(ARMS):
        for j,f in enumerate(fold_rows):
            color=('#0072b2','#d55e00')[k];gain=f['gains'][arm]
            ax.scatter(j+(k-.5)*.18,gain,marker=('o','s')[k],facecolors=color if f['valid'] else 'none',edgecolors=color,
                       label=arm if j==0 else None)
    ax.axhline(0,color='black',lw=.8);ax.set(xticks=range(len(fold_rows)),xticklabels=[f'{f["case"][-4:]}\n{f["norad"]}' for f in fold_rows],
        ylabel='Held-family predictive score gain (positive is better)',xlabel='Scan / held NORAD')
    ax.tick_params(axis='x',labelsize=7);ax.legend();fig.suptitle('Entire families withheld from both position fits and calibration\nFilled markers: both fits pass existing gates; hollow: fold does not qualify')
    fig.savefig(out/'held_families.png',dpi=160);plt.close(fig)
    metric=['| Arm | Policy | Confirmed GLRT | % | Provisional target points | Median km | Mean km | P90 km | Worst km |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for a in ARMS:
        for m,label in zip(METHODS,LABELS):
            s=stats[a][m];metric.append(f'| {a} | {label} | {s["associated_points"]:,} | {s["coverage_percent"]:.2f} | {s["provisional_points"]} | {s["median_km"]:.3f} | {s["mean_km"]:.3f} | {s["p90_km"]:.3f} | {s["worst_km"]:.3f} |')
    table=['| Scan | Target passes before constraints | Valid folds | Paired witnesses | Target guard / confirmation / both | Fitted-c error: support → unguarded → both km |','|---|---|---:|---|---|---:|']
    for c in targets:
        d=decisions[c];r=next(r for r in rr if r['case']==c);check=d.get('confirmation',{})
        table.append(f'| {c} | {d["preconstraint_target_pass"]} | {check.get("valid_folds",0)} | {check.get("witness_families",[])} | {" / ".join("accept" if d["decisions"][m] else "provisional" for m in ("preconstraint","witness","combined"))} | {r["support_error_km"]:.3f} → {r["unguarded_error_km"]:.3f} → {r["combined_error_km"]:.3f} |')
    folds=['| Scan | Held family | Points | Valid | Predictive gain c=0 / fitted-c | Failing curves before / after (union across arms) |','|---|---:|---:|---|---:|---:|']
    for f in fold_rows:
        counts=[len(set(sum(f[m+'_failures'].values(),[]))) for m in ('before','after')]
        folds.append(f'| {f["case"]} | {f["norad"]} | {f["held_points"]} | {f["valid"]} | {f["gains"]["c0"]:.3f} / {f["gains"]["fitted_c"]:.3f} | {counts[0]} / {counts[1]} |')
    accepts={m:[c for c,d in decisions.items() if d['decisions'][m]] for m in ('preconstraint','witness','combined')}
    execution=read(study/'execution.json')
    text=f'''# Provisional satellite-family recovery and independent-family confirmation — 2026-10-29

Implemented and tested two RF-only guards, separately and together, on all 24 completed DS24 cases from the preceding development benchmark. A blocked recovery remains a provisional graph-track hypothesis and cannot change the reported position. Production and published ALGO contracts are unchanged.

Target gate guard accepts: **{', '.join(accepts['preconstraint']) or 'none'}**. Family confirmation accepts: **{', '.join(accepts['witness']) or 'none'}**. Both guards accept: **{', '.join(accepts['combined']) or 'none'}**.

The simple target guard blocks all three large regressions (0079, 0093, 0099), retains four recoveries and confirms **254 additional points beyond support backoff**, while keeping 203 target points provisional. Its fitted-c median remains 1.087 km; mean improves only from 1.16884 to 1.16639 km, about **2.45 meters** averaged over 24 scans. Its main demonstrated value is preventing the unguarded regression, not delivering a substantial new accuracy gain. It still accepts the small 0010 regression and the mixed-arm 0083 result.

The stricter family test accepts only 0013, adding 57 confirmed points over support and leaving 348 target points provisional. It also blocks 0089's useful 63-point recovery and 0083's fitted-c improvement. Those are real lost recoveries under this rule. For 0013, the second paired witness improves fitted-c predictive score by only 0.027; passing the experimental vote should not be portrayed as strong statistical evidence. Both guards together equal the family-only policy in this cohort.

## Matched c controls and results

{chr(10).join(metric)}

All policies share the same 108,600 original GLRT winners, causal catalogues, existing baseline/support results and full-data recovery proposals. The 29-point baseline difference between `c` arms is inherited from scan 0011. A policy accepts a recovery only as a paired decision; it cannot choose a different satellite or prior using GPS. Frequency RMS and scores are recorded separately in the per-scan CSV. Because evidence membership changes, aggregate RMS is not a controlled accuracy metric.

![Position error distributions](distributions.png)

![Each originally accepted recovery](recoveries.png)

## Exact guards

**Target gate guard:** the restored target itself must pass all its existing residual/profile/alias gates in the original unconstrained full-data fit in both `c` arms. The accepted full-data proposal must still pass every original final gate and preserve all preceding accepted points. This avoids accepting a track solely because constrained position movement makes that same target pass. An older track may still require the existing constrained check; this is an explicit limited ablation, not a ban on all constrained optimization.

**Whole-family confirmation:** take the three largest retained satellite families by complete curved evidence, requiring at least 20 points and 24 seconds per eligible component, with deterministic NORAD tie breaking. Remove each held family everywhere: curved observations across both receivers/channels, and every predictive entry. Reset its phase mean to the strictly causal forecast. Refit the preceding model without recovery from the regional-box center. Reselect the target's 300/1,000 Hz prior using the existing blocked predictive selector inside this fold. Refit with recovery from the same center, with identical five phase-refresh rounds and up to 48 steps per round. No constrained rescue is used inside a fold.

Predict the complete held curved family under each fit, including nuisance coefficient covariance, shared phase/orbit uncertainty and 300 Hz per-curve constants. Held measurement noise uses the existing cached radio scale; no held residual is used to learn a new noise scale. Compare the same held observations using their joint Gaussian predictive negative twice log density. No random held subset is used for the family vote. Existing predictive-only members of that family are excluded from training but are not included in the held score.

A fold is valid only if both before/after fits pass all existing curved and predictive gates and phase convergence in both `c` arms, and the held family is above the horizon. Confirmation needs **at least two distinct valid families with positive predictive gain in both arms**, and positive aggregate gain over all valid folds in both arms. Invalid folds cannot vote. No GPS-derived conflict-cost threshold or displacement cutoff is introduced. These strict rules are deliberately reported as an experimental gate, not calibrated probabilities.

**Both guards** requires the target gate guard and confirmation. It is the conservative provisional policy, not a production promotion.

## Every recovery decision

{chr(10).join(table)}

The other 17 scans had no accepted reentry in the frozen preceding experiment and retain the exact support-backoff result; they were not subjected to a new satellite search. The seven candidates were nominated by the existing full-data procedure, not selected using new GPS errors.

## Family predictions and failure cases

![Whole-family validation gains](held_families.png)

{chr(10).join(folds)}

Positive held density alone cannot qualify an invalid training fold. Conversely, failure to qualify is lack of confirmation under this model; it does not establish that the satellite identity is wrong. The machine-readable summary includes failing component names and phase convergence for every fold, so rejection due to fold instability can be distinguished from a genuinely negative predictive score.

0093 has zero valid folds because the newly restored target still fails its residual screen in all three unconstrained fold fits; the preceding fits pass. Its zero aggregate valid-fold gain therefore means **no qualifying evidence**, not a measured tie. By contrast, 0010 has three valid folds but negative aggregate predictive gain, while 0083 and 0089 each have two valid folds and negative aggregate gain. This distinguishes residual incompatibility from lack of independent predictive support.

The recommended next step is separate-scan validation of the cheap target guard, while retaining the family test as a conservative diagnostic. A less restrictive confirmation rule would need a new frozen protocol and independent testing, not relaxation until these desired recoveries pass. Production remains unchanged.

## Provisional evidence is not confirmed association

For a blocked recovery, only the nominated graph target's original observation IDs are retained as provisional. They do not affect position, receiver calibration, or the confirmed GLRT numerator. Post-fit-only extension points obtained at the blocked endpoint are not retained as provisional merely to inflate coverage. Confirmed old observation IDs are preserved. A provisional identity has not necessarily passed the residual gates at the fallback position; it is explicitly a pending hypothesis, not an accepted orbit overlay at that position.

## Validation scope and reproducibility

The protocol and code hash were saved before this run. However, the same 24 development scans and their earlier errors motivated the guard design. Thus these results are **not an independent generalization claim**, even though inference never reads GPS. The inspected completed DS24 baseline roots contained no compatible additional fast cases beyond this cohort. No threshold was tuned after seeing these new results and no new ALGO version is promoted.

Whole held families are excluded from the two fold position fits, calibration and width selection. Graph construction, initial satellite labels, the preceding accepted mask, proposal nomination and cached measurement scales remain fixed full-data inputs. This is conditional validation of incremental recovery, not an end-to-end blind identity/acquisition experiment. In particular, the whole-family test cannot prove the original graph joins or candidate catalogue are correct.

All cases use the existing 25×25 km search box centered at 37.906, −122.545. The reporting-only coordinate is {SITE[0]}, {SITE[1]}; errors use the same 6371 km spherical distance as prior reports. Both `c=0` and fitted-`c` are reported with matched observations, candidate sets, priors and optimization budgets. No post-observation TLE or new RF collection is used. Three isolated workers ran with a 360-second per-case cap. Execution statuses: { {s:sum(r['status']==s for r in execution) for s in sorted({r['status'] for r in execution})} }. Failures/timeouts retain the preceding qualified position and cannot silently confirm a family.

Unit tests cover removal of a family across repeated curved appearances and predictive entries, causal-prior restoration without mutating the original data, distinct-family votes, paired-arm agreement, invalid-fold exclusion and aggregate disagreement. Real-data checks assert zero overlap between held and training IDs and replay fitted objectives to 1e-5 before held prediction.

Source: `tools/provisional_family_recovery.py` and `tools/report_provisional_family_recovery.py`. Original input study: `{source}`. New outputs: `{study}`.

```bash
export PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
.venv/bin/python tools/provisional_family_recovery.py freeze --root /path/to/corpus --study /path/to/combined-reentry --output /new/study
.venv/bin/python tools/provisional_family_recovery.py case --root /path/to/corpus --study /path/to/combined-reentry --case DS24-0089 --output /new/study/DS24-0089
.venv/bin/python tools/report_provisional_family_recovery.py --study /path/to/sealed/study --output /new/report
```

See [summary and decisions](summary.json), [per-scan metrics](per_scan.csv), [provenance](provenance.json), and [full compressed experiment receipts](receipts.json.gz). Hash strings in receipts are losslessly interned: replace `{{"$sha256": i}}` with `sha256_strings[i]`. Previous analyses: [warning signals](../2026_10_29_reentry_warning_signals/README.md) and [unguarded recovery](../2026_10_29_combined_family_reentry/README.md).
'''
    (out/'README.md').write_text(text)
    files=[p for p in sorted(study.rglob('*.json')) if out not in p.parents and not any(s.startswith('publication') for s in p.relative_to(study).parts)]
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
        with gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as gz:gz.write(json.dumps(dict(sha256_strings=strings,records=records),separators=(',',':'),allow_nan=False).encode())
    write(out/'provenance.json',dict(protocol=protocol,input_sha256={str(p.relative_to(study)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        source_tools_sha256={n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest() for n in ('provisional_family_recovery.py','report_provisional_family_recovery.py')}))
    print(json.dumps(dict(accepts=accepts,statistics=stats),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
