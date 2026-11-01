"""Generate the numerical tables and figure index after inference is sealed."""
import csv
from pathlib import Path
import numpy as np
import evaluate as e
LABELS={'ALGO06':'ALGO06','history_only':'History only','reassociation_only':'Reassociation only','combined':'Combined'}


def md_table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+
                     ['| '+' | '.join(map(str,r))+' |' for r in rows])


def main():
    summary=e.read(e.OUT/'summary.json');manifest=e.read(e.OUT/'manifest.json')
    rows=list(csv.DictReader((e.OUT/'positions.csv').open()));metrics=summary['metrics']
    outcome=[]
    for dataset in ('DS26','DS27','DS28'):
        for method in e.METHODS:
            c=next(r for r in metrics if r['dataset']==dataset and r['arm']=='c0' and r['method']==method)
            f=next(r for r in metrics if r['dataset']==dataset and r['arm']=='fitted_c' and r['method']==method)
            outcome.append([dataset,LABELS[method],f['n'],f"{c['mean_m']/1000:.3f} / {f['mean_m']/1000:.3f}",
                f"{f['median_m']/1000:.3f}",f"{f['p90_m']/1000:.3f}",f"{f['max_m']/1000:.3f}",f['changed'],
                f"{f['improved25']} / {f['regressed25']}",f"{f['associated_pct']:.3f}%"])
    tables=md_table(['Dataset','Method','N','Mean km c=0 / fitted c','Median km fitted c','P90 km fitted c','Worst km fitted c','Changed','Better / worse >25m','GLRT associated'],outcome)
    changed=[]
    for r in rows:
        if r['arm']!='fitted_c' or r['changed']!='True':continue
        c=next(x for x in rows if x['case']==r['case'] and x['method']==r['method'] and x['arm']=='c0')
        changed.append([r['case'],LABELS[r['method']],r['selected'],
                        f"{float(r['baseline_m'])/1000:.3f} → {float(r['error_m'])/1000:.3f}",
                        f"{float(c['baseline_m'])/1000:.3f} → {float(c['error_m'])/1000:.3f}",
                        'Previously tested' if r['prior_prototype_exposure']=='True' else 'Additional scan'])
    changes=md_table(['Scan','Method','Accepted correction','Fitted-c error km','c=0 error km','Exposure'],changed)
    funnel=md_table(['Dataset','Triggered scans','Family screens','Whole-family proposals','Predictive pass','Reassociation accepted','Combined identity changes','History-only accepted'],[
        [r[k] for k in ('dataset','triggered_scans','screened_families','whole_family_proposals','predictive_pass','reassociation_only_accepted','combined_identity_changes','history_only_accepted')] for r in summary['funnel']])
    new=[]
    for m in metrics:
        if m['dataset']=='new_to_rule' and m['arm']=='fitted_c':
            new.append([LABELS[m['method']],m['n'],f"{m['mean_m']/1000:.3f}",m['changed'],m['improved25'],m['regressed25'],
                f"{m['mean_delta_m']:+.1f}",f"[{m['bootstrap_mean_delta_low_m']:+.1f}, {m['bootstrap_mean_delta_high_m']:+.1f}]"])
    newtable=md_table(['Method','N','Mean km','Changed','Better >25m','Worse >25m','Mean change m','Descriptive bootstrap interval m'],new)
    attempts=summary['attempt_count'];completed=summary['complete_attempts'];missing=sum(r['status']!='complete' for r in summary['availability'])
    durations=[r['seconds'] for r in summary['availability'] if r['status']=='complete']
    fallbacks=[r['case'] for r in summary['availability'] if r['status']=='compute_fallback']
    wrapper_completed=[r['case'] for r in e.read(e.OUT/'compute_fallbacks.json').get('completed_before_wrapper_timeout',[])]
    hist=summary['history'];filled=sum(r['available']>0 for r in hist);requested=sum(r['requested'] for r in hist)
    diagnostics=e.read(e.OUT/'diagnostic_summary.json');transfer=diagnostics['transfer'];sensitivity=diagnostics['sensitivity']
    pred=md_table(['Scan','Method','Arm','Held RX','RMS before → after Hz','Predictive score gain','Phase closed'],[
        [r['case'],LABELS[r['method']],r['arm'],r['receiver'],f"{r['before_rms_hz']:.1f} → {r['after_rms_hz']:.1f}",
         f"{r['predictive_gain']:+.2f}",r['both_phase_closed']] for r in transfer])
    sens=md_table(['Scan','Variant','Diagnostic','Arm','Error km','Endpoint shift km','Qualified / margin passed'],[
        [r['case'],LABELS[r['variant']],r['method'],r['arm'],f"{r['error_m']/1000:.3f}" if r.get('error_m') is not None else 'Incomplete',
         f"{r['displacement_km']:.3f}" if r.get('displacement_km') is not None else '—',f"{r['qualified']} / {r.get('margin_pass','—')}"] for r in sensitivity])
    figures=[]
    for p in sorted(e.OUT.glob('DS*-curves.png')):figures.append(f"### {p.stem}\n\n![Native GLRT, adjusted orbits and residuals]({p.name})")
    recommendation=(e.OUT/'recommendation.md').read_text() if (e.OUT/'recommendation.md').exists() else 'Production remains ALGO06. Review the paired regressions and independent predictive checks before any promotion.'
    text=f'''# Causal reconsideration across DS26, DS27 and DS28

2026-11-01. Frozen follow-up to the [causal-history and reconsideration prototype](../2026_11_01_ds26_reconsideration/README.md). Offline research; production remains ALGO06.

{recommendation}

## Cohort results

{tables}

The evaluation includes every usable fast-scan baseline in the frozen DS26/DS27 inventories: 148 DS26 and 13 DS27 scans. DS28 revision 2 supplies 14 separate validation scans. Fifteen pre-existing unavailable scans remain in [availability.csv](availability.csv): 11 DS26, two DS27 and two DS28. They are not assigned zero error or zero GLRT coverage. The dataset rosters contain 190 acquisitions in total; the paired numerical comparison covers 175. DS28 was excluded from developing this candidate, but had already been studied for ALGO06; it is not a wholly untouched dataset.

There are **{len(fallbacks)} bounded-computation fallbacks**: {', '.join(fallbacks) if fallbacks else 'none'}. Their exact ALGO06 outcomes remain in every method's distribution. An incomplete search is explicitly marked `compute_fallback`, not counted as evidence against a replacement or relabeled as a successfully completed search. Any partially evaluated hypothesis remains diagnostic. The fixed process cap is 1,800 seconds per scan.

Completed atomic inference results saved before a wrapper shutdown timeout are accounted separately: {', '.join(wrapper_completed) if wrapper_completed else 'none'}. Those completed results are audited and retained; an operating-process timeout is not automatically an incomplete scientific result. [Execution accounting](compute_fallbacks.json) preserves both categories.

![Paired error CDFs](error_cdf.png)

All GLRT percentages use unique native observation IDs and the full native GLRT denominator. They are unchanged by these variants: this experiment repairs identity and uncertainty on existing evidence, rather than recovering additional points. No curve is split, truncated, given a free independent slope, or dropped to improve position.

## Every accepted change

{changes}

![Every changed scan, both c arms](changed_scans.png)

These are decisions from a frozen RF-only rule. No satellite, prior scale, starting point or acceptance setting is selected using position error. The shared candidate set and two starts are matched between c=0 and fitted-c arms.

![RF score versus position accuracy](score_vs_accuracy.png)

RF score and position accuracy are separate outcomes. A better normalized fit can still move the estimate away from the evaluation site. [positions.csv](positions.csv) retains both objectives, RMS, errors, coverage and paired changes for every method and scan.

## What generalizes beyond the earlier prototype

The four development outliers and eight earlier randomized pilot scans are marked as previously exposed. Removing all twelve leaves the following DS26/DS27 results:

{newtable}

Intervals use 5,000 paired scan resamples with seed 20261104 and summarize the mean error change. They are descriptive: scans share a site, hardware and sometimes nearby orbital conditions; these are not independence-calibrated noninferiority bounds. Zero change on a finite validation cohort does not establish a population tail guarantee.

## Four controlled variants

1. **ALGO06:** exact frozen 72-hour / ±30-second recovery outputs, with no recency penalty.
2. **Complete history only:** retain identities and native evidence; fill absent or invalid earlier causal history for active families, then apply the existing phase and physical-mode uncertainty machinery. Preserve valid incumbent history. Change the output only if both c arms qualify and improve normalized RF score against the original-prior matched continuation and published endpoint. If no history is missing, return ALGO06 exactly.
3. **Reassociation only:** RF-triggered whole-family catalogue search with existing history/fallback priors.
4. **Combined:** same search and candidate universe, with complete causal history for current and proposed identities. An accepted history-only correction is retained when no replacement qualifies. No greedy sequence of replacements is performed.

The primary validation candidate was prespecified as **combined**. All four cells were evaluated on DS28 under the same frozen rules; DS28 results did not alter any setting. DS28-0002 was used for a baseline-replay integration test before launching the batch, not for fitting or tuning a replacement. Within a scan, a replacement can change at most one family. Partial-track partitions from earlier exploration remain diagnostic-only and are not eligible here.

### Exact baseline restoration

The original research inputs describe the state before ALGO06's extra recovery. We explicitly restore every accepted 72-hour/30-second predictive family, its native ownership, phase reference and saved endpoint before this study. We require full likelihood agreement within 1e-4. Conditional attachments for both shared-family and gap-fragment recoveries are retained. The tests include DS28-0002, where omitting this step would incorrectly lose 28 accepted points. No nominally ALGO06 row silently uses an earlier algorithm's ownership.

### Causal history

Both nominal element epoch and archive collection precede the scan cutoff. Discovery uses the frozen full 72-hour causal regional catalogue. Missing-history completion takes the newest genuinely earlier element available in the prior 72-hour archive collection window, separated from the nominal epoch by at least one second. Sub-second formatting duplicates do not count as history. No future TLE is used for discovery, priors, fitting, selection or these validation diagnostics. The nominal TLE is not selected by best fit.

History-only completion found missing or invalid history in **{filled} scans**, with **{requested} requested satellite histories** across the 175 scans; available and missing counts are in [history_inventory.csv](history_inventory.csv). Additional exports for proposed replacement identities are recorded in the manifest. Prior uncertainty can legitimately become larger or smaller; filling history is not a blanket tightening of nuisance freedom.

### Trigger, search and acceptance

{funnel}

The funnel counts whole-family proposals before and after conditional predictive checks. Partition diagnostics cannot be accepted. A scan can nominate two target families; both c arms must pass the predictive screen before final fitting. Full counts and incomplete screen statuses are retained in [search_funnel.csv](search_funnel.csv).

The trigger is the preceding prototype's summed local omission displacement across both c arms, requiring at least 30 fitted points and two curved tracks. Search at most two families above 0.5 km. Nominate from the complete eligible causal bank on the two longest target curves, then compare at most two whole-family replacement hypotheses. Use the same reduced phase/offset/shared-rate screening model and five randomized synchronized five-second block holdouts with five-second guards. Require positive mean predictive gain and at least four winning folds in both arms.

Candidate discovery and graph/alias preprocessing use the full source. Predictive checks are therefore conditional, not independent evidence of catalogue discovery; repeated or overlapping folds are not independent trials. They do not yield calibrated satellite-identity probabilities.

Fit candidate and incumbent continuation from the same published fitted-c and family-omitted fitted-c RF endpoints, with 15 phase rounds, 40 constrained position iterations and the original 25×25 km box centered at 37.906, −122.545. Enforce existing residual gates, exact-orbit checks, optimizer success, phase closure ≤0.01 s, mixture phase interior, native owner retention and no unintended reassignment. Require positive paired RF gain beyond `2 log(shortlist size)` against the best qualified incumbent continuation; also retain the incumbent score at its published endpoint under the matched priors as a conservative bound. That extra bound is a frozen-reference score, not a newly converged incumbent solution. This matched-control requirement is stricter than comparing only with the published endpoint in the preceding small prototype. Continuation-only gains are not credited as satellite reassociation.

All satellite and hardware priors, native masks, weights and candidate nomination rules remain fixed across paired arms. The known site (37.849061591561885, −122.48574968092912) is used by the endpoint error reporter, never by nomination, optimization or acceptance.

## Predictive and sensitivity review

For every accepted replacement we fit the physical-feature Gaussian model on the remaining curved evidence and predict the target tracks on one held receiver. Both hypotheses use the same whole-family-omitted RF position. Phase is refreshed from training evidence only, with a 20-iteration/0.01-second closure check. This conditional diagnostic inherits graph/alias choices and uses 150 Hz noise; it is not an independently calibrated identity probability or a fresh geolocation estimate. Any unclosed transfer cell is marked and cannot count as supporting predictive evidence.

{pred}

![Cross-receiver conditional prediction](receiver_transfer.png)

When target evidence is confined to one receiver, cross-receiver transfer is unavailable, not a passing check. We additionally hold out entire target tracks and predict them from the remaining curved evidence. These checks retain the same conditional-discovery limitations. Full results are in [whole_track_transfer.csv](whole_track_transfer.csv).

![Whole-track conditional prediction](whole_track_transfer.png)

We separately perturb the normalized residual-gate margin by 0.01 and 0.05 and reduce the nonlinear receiver prior from 200 to 50 Hz. Each uses the same selected fitted-c starting position for both c arms, with unchanged fit budgets. These settings cannot modify the frozen output and are not selected by GPS error.

{sens}

Native orbit/residual panels below use the candidate's alias branch. Curves include fitted receiver and orbital terms; residuals are in-sample diagnostics. Numerical residual means, slopes, lag correlation and structure gates are retained in the hashed diagnostic artifacts. Earlier detailed polynomial/track-join audits are not relabeled as freshly repeated here.

{chr(10).join(figures)}

## Completion, cost and limits

There are {attempts} recorded primary candidate/control position attempts, of which {completed} completed numerically; incomplete attempts and rejected fits are distinct in [attempts.csv](attempts.csv). Cases use bounded processes with explicit failure records. Median completed whole-scan research time was {np.median(durations):.1f} seconds and maximum {max(durations):.1f} seconds, including reconstruction and search; bounded failures are listed separately. Ten evaluation workers and two validation workers initially ran with single-thread numerical libraries on shared hardware. Three additional tail-roster workers and subsequently three DS27 workers used freed capacity, with per-case locks and attempt receipts preventing duplicate fits or silently renewed budgets. Workers that encounter an active case wait for its existing outcome. These timings evaluate all four variants and are not a single-policy production or embedded benchmark.

The family-influence implementation was optimized to avoid calculating unused omission Hessians; the gradient, baseline Hessian and ordering are unchanged, and exact ranking equality was tested. Early workers used the original arithmetic. Frozen and final code hashes are both retained.

This is a downstream conditional reassociation evaluation on saved ALGO06 evidence. It does not rerun IQ extraction, acquisition, graph construction or the cold regional search. It tests neither sample-rate changes nor receiver pointing changes. It does not justify attributing remaining error to those hardware factors. Scans that fail to improve remain valid unresolved cases; the experiment does not force an association to reach a coverage target.

## Reproduction and evidence

- [Frozen protocol](protocol.json), [diagnostic protocol](diagnostic_protocol.json), [manifest and raw hashes](manifest.json).
- [Summary](summary.csv), [positions and coverage](positions.csv), [decision ledger](decisions.csv), [attempts](attempts.csv), [availability](availability.csv), [history inventory](history_inventory.csv).
- [Predictive transfer](transfer.csv), [sensitivity](sensitivity.csv), [compact per-scan receipts](receipts/).
- [Evaluation adapter](evaluate.py), [diagnostics](diagnostics.py), [renderer](render.py), [seal/audit](seal.py), [report generator](write_report.py), [tests](test_evaluate.py), [test output](tests.txt).

Use `/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python`, `PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=src:tools`, from the recorded worktree. Commands: `evaluate.py evaluation --workers 10`, `evaluate.py validation --workers 2`, `diagnostics.py CASE` for accepted changes, `render.py`, then `seal.py` and `write_report.py`. Do not rerun `freeze` over the frozen protocol. Raw predictions and complete fits remain in the manifest's local archive; compact receipts, figures and scripts are versioned.

No production component, public contract, golden fixture, QNAP file or RF collection setting was modified.
'''
    (e.OUT/'README.md').write_text(text)
    print('Wrote report with',len(changed),'changed method/scan rows')


if __name__=='__main__':main()
