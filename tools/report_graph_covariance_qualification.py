"""Report sealed inference; evaluation coordinates are used only in this tool."""

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

ARMS = ('c0', 'fitted_c')
SITE = (37.849061591561885, -122.48574968092912)


def error_km(latlon):
    lat, lon = np.radians(latlon)
    ref_lat, ref_lon = np.radians(SITE)
    a = np.sin((lat-ref_lat)/2)**2 + np.cos(lat)*np.cos(ref_lat)*np.sin((lon-ref_lon)/2)**2
    return float(12742*np.arcsin(np.sqrt(np.clip(a, 0, 1))))


def statistics(rows, arm, method):
    selected = [r for r in rows if r['arm'] == arm]
    errors = np.array([r[method+'_error_km'] for r in selected])
    points = sum(r[method+'_points'] for r in selected)
    return dict(mean_km=float(errors.mean()), median_km=float(np.median(errors)),
                p90_km=float(np.percentile(errors, 90)), worst_km=float(errors.max()),
                associated_points=points, total_GLRT=sum(r['total_GLRT'] for r in selected),
                pooled_association_percent=100*points/sum(r['total_GLRT'] for r in selected))


def run(args):
    root=args.study; out=args.output; out.mkdir(parents=True,exist_ok=False)
    protocol=read(root/'protocol.json'); results=[]; rows=[]
    for case in protocol['selected']:
        source=root/case/'result.json'
        for prefix in ('single', 'single-controlled'):
            candidate=root/prefix/case/'result.json'
            if candidate.exists():source=candidate
        d=read(source);results.append(d)
        for arm in ARMS:
            row=dict(case=case,arm=arm,total_GLRT=d['total_GLRT'],support_status=d['support_status'],
                     covariance_status=d['covariance_status'],source=str(source.relative_to(root)))
            for method in ('baseline','support','covariance'):
                endpoint=d[method][arm]
                row[method+'_error_km']=error_km(endpoint['endpoint_latlon'])
                row[method+'_points']=endpoint['proposed_associated_points']
                row[method+'_RMS_hz']=endpoint['RMS_hz']
                row[method+'_score']=endpoint['negative_twice_elbo']
            row['provisional_error_km']=error_km(d['provisional'][arm]['endpoint_latlon']) if 'provisional' in d else None
            rows.append(row)
    with (out/'per_scan.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    stats={a:{m:statistics(rows,a,m) for m in ('baseline','support','covariance')} for a in ARMS}
    write(out/'summary.json',dict(statistics=stats,evaluation_site=SITE,
        distance='great-circle distance on 6371 km sphere; same metric in every arm',rows=rows))
    plt.rcParams.update({'font.size':10,'axes.grid':True,'grid.alpha':.25})
    fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for k,arm in enumerate(ARMS):
        selected=[r for r in rows if r['arm']==arm];x=np.arange(len(selected))
        for method,label,color in [('baseline','Production-equivalent baseline','#666666'),('support','Qualified support backoff','#0072b2')]:
            y=[r[method+'_error_km'] for r in selected]
            axes[k,0].plot(x,y,'o-',label=label,color=color)
            axes[k,1].step(np.sort(y),np.arange(1,len(y)+1)/len(y),where='post',label=label,color=color)
        axes[k,0].set(xticks=x,xticklabels=[r['case'][-4:] for r in selected],ylabel=arm+' error (km)',xlabel='DS24 scan')
        axes[k,1].set(xlabel='Position error (km)',ylabel='Fraction of scans',ylim=(0,1.04))
        axes[k,0].axhline(.5,ls=':',color='black',label='500 m goal')
        axes[k,0].legend(fontsize=8);axes[k,1].legend(fontsize=8)
    fig.suptitle('Frozen random 12-scan cohort: 4 improvements, 8 unchanged\nCovariance recovery accepts no additions and equals support backoff')
    fig.savefig(out/'position_errors.png',dpi=160);plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    selected=[r for r in rows if r['arm']=='fitted_c'];x=np.arange(len(selected));w=.36
    for shift,method,label,color in [(-w/2,'baseline','Baseline','#888888'),(w/2,'support','Support backoff','#0072b2')]:
        axes[0].bar(x+shift,[100*r[method+'_points']/r['total_GLRT'] for r in selected],width=w,label=label,color=color)
    axes[0].set(xticks=x,xticklabels=[r['case'][-4:] for r in selected],ylabel='% of original GLRT winners',ylim=(0,100));axes[0].legend()
    for arm,marker in [('c0','o'),('fitted_c','s')]:
        values=[r for r in rows if r['arm']==arm and r['support_status']=='accepted']
        xx=[r['support_points']-r['baseline_points'] for r in values];yy=[1000*(r['baseline_error_km']-r['support_error_km']) for r in values]
        axes[1].scatter(xx,yy,marker=marker,label=arm)
        if arm=='fitted_c':
            for r,a,b in zip(values,xx,yy):axes[1].annotate(r['case'][-4:],(a,b),xytext=(4,4),textcoords='offset points')
    axes[1].axhline(0,color='black',lw=.8);axes[1].set(xlabel='Additional associated GLRT points',ylabel='Position-error reduction (m)');axes[1].legend()
    fig.suptitle('Coverage is counted separately from position accuracy')
    fig.savefig(out/'coverage.png',dpi=160);plt.close(fig)

    families=[read(p) for p in sorted(root.glob('family-*/family.json'))];complete=[d for d in families if d['status']=='complete']
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained');xx=np.arange(len(complete))
    family_rows=[]
    for k,arm in enumerate(ARMS):
        gains=[]
        for d in complete:
            white=d['predictions']['white'][arm]['joint'];corr=d['predictions']['correlated'][arm]['joint']
            gain=white['objective']-corr['objective'];gains.append(gain)
            family_rows.append(dict(norad=d['norad'],arm=arm,points=d['held_RX1_points'],gain=gain,
                joint_pass=corr['noise']['noise_screen_pass'],per_track_pass=all(g['noise_screen_pass'] for g in corr['per_track_noise'].values()),
                calibration_qualified=d['calibration']['qualified'],
                remaining_gate_failures=[g['component'] for g in d['training_fold'][arm]['gates']['tracks']+d['training_fold'][arm]['linear_gates'] if not g['compatible']]))
        axes[0].bar(xx+(k-.5)*.36,gains,width=.36,label=arm)
    axes[0].set(xticks=xx,xticklabels=[str(d['norad']) for d in complete],ylabel='White minus correlated predictive −2 log density',xlabel='Entire satellite family withheld');axes[0].legend()
    axes[1].bar(xx,[d['held_RX1_points'] for d in complete],color='#009e73')
    axes[1].set(xticks=xx,xticklabels=[str(d['norad']) for d in complete],ylabel='Held whole-family RX1 points',xlabel='Satellite NORAD')
    fig.suptitle('Five whole-family predictions improve; all target residual screens pass\nConditional evidence: fixed identities and one remaining CH1 calibration gate failure per fold')
    fig.savefig(out/'family_holdouts.png',dpi=160);plt.close(fig);write(out/'family_summary.json',family_rows)

    failure=read(root/'failure-audit/failure.json')
    fig,axes=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for k,arm in enumerate(ARMS):
        d=failure[arm];t=np.array(d['times_s']);y=np.array(d['residual_hz']);owner=np.array(d['owner']);sigma=np.array(d['conditional_sigma_hz'])
        for j,color in [(0,'#cc79a7'),(1,'#009e73')]:
            use=owner==j;axes[k,0].errorbar(t[use],y[use],yerr=sigma[use],fmt='o',ms=3,alpha=.8,color=color,label=f'CH{j+7}, marginal ±1σ')
        axes[k,0].axhline(0,color='black',lw=1);axes[k,0].set(xlabel='Scan time (s)',ylabel=arm+' held residual (Hz)');axes[k,0].legend(fontsize=8)
        d=d['common_and_differential_mean'];means=d['mean_hz'];sig=d['sigma_hz']
        axes[k,1].errorbar([0,1],means,yerr=sig,fmt='o',capsize=5,color='#0072b2')
        axes[k,1].axhline(0,color='black',lw=1);axes[k,1].set(xticks=[0,1],xticklabels=['Common to CH7/8','Half of CH7 − CH8'],ylabel='GLS offset ±1σ (Hz)')
    fig.suptitle('Pilot failure interval: randomly withheld time blocks 96–120 s\nCH7 fails the frozen screen under chronological, reversed and marginal whitening')
    fig.savefig(out/'pilot_failure.png',dpi=160);plt.close(fig)

    # Freeze exact receipts and provenance. This includes superseded diagnostic
    # output, clearly separated by path from the controlled DS24-0097 rerun.
    files=sorted(root.rglob('*.json'));receipts={};hashes={}
    for p in files:
        if out in p.parents or p.relative_to(root).parts[0].startswith('publication'):continue
        key=str(p.relative_to(root));receipts[key]=read(p);hashes[key]=hashlib.sha256(p.read_bytes()).hexdigest()
    # Observation hashes recur in many controls. Intern them losslessly rather
    # than checking tens of megabytes of duplicated random hashes into git.
    hashes_by_index=[]; hash_index={}
    def intern(value):
        if isinstance(value,dict):return {k:intern(v) for k,v in value.items()}
        if isinstance(value,list):return [intern(v) for v in value]
        if isinstance(value,str) and value.startswith('sha256:') and len(value)==71:
            if value not in hash_index:
                hash_index[value]=len(hashes_by_index);hashes_by_index.append(value)
            return {'$sha256':hash_index[value]}
        return value
    packed=intern(receipts)
    archive=dict(format='interned-sha256-strings-v1',sha256_strings=hashes_by_index,records=packed)
    with (out/'receipts.json.gz').open('xb') as raw:
        with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0) as gz:gz.write(json.dumps(archive,separators=(',',':'),allow_nan=False).encode())
    source_names=('benchmark_graph_covariance.py','run_graph_covariance_cohort.py',
        'audit_graph_covariance_families.py','report_graph_covariance_qualification.py',
        'probe_high_channel_correlated_noise.py','correlated_curve_prediction.py')
    write(out/'provenance.json',dict(source_sha256=hashes,protocol=protocol,
        single_curve_amendment=read(root/'single-curve-amendment.json'),
        source_tools_sha256={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in source_names}))
    def metric_table():
        lines=['| Arm | Method | Median km | Mean km | P90 km | Worst km | Associated GLRT | % pooled |','|---|---|---:|---:|---:|---:|---:|---:|']
        for a in ARMS:
            for m in ('baseline','support','covariance'):
                s=stats[a][m];lines.append(f"| {a} | {m} | {s['median_km']:.3f} | {s['mean_km']:.3f} | {s['p90_km']:.3f} | {s['worst_km']:.3f} | {s['associated_points']:,} | {s['pooled_association_percent']:.2f}% |")
        return '\n'.join(lines)
    per_scan=['| Scan | Support decision | Added GLRT | c=0 before → after km | Fitted-c before → after km |','|---|---|---:|---:|---:|']
    for case in protocol['selected']:
        z=[r for r in rows if r['case']==case];a,b=z
        per_scan.append(f"| {case} | {a['support_status']} | {a['support_points']-a['baseline_points']} | {a['baseline_error_km']:.3f} → {a['support_error_km']:.3f} | {b['baseline_error_km']:.3f} → {b['support_error_km']:.3f} |")
    secondary=[]
    for d in results:
        if 'provisional' not in d:continue
        for a in ARMS:
            rr=next(r for r in rows if r['case']==d['case'] and r['arm']==a)
            secondary.append(f"| {d['case']} | {a} | {d['proposal']['norad']} | {d['proposal']['points']} | {rr['support_error_km']:.3f} → {rr['provisional_error_km']:.3f} | rejected |")
    text=f'''# CH7/CH8 qualification and support-backoff benchmark — 2026-10-29

Active orbital-support backoff recovered **359 original GLRT winners** across four of 12 randomly selected DS24 fast scans. All four affected scans improved in both `c=0` and fitted-`c` arms; the other eight were unchanged. The covariance proposal accepted no further tracks. Production is unchanged and this report does not promote a new ALGO version.

The pilot remains useful evidence for correlated receiver residuals, but its CH7 interval fails a frozen residual test. Predictive score improvement alone does not establish better localization or justify accepting a track.

## Frozen cohort and controls

- Source: `{protocol['root']}`; 24 completed DS24 fast-scan family-cavity results. Twelve selected without replacement using seed **2026102903** before examining new position errors. This is a completed-case, same-site benchmark, not all DS24 or new-location validation.
- Baseline: exact objective replay of saved production-equivalent ALGO02 + causal signed phase priors + equal-prior family comparison. This is a downstream recovery benchmark on cached acquisition/GLRT/graph results, not a new RF or full acquisition run. Each replay agrees to absolute objective tolerance 1e-5.
- Search: 25×25 km regional box centered at **37.906, −122.545**, start `[0,0]` relative to that center, five phase-refresh rounds, up to 48 optimization steps per round. Both `c` arms use matched candidate sets, observations, priors and budgets for each proposal.
- Evaluation only: `{SITE[0]}, {SITE[1]}`. Errors are great-circle distances on a 6371 km sphere. Evaluation occurs after inference is sealed. The Oct29 pilot has no new position-error claim here.
- Causal inputs only. No post-observation TLE is introduced. Prior pilot audit found identical target TLE lines in nine later archive snapshots, so those archives did not provide a genuinely newer target orbit.
- Four isolated numerical workers, five-minute cap per cohort job. No new recordings or production changes.

## Results

{metric_table()}

P90 uses the ordinary interpolated sample percentile. Pooled coverage is total distinct associated original GLRT winners divided by total original winners across scans; it is not a channel-averaged percentage. Accepted covariance policy equals support backoff because no covariance addition qualifies.

![Position error per scan and empirical distributions](position_errors.png)

{chr(10).join(per_scan)}

![Coverage and independently reported position improvement](coverage.png)

Support backoff tests the largest wholly rejected curved component whose nominal orbital-correction support is not backed by two active receiver/channel groups. It refits with orbital corrections restricted to actually supported groups. It accepts only if both arms pass the retained curved and predictive gates and preserve every previously associated point. It does not select by GPS error. DS24-0095 and DS24-0101 proposals were rejected because their proposed tracks still failed gates. The algorithm does not repeatedly search smaller proposals in this bounded experiment.

The frequency RMS and raw objective are recorded separately in `per_scan.csv`. Scores across methods use different observation sets and should **not** be read as a direct localization ranking or evidence ratio.

## High-channel applicability and frozen secondary amendment

The primary rule requires two whole rejected, overlapping CH7/CH8 curves on the same receiver, independently nominated to the same incumbent satellite family. None of the 12 scans has this pattern. Thus the primary benchmark cannot demonstrate generalized paired covariance recovery.

Before reading position errors, a separately recorded amendment allowed a single long high-channel curve: at least 20 points and 24 s, same frozen calibration and acceptance rules. Only DS24-0010, DS24-0085 and DS24-0097 had initial offers. DS24-0010 did not meet the longer span rule; the other two were tested. Results below are **rejected diagnostic proposals**, not adopted algorithm outputs.

| Scan | Arm | Proposed NORAD | Proposed points | Support → provisional error km | Decision |
|---|---|---:|---:|---:|---|
{chr(10).join(secondary)}

- DS24-0085: the independently trained covariance model qualifies, but held score is slightly worse than white noise on the primary partition (−0.053 / −0.108 improvement in `c=0` / fitted `c`), and seed 0 fails held residual screening. A different partition improves score by about 13; that does not override the failures. The diagnostic position becomes slightly worse.
- DS24-0097: the covariance model fails its training complexity penalty; held residual tests fail for every partition and both arms. The best candidate beats other tested incumbent identities by a large margin but still fits inadequately. Its diagnostic position improves, which is deliberately **not** used to waive failed gates.
- Challenger identities are all incumbent active families plus the original target nominees, using the same covariance and alias profiling. This is not an exhaustive proof against every catalogue satellite. Require a ≥10 joint-score margin in both arms, three held partitions with passing joint/per-track checks and improvement over white noise, physical offset/RMS/visibility limits, all original gates and point preservation.

An implementation audit found that the pilot position helper defaulted to active orbital support. The benchmark now explicitly retains nominal support when support backoff was not accepted. DS24-0097 was rerun under this matched control; `single-controlled/DS24-0097` is authoritative. The earlier `single/DS24-0097` diagnostic is retained for audit. DS24-0085 already used accepted active support and is unaffected.

## Whole-family covariance validation

Remove each of six noise-training satellite families from **all receivers' curved calibration and predictive likelihood**, restore strictly pre-RF causal phase forecasts, refit, relearn covariance from remaining families, and predict the withheld complete RX1 curves. Retain nominal orbital prior uncertainty for the withheld satellite; do not falsely treat its calibration as exact. Target families 57701 and 58101 never train these noise models.

Five folds have eligible whole curves (376 held points total); NORAD 69970 has no eligible complete RX1 curve. Correlated prediction improves whole-family predictive −2 log density for every testable fold in both arms, by **5.7–27.7** units. Joint and individual held-curve noise screens pass throughout.

![Whole-family holdouts](family_holdouts.png)

These are conditional predictive checks: identities, aliases, graph and incumbent likelihood powers remain fixed. Each deletion refit retains one failing existing CH1 T002 gate after restoring nominal support and causal phase means; these folds are **not** valid end-to-end localization candidates. This limits the evidence but does not conceal it. See `family_summary.json` for every fold, gate failure and gain.

## Remaining pilot CH7 failure

The randomly withheld blocks at 96–120 s still fail CH7's mean screen. The failure survives chronological Cholesky whitening, reversed factorization and per-channel marginal whitening. It is not explained solely by arbitrary channel ordering.

The fitted-`c` physical GLS decomposition finds a common offset of **−102.7 ± 41.1 Hz** (−2.50σ), and a half-channel-difference of **−24.6 ± 16.2 Hz** (−1.52σ). CH7 alone has GLS mean −132.1 ± 44.7 Hz (−2.95σ). Joint conditional chi-square upper-tail probability is 0.532. These correlated samples show moderate local mean structure without an unusually large overall quadratic residual.

![Held pilot residuals and physical GLS means](pilot_failure.png)

The existing innovation-mean test and physical GLS mean test ask different questions. GLS transforms the mean/trend design along with the data; simply testing a constant or raw time trend on whitened innovations does not do that. This is a plausible direction for improving test interpretation, **not** a reason to replace the frozen gate after observing a near-threshold failure. No such gate relaxation was applied here.

## Recommendation and next bounded iteration

1. Keep covariance recovery experimental. Independently supported temporal correlation is plausible, but the current acceptance rule does not generalize to extra accepted curves in this cohort.
2. Qualify support backoff on the remaining completed DS24 cases and then an independent time cohort, with the same paired `c` controls and explicit tail-regression checks. Four improvements with zero observed regressions is promising but too small and too same-site to justify a new ALGO release.
3. Predeclare physical GLS mean/slope/curvature tests, calibrate their false-positive behavior with synthetic correlated residuals, and evaluate them on whole-family deletions. Do not tune them to make CH7 pass.
4. Keep identity ambiguity separate from residual-model inadequacy. DS24-0097 demonstrates that a strong relative identity score is insufficient for a valid absolute fit. For that case, inspect full-catalogue competitors and track joins before adding nuisance flexibility.

The worst error remains 2.205 km and the 500 m target is not achieved. More associated points helped four scans, but this experiment does not establish that coverage alone solves the remaining position bias.

## Reproduction and artifacts

Tools: `tools/benchmark_graph_covariance.py`, `tools/run_graph_covariance_cohort.py`, `tools/audit_graph_covariance_families.py`, `tools/report_graph_covariance_qualification.py`, with the existing correlated-noise helpers. Use `PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` and the project virtual environment.

```bash
python tools/benchmark_graph_covariance.py freeze --root /srv/bulk/leo/research/ds25-20261024 --output STUDY
python tools/run_graph_covariance_cohort.py --study STUDY
python tools/benchmark_graph_covariance.py case --root /srv/bulk/leo/research/ds25-20261024 --case DS24-0097 --parent STUDY/DS24-0097 --output STUDY/single-controlled/DS24-0097 --allow-single
python tools/audit_graph_covariance_families.py family --run PILOT/run --ch1 PILOT/support-backoff-final --source-root SOURCE --parent PILOT/correlated-noise-v3 --output STUDY/family-66816 --norad 66816
python tools/audit_graph_covariance_families.py failure --run PILOT/run --ch1 PILOT/support-backoff-final --source-root SOURCE --parent PILOT/correlated-noise-v3 --output STUDY/failure-audit
python tools/report_graph_covariance_qualification.py --study STUDY --output REPORT
```

`PILOT=/srv/bulk/leo/research/fast8-013224-rerun-20261029`; use the source-root recorded in pilot launch receipts. Repeat family command for 57714, 59418, 63790, 69970 and 100628. The cohort already stores every terminal result; completed outputs are never overwritten.

- `per_scan.csv`: both arms, every scan, point counts, frequency fit, score, policy error and diagnostic error.
- `summary.json`, `family_summary.json`: machine-readable summaries.
- `receipts.json.gz`: losslessly packed JSON study records, including split assignments, validation failures, calibration grids, candidate challenges, original and controlled diagnostics, and fit histories. Paths distinguish authoritative reruns. Decode each one-key `{{"$sha256": i}}` object in `records` by replacing it with `sha256_strings[i]`; all other values are literal. Interning repeated observation hashes keeps the archive small.
- `provenance.json`: source receipt hashes and frozen protocol/amendment.
- Tests: 21 passed across `test_graph_covariance_qualification.py`, `test_correlated_curve_prediction.py`, and `test_shared_high_channel_basis.py`. No production service or scientific golden fixture changed.
'''
    (out/'README.md').write_text(text)
    print(json.dumps(stats,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args())
