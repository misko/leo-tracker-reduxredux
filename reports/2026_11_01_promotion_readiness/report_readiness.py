"""Render sealed fresh outcomes separately from retrospective guard evidence."""
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path(__file__).resolve().parent


def read(p):return json.loads(Path(p).read_text())
def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+
                     ['| '+' | '.join(map(str,r))+' |' for r in rows])


def main():
    protocol=read(OUT/'candidate/protocol.json');roster=read(OUT/'fresh/roster.json')['rows']
    rows=[];decisions=[]
    for item in roster:
        case=item['case'];result=read(OUT/'candidate'/case/'result.json')
        z=read(OUT/'fresh/inputs'/(case+'.json'));total=len(read(Path(z['native_path'])/'observations.json'))
        for arm in ('c0','fitted_c'):
            b=result['baseline'][arm];r=result['final'][arm]
            assert r['associated']==b['associated']
            if result['selected'] is None:assert r==b
            rows.append(dict(case=case,recording_id=item['recording_id'],arm=arm,status=result['execution_status'],
                 selected=result['selected'],baseline_m=b['error_m'],candidate_m=r['error_m'],delta_m=r['error_m']-b['error_m'],
                 associated=r['associated'],total_glrt=total,associated_pct=100*r['associated']/total,
                 baseline_objective=b['objective'],candidate_objective=r['objective'],seconds=result['supervisor_seconds']))
        decisions.append(dict(case=case,status=result['execution_status'],selected=result['selected'],
             targets=result.get('targets',[]),guards=result.get('guards',{}),review=result.get('review',[]),
             candidate_records=[dict(name=r['name'],accepted=r['accepted'],gains=r.get('gains',{})) for r in result.get('records',[])],
             failure=result.get('reason'),seconds=result['supervisor_seconds']))
    with (OUT/'fresh_positions.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    summary=[]
    for arm in ('c0','fitted_c'):
        use=[r for r in rows if r['arm']==arm]
        for method,key in [('ALGO06','baseline_m'),('guarded_candidate','candidate_m')]:
            errors=np.array([r[key] for r in use])
            summary.append(dict(arm=arm,method=method,n=len(use),mean_m=float(errors.mean()),median_m=float(np.median(errors)),
              p90_m=float(np.quantile(errors,.9)),max_m=float(errors.max()),within500=int((errors<500).sum()),
              associated_pct=100*sum(r['associated'] for r in use)/sum(r['total_glrt'] for r in use)))
    (OUT/'fresh_summary.json').write_text(json.dumps(dict(summary=summary,decisions=decisions,protocol_sha256=__import__('hashlib').sha256((OUT/'candidate/protocol.json').read_bytes()).hexdigest()),indent=2)+'\n')
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for ax,arm in zip(axes,('c0','fitted_c')):
        use=[r for r in rows if r['arm']==arm];x=np.arange(len(use))
        ax.bar(x-.18,[r['baseline_m']/1000 for r in use],width=.36,label='ALGO06',color='#555555')
        ax.bar(x+.18,[r['candidate_m']/1000 for r in use],width=.36,label='Guarded candidate',color='#276bb0')
        ax.set(xticks=x,xticklabels=[r['case'][-4:] for r in use],ylabel='Position error (km)',xlabel='Fresh scan',title=arm)
        ax.axhline(.5,color='#999999',linestyle=':',label='500 m');ax.grid(axis='y',alpha=.2)
    axes[0].legend(fontsize=8);fig.suptitle('Five fresh fast recordings: frozen causal candidate vs published ALGO06')
    fig.savefig(OUT/'fresh_position_errors.png',dpi=170);plt.close(fig)
    population=list(csv.DictReader((OUT/'population_summary.csv').open()))
    poptable=table(['Dataset','Method','N','Mean c=0 / fitted-c km','Fitted-c median / P95 km','Improved / regressed >25m'],[
      [ds,m,next(r['n'] for r in population if r['dataset']==ds and r['method']==m),
       ' / '.join(f"{float(next(r['mean_m'] for r in population if r['dataset']==ds and r['method']==m and r['arm']==a))/1000:.3f}" for a in ('c0','fitted_c')),
       ' / '.join(f"{float(next(r[k] for r in population if r['dataset']==ds and r['method']==m and r['arm']=='fitted_c'))/1000:.3f}" for k in ('median_m','p95_m')),
       ' / '.join(next(r[k] for r in population if r['dataset']==ds and r['method']==m and r['arm']=='fitted_c') for k in ('improved25','regressed25'))]
      for ds in ('DS26','DS27','DS28') for m in ('ALGO06','combined','guarded_candidate')])
    fresh=table(['Case','Recording UTC','c=0 before → after km','Fitted-c before → after km','GLRT associated','Search status'],[
      [r['case'],r['recording_id'].split('-')[2]+' '+r['recording_id'].split('-')[3],
       ' → '.join(f"{next(q[k] for q in rows if q['case']==r['case'] and q['arm']=='c0')/1000:.3f}" for k in ('baseline_m','candidate_m')),
       f"{r['baseline_m']/1000:.3f} → {r['candidate_m']/1000:.3f}",f"{r['associated_pct']:.2f}%",r['status']]
      for r in rows if r['arm']=='fitted_c'])
    means=table(['Arm','Method','N','Mean km','Median km','Worst km','Below500m'],[
      [r['arm'],r['method'],r['n'],f"{r['mean_m']/1000:.3f}",f"{r['median_m']/1000:.3f}",f"{r['max_m']/1000:.3f}",r['within500']] for r in summary])
    completed=sum(d['status']=='complete' for d in decisions);changed=sum(d['selected'] is not None for d in decisions)
    text=f'''# Causal reassociation: promotion-readiness investigation

2026-11-01. Follow-up to the [175-outcome population study](../2026_11_01_reconsideration_population/README.md). **Production remains ALGO06.** This study implements and tests a bounded research candidate; it does not install a production worker, change a persisted contract, or mint a new ALGO version.

## Decision

Move forward with the guarded candidate for shadow qualification. The guard retains three large development repairs, withholds the model-ambiguous DS26-0044 replacement, and does not publish standalone prior changes. The existing-cohort analysis is a retrospective decision-layer audit over saved fits, not an independent rerun of the new implementation on all 175 scans. The five fresh fast scans were run through the frozen new implementation: **{completed}/5 completed their searches; {changed}/5 changed their published endpoint**. Every other outcome retains its exact baseline, with incomplete searches distinguished from completed rejections.

The remaining prerequisites for a production default are an isolated production adapter/release with exact replay parity and shadow operation, plus more independent evidence for the changed cases and remaining model sensitivity. Small same-site validation with few or no accepted corrections cannot establish a population tail guarantee. Neither the current candidate nor this study achieves 500 m typical accuracy.

## What the three investigations found

1. **Association validation:** receiver-shared offsets and unique guarded time groups support 0034, 0066 and 0251 over every tested finalist in both c arms. Scan 0044 loses to 58786 in held prediction, although 58786 fails full joint curvature gates. NORAD 63186 is a qualified bounded full-model hypothesis, not a uniquely established identity. Scan 0034 has a small worst-fold margin and gate/position sensitivity; 0066 has no target RX2 transfer evidence. [Full evidence and figures](validation/report.md).
2. **Two-family replacements:** neither 0203 nor 0070 improves under the unchanged acceptance checks. Scan 0070's aggregate joint predictive gain hides one family's losses in all five folds; the pair subsequently fails physical/owner checks. Scan 0203's nominees already own other tracks, making shared-identity merging a separate unresolved problem. A pooled frozen-alias merge fails; this does not exhaust proper joint alias/phase discovery. [Full evidence and figures](joint/report.md).
3. **Prior regression:** the standalone 64938 predictive mixture, whose phase width expands from 1 to 15 s, explains most of 0058's regression. Phase-width-only changes in the calibration families are nearly null; physical radial tightening helps slightly. Relaxing 64938's prior reduces its normalized RF penalty and position-dependent pull, worsening error despite improving fit. This does not prove the old 1 s fallback physically correct or justify a scan-specific cap. [Full ablation and figures](prior/report.md).

![Finalist predictive competition](validation/figures/predictive_competitors.png)

## Retrospective population audit

{poptable}

The guarded candidate keeps 0034 (4.498→0.374 km), 0066 (2.370→1.218 km), and 0251 (6.561→1.162 km), fitted-c. The observed absence of regressions is development evidence because the guard was designed after reviewing the earlier population results. Both arms preserve every native owner count. Coverage remains 71.256% for DS26, 78.252% for DS27, and 74.969% for DS28. The 175 usable outcomes retain the earlier explicit compute fallback; 15 upstream unavailable acquisitions remain in the parent 190-acquisition accounting.

The guard cannot repair the two worst failures, whose fitted-c errors remain 6.858 and 6.716 km. Its smaller mean gain than the broad combined method is the cost of withholding ambiguous/prior-only outcomes. Missing fits, insufficient unique partitions, and failed rivals are explicitly distinguished; no GPS error selects a satellite or overrides a decision.

![Retrospective CDF](population_cdf.png)

## Fresh fast-scan validation

The cohort contains all five whole fast acquisitions after the DS28 revision 2 cutoff found in the two canonical live fast-recording roots at the frozen inventory time. Raw-content duplicates are deduplicated, and all five have completed public ALGO06 baselines. This is a bounded live-root cohort, not a new DS-number or exhaustive all-storage census. The user confirmed the same evaluation site; it is used only for endpoint error reporting. No new RF collection or IQ reprocessing was initiated.

{fresh}

{means}

All five searches completed normally. Eight triggered families produced nine whole-family proposals. Only FRSH-0003's 48289→63926 passed the inherited predictive screen; its receiver-shared minimum competitor margin was −19.947, so the new guard withheld it. No proposal reached history completion or joint control/candidate fitting. These fresh scans validate nomination, screening and exact fallback behavior, **not successful replacement end-to-end or an accuracy improvement**. Median supervisor latency was 76.61 s; the maximum was 95.29 s, below the 1200 s cap. The [execution audit](execution-audit.json) verifies all 1971 source and 12339 input hashes after completion.

![Fresh paired errors](fresh_position_errors.png)

Inputs are private verified copies exported through the read-only ALGO05 port and the public ALGO06 terminal. None of the five has an ALGO06 additive recovery. Preflight reproduces all five published fitted-c positions with exactly 0° difference, both full owner maps, and normalized objectives. It does not substitute an earlier pipeline result. [Preflight](candidate/preflight.json), [compact fresh inventory and raw archive hash](fresh-inventory-compact.json), [fresh outcomes](fresh_summary.json), [per-scan metrics](fresh_positions.csv).

## Frozen guarded algorithm

The [runner](run_candidate.py) consumes the exact ALGO06 state and complete causal catalogue. It uses the prior RF-influence top-two-family trigger, at least 30 native points and two tracks, with at most two whole-family nominees each. It preserves original observation weights, aliases/graph evidence, inherited predictive gates, shared hardware and physical orbit priors, and the 25×25 km box centered at 37.906, −122.545. No recency penalty or later TLE enters inference.

Before expensive fitting, every proposed replacement must beat all common finalists, including the incumbent, on every distinct held-group partition in both c arms. New checks use up to 10 unique randomized 5 s time groups with 5 s guards, seed 20261111, requiring at least 5 valid distinct held sets. Offsets are shared per receiver with 300 Hz sigma, one shared rate uses 0.5 Hz/s sigma, phase sigma is 5 s on ±30 s, and noise is 150 Hz. The minimum normalized predictive margin must be strictly positive. This is an ordering guard, not a calibrated probability; overlapping training sets and full-data nomination prevent an independent-discovery interpretation.

Only admitted identity replacements cause causal history completion and full physical refits. Both arms, candidate and incumbent control, receive the same published fitted-c and family-omitted fitted-c starts, 15 phase rounds and 40 position iterations. Require original residual and exact-orbit gates, successful optimization, phase closure ≤0.01 s, interior mixture phase mass, matched native fit IDs, no lost owners, and no reassignment outside the target family. Destination identities already owning baseline points are excluded; merging remains a separate research problem. RF gain must beat both the matched-prior continuation and conservative published bounds, including the inherited shortlist penalty. At most one replacement is adopted. Prior-only changes, continuation-only changes and partial-track partitions cannot publish.

[Propagation eligibility](propagation_audit.md) explicitly separates uniform all-grid SGP4 model-invalid elements from incomplete propagation. The six historical failure instances are code 1 on all 381 knots; this is not a physical-decay diagnosis. Such elements lie outside the successfully propagatable model universe. Partial, mixed, unknown, or nonfinite-without-error failures block the run. All five fresh catalogues have zero failures. Candidate competition remains conditional on the bounded shortlist; it is not exhaustive exact fitting of every catalogue element.

Each scan runs in a separate supervised process with a 1200 s hard cap and exact ALGO06 fallback. Any incomplete candidate/control fit, worker failure or unmatched propagation failure prevents a partial winner from publishing. No renewed budget is silently granted after an incomplete attempt. Frozen inputs cover the complete exported tree, actual previous-TLE paths/receipts, numerical source files and runtime versions. Root boundaries prevent writes to sealed evidence or production. [Frozen candidate protocol](candidate/protocol.json), [policy](policy.py), [tests](candidate-tests.txt).

## Next promotion gates

1. Port this frozen candidate behind a versioned read-only ALGO06 export and isolated result namespace; keep production contracts immutable and verify exact scientific parity on both arms.
2. Exercise a successful replacement canary through the production adapter, then shadow it on future fast recordings with an explicit budget/fallback, retaining every unavailable or failed case. Check false replacement behavior as well as error and runtime; the five fresh scans alone are insufficient because no replacements activated.
3. Keep the unresolved pair/merge work outside this candidate. For the next joint test, require support for each affected family under joint calibration before allowing aggregate gains to select a pair, and jointly nominate aliases/phases for existing-family merges.
4. Review broad error and tail metrics before a new ALGO version/default. The 500 m objective needs improvements to typical scan information, not only a few outlier replacements.

All source, numerical receipts, figures and compact tables are local research outputs. The publication manifest distinguishes versioned artifacts from large local-only export/array archives and records their hashes. Source provenance and passed tests are recorded in each branch's manifest. No production files, golden fixtures, QNAP paths, RF settings or published observations were changed.
'''
    (OUT/'README.md').write_text(text)
    print('Wrote report;',completed,'complete;',changed,'fresh changed')


if __name__=='__main__':main()
