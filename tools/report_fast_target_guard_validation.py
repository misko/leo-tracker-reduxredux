"""Report the sealed separate-recording guard validation; GPS is evaluation only."""
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
from report_graph_covariance_qualification import SITE, error_km

METHODS = ('baseline', 'support', 'unguarded', 'guarded')
LABELS = ('Baseline', 'Support backoff', 'Unguarded recovery', 'Target gate guard')
COLORS = ('#888888', '#0072b2', '#d55e00', '#009e73')
ARMS = ('c0', 'fitted_c')


def run(args):
    study = args.study
    protocol = read(study / 'protocol.json')
    execution = read(study / 'execution.json')
    assert sorted(r['case'] for r in execution) == sorted(protocol['cases'])
    assert all(r['status'] in ('complete', 'failed') for r in execution)
    root = Path(protocol['root'])
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    rows, decisions = [], []
    for case in protocol['cases']:
        terminal = read(study / (case + '-terminal.json'))
        if terminal['status'] != 'complete':
            decisions.append(dict(case=case, status='failed', reason=terminal['reason']))
            continue
        source = read(study / 'recovery' / case / 'result.json')
        decision = dict(case=case, status='complete', support_status=source['support_status'],
                        reentry_status=source['status'], guard_accepted=terminal['guard_accepted'],
                        proposal=source.get('proposal'), sigma_hz=source.get('selected_sigma_hz'),
                        provisional_points=len(terminal['provisional_observation_ids']))
        path = study / 'recovery' / case / 'unconstrained.json'
        if path.exists():
            pair = read(path)
            decision['target_gates'] = {a:next(g for g in pair[a]['gates']['tracks']
                if g['component'] == source['proposal']['component']) for a in ARMS}
        decisions.append(decision)
        total = len(read(root / case / 'observations.json'))
        for arm in ARMS:
            results = dict(baseline=source['baseline'][arm], support=source['support'][arm],
                           unguarded=source['policy'][arm], guarded=terminal['policy'][arm])
            row = dict(case=case, arm=arm, total_GLRT=total)
            for method, r in results.items():
                if method != 'baseline':
                    assert set(source['support'][arm]['proposed_associated_ids']) <= set(r['proposed_associated_ids'])
                row[method+'_error_km'] = error_km(r['endpoint_latlon'])
                row[method+'_points'] = r['proposed_associated_points']
                row[method+'_coverage_percent'] = 100*r['proposed_associated_points']/total
                row[method+'_RMS_hz'] = r['RMS_hz']
                row[method+'_negative_twice_elbo'] = r['negative_twice_elbo']
            rows.append(row)
    stats = {}
    for arm in ARMS:
        rr = [r for r in rows if r['arm'] == arm]
        stats[arm] = {}
        for m in METHODS:
            if not rr: continue
            errors = [r[m+'_error_km'] for r in rr]
            points = sum(r[m+'_points'] for r in rr)
            total = sum(r['total_GLRT'] for r in rr)
            stats[arm][m] = dict(scans=len(rr), points=points, total_GLRT=total,
                coverage_percent=100*points/total, mean_km=float(np.mean(errors)),
                median_km=float(np.median(errors)), worst_km=max(errors))
    write(out/'summary.json', dict(statistics=stats, rows=rows, decisions=decisions,
          execution=execution, evaluation_site=SITE))
    if rows:
        with (out/'per_scan.csv').open('x', newline='') as f:
            w=csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n'); w.writeheader(); w.writerows(rows)
        plt.rcParams.update({'font.size':10, 'axes.grid':True, 'grid.alpha':.25})
        fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
        for col, arm in enumerate(ARMS):
            rr = [r for r in rows if r['arm'] == arm]; x=np.arange(len(rr))
            for j, (m, label, color) in enumerate(zip(METHODS, LABELS, COLORS)):
                offset=(j-1.5)*.19
                axes[0,col].bar(x+offset,[r[m+'_error_km'] for r in rr],width=.18,color=color,label=label)
                axes[1,col].bar(x+offset,[r[m+'_coverage_percent'] for r in rr],width=.18,color=color,label=label)
            axes[0,col].axhline(.5,color='black',ls=':',label='500 m goal')
            axes[0,col].set(title=arm,ylabel='Position error (km)')
            axes[1,col].set(ylabel='Associated original GLRT (%)',ylim=(0,100))
            for ax in axes[:,col]: ax.set(xticks=x,xticklabels=[r['case'][-4:] for r in rr],xlabel='Separate fast scan')
            axes[0,col].legend(fontsize=8)
        fig.suptitle('Four separate recordings: frozen policy, same site\nGuard and unguarded agree where no proposal is blocked')
        fig.savefig(out/'per_scan.png',dpi=170); plt.close(fig)
        fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
        for ax,arm in zip(axes,ARMS):
            rr=[r for r in rows if r['arm']==arm]
            for j,(m,label,color) in enumerate(zip(METHODS,LABELS,COLORS)):
                values=np.sort([r[m+'_error_km'] for r in rr])
                ax.step(values,np.arange(1,len(values)+1)/len(values),where='post',color=color,
                        label=label,ls=('--' if m=='guarded' else '-'),lw=2.5-j*.3)
            ax.axvline(.5,color='black',ls=':');ax.set(title=arm,xlabel='Position error (km)',ylabel='Fraction of completed scans');ax.legend(fontsize=8)
        fig.suptitle('Separate-recording error distributions (small availability cohort)')
        fig.savefig(out/'distributions.png',dpi=170);plt.close(fig)
    metric=['| Arm | Policy | GLRT associated | % | Mean km | Median km | Worst km |',
            '|---|---|---:|---:|---:|---:|---:|']
    scans=['| Scan | Arm | Baseline error km | Support error km | Guarded error km | Baseline → guarded GLRT % |',
           '|---|---|---:|---:|---:|---:|']
    for arm in ARMS:
        for m,label in zip(METHODS,LABELS):
            if m not in stats[arm]: continue
            s=stats[arm][m];metric.append(f'| {arm} | {label} | {s["points"]:,}/{s["total_GLRT"]:,} | {s["coverage_percent"]:.2f} | {s["mean_km"]:.3f} | {s["median_km"]:.3f} | {s["worst_km"]:.3f} |')
    for r in rows:
        scans.append(f'| {r["case"]} | {r["arm"]} | {r["baseline_error_km"]:.3f} | {r["support_error_km"]:.3f} | {r["guarded_error_km"]:.3f} | {r["baseline_coverage_percent"]:.2f} → {r["guarded_coverage_percent"]:.2f} |')
    table=['| Scan | Support recovery | Family reentry | Guard accepts | Target | Prior Hz |', '|---|---|---|---|---|---:|']
    for d in decisions:
        if d['status']=='failed':table.append(f'| {d["case"]} | failed | {d["reason"]} | — | — | — |');continue
        t=d['proposal'];target=f'{t["norad"]}: {t["points"]} points, {t["span_s"]:.1f} s' if t else 'none'
        table.append(f'| {d["case"]} | {d["support_status"]} | {d["reentry_status"]} | {d["guard_accepted"]} | {target} | {d["sigma_hz"] or "—"} |')
    manifest=['| Label | Recording |', '|---|---|']+[f'| {r["dataset_label"]} | `{r["recording_id"]}` |' for r in protocol['recordings']]
    gate_table=['| Scan | Arm | Target RMS Hz | Mean z | Slope z | Maximum step z | Lag-1 ACF | Pass |',
                '|---|---|---:|---:|---:|---:|---:|---|']
    for d in decisions:
        for arm,g in d.get('target_gates',{}).items():
            gate=g['conditional_residual_gate'];v=gate['diagnostics']
            gate_table.append(f'| {d["case"]} | {arm} | {gate["rms_hz"]:.2f} | {v["mean_z"]:.3f} | {v["slope_z"]:.3f} | {v["maximum_step_z"]:.3f} | {v["lag1_acf"]:.3f} | {g["compatible"]} |')
    interpretation=[]
    for arm in ARMS:
        if not stats[arm]: continue
        b,s,g=[stats[arm][m] for m in ('baseline','support','guarded')]
        interpretation.append(f'For {arm}, the complete guarded stack adds {g["points"]-b["points"]} points over baseline '
            f'({s["points"]-b["points"]} from support backoff and {g["points"]-s["points"]} from family reentry). '
            f'Mean error changes {b["mean_km"]:.3f} → {g["mean_km"]:.3f} km; median changes '
            f'{b["median_km"]:.3f} → {g["median_km"]:.3f} km; worst changes {b["worst_km"]:.3f} → {g["worst_km"]:.3f} km.')
    rr=[r for r in rows if r['arm']=='fitted_c']
    for r in rr:
        if abs(r['guarded_error_km']-r['baseline_error_km'])<1e-10: continue
        delta=1000*(r['guarded_error_km']-r['baseline_error_km'])
        interpretation.append(f'{r["case"]}: fitted-c error {r["baseline_error_km"]:.3f} → '
            f'{r["support_error_km"]:.3f} → {r["guarded_error_km"]:.3f} km (baseline → support → guarded), '
            f'a {abs(delta):.1f} m {"improvement" if delta<0 else "regression"}; '
            f'{r["guarded_points"]-r["baseline_points"]} additional confirmed points.')
    accepted=[d for d in decisions if d.get('reentry_status')=='accepted']
    blocked=[d for d in accepted if not d['guard_accepted']]
    interpretation.append(f'{len(accepted)} family proposals qualified for the original recovery policy; '
        f'{len(blocked)} were blocked by the target guard. '
        + ('The guarded and unguarded outputs therefore coincide: this cohort shows that these recoveries survive the guard, '
           'but provides no new example testing its ability to reject a harmful proposal.' if not blocked else
           'The decision table identifies which proposals the guard blocked.'))
    interpretation.append('Recommendation: retain this as a research candidate and do not promote a new production ALGO version yet. '
        'The sample is small and same-site; one additional clean target can still increase position error. '
        'Passing residual gates is a compatibility check, not a probability of correct identity or a guarantee of useful position information. '
        'The next experiment should keep this rule frozen on additional disjoint scans and diagnose the accepted regression using independent-family prediction and old-evidence conflict, '
        'without selecting a rejection threshold using its known GPS error.')
    body=f'''# Separate fast-scan validation of the target-gate guard — 2026-10-29

The frozen guard and its preceding recovery stack were rerun on four prepared 10 MS/s fast recordings with no recording-ID overlap with the development corpus. All localization results were computed afresh from the copied GLRT/graph inputs and strictly causal orbital inputs. Evaluation coordinates were used only after every inference decision was sealed. Production remains unchanged.

## Interpretation

{chr(10).join(chr(10)+p+chr(10) for p in interpretation)}

## Matched position and coverage results

{chr(10).join(metric)}

![Per-scan errors and GLRT coverage](per_scan.png)

{chr(10).join(scans)}

![Small-cohort distributions](distributions.png)

## Decisions and scope

{chr(10).join(table)}

The restored target's **unconstrained** residual checks are below. These are the checks used by the guard, before any constrained fallback. The full profile, alias and all-old-track checks remain in the receipts. ACF is dimensionless, and z values use the existing model's uncertainty normalization.

{chr(10).join(gate_table)}

This is a four-recording, same-site availability cohort, not validation at a new location or a random sample of the full dataset. Failure statuses are reported explicitly; aggregate metrics include only completed paired cases. The full requested denominator is four scans. Frequencies, residual RMS and negative twice ELBO are in [the per-scan CSV](per_scan.csv), separate from position error. Methods have different accepted observation sets, so lower in-sample frequency RMS is not evidence of better localization.

The guard requires an already accepted full-data recovery proposal and a restored target that passes the existing **unconstrained** residual/profile/alias gates in both `c=0` and fitted-`c` arms. Existing final gates and preservation of preceding accepted observation IDs still apply. Old tracks can still use the existing constrained refinement. Blocked target IDs remain provisional and do not affect position or confirmed coverage. This tests the identical narrow rule from [the development report](../2026_10_29_provisional_family_recovery/README.md).

The recovery stack first attempts active-support backoff. It then nominates at most one largest wholly unassociated curved track with at least 20 points and 24 seconds and no active family evidence. Its original family must win the bounded full causal catalogue screen in both arms, satisfy RMS ≤450 Hz, absolute bias ≤3,000 Hz and elevation ≥0°. The target constant prior is selected between 300 and 1,000 Hz using the existing randomized 12-second block predictive selector at the preceding RF endpoint. The wider prior requires total held-density improvement above `2 log(2)` in both arms. Full recovery uses five phase-refresh rounds of up to 48 iterations, with the existing constrained fallback of five rounds of up to 20 iterations. No threshold, nominee, prior, or guard decision is selected using evaluation error.

## Reproducibility and limits

{chr(10).join(manifest)}

These four recordings were selected because their existing preparation was complete and disjoint from the development corpus; they were not selected by position error. Fresh baselines include the causal signed-phase prior and the current family-comparison stage. This is an end-to-end localization replay from existing graph/GLRT inputs, not a new IQ acquisition or a reconstruction of GLRT extraction. Original input hashes, source hashes, exact manifests and all decision receipts are retained.

Both arms use matched input observations, candidate catalogues, other priors, regional box and search budgets. Fits start at the established 25×25 km regional box centered at 37.906, −122.545. The reporting-only evaluation site is {SITE[0]}, {SITE[1]}, explicitly confirmed by the user for these recordings. Distances use the same 6371 km spherical metric as previous reports. No post-scan TLE or new RF collection is used. Four isolated workers use one BLAS thread each; per-stage caps are 360 s for initial localization, 360 s for family comparison and 240 s for recovery. All inference decisions precede this report's evaluation.

Source files: `tools/validate_fast_target_guard.py`, `tools/report_fast_target_guard_validation.py`. Tests cover paired-arm acceptance, rejection of missing or failing target gates, original-proposal acceptance, duplicate/overlapping recordings and the 10 MS/s fast-recording restriction. Runtime checks verify preparation input hashes, frozen algorithm source hashes, baseline qualification and old-point preservation.

```bash
export PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
.venv/bin/python tools/validate_fast_target_guard.py freeze --prepared /prepared/four --development /development/corpus --output /new/study
.venv/bin/python tools/validate_fast_target_guard.py run --output /new/study
.venv/bin/python tools/report_fast_target_guard_validation.py --study /new/study --output /new/report
```

See [summary](summary.json), [provenance](provenance.json), and [compressed decision receipts](receipts.json.gz). Large frozen input banks and original observations remain in the existing corpus and are referenced by digest. Receipt hash strings are losslessly interned: replace `{{"$sha256": i}}` with `sha256_strings[i]`.
'''
    (out/'README.md').write_text(body)
    excluded={'inference/'+name for name in protocol['input_sha256']}
    files=[p for p in sorted(study.rglob('*.json')) if out not in p.parents
           and str(p.relative_to(study)) not in excluded and not any(s.startswith('publication') for s in p.relative_to(study).parts)]
    strings=[];indices={}
    def intern(value):
        if isinstance(value,dict):return {k:intern(v) for k,v in value.items()}
        if isinstance(value,list):return [intern(v) for v in value]
        if isinstance(value,str) and value.startswith('sha256:') and len(value)==71:
            if value not in indices:indices[value]=len(strings);strings.append(value)
            return {'$sha256':indices[value]}
        return value
    records=intern({str(p.relative_to(study)):read(p) for p in files})
    with (out/'receipts.json.gz').open('xb') as f:
        with gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as gz:
            gz.write(json.dumps(dict(sha256_strings=strings,records=records),separators=(',',':'),allow_nan=False).encode())
    write(out/'provenance.json',dict(protocol=protocol,
        receipt_sha256={str(p.relative_to(study)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        report_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    print(json.dumps(dict(statistics=stats,decisions=[{k:v for k,v in d.items() if k!='target_gates'} for d in decisions]),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args())
