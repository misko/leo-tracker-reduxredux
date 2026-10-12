# Clock and orbital-phase diagnostics on the frozen eight-channel cohort

## Motivation

The [completed six-scan evaluation](../relative-phase/README.md) explains
70–91% of strong GLRT evidence, but the configured Sausalito reference remains
below the best evaluated likelihood. Better frequency scores alone do not meet
the position objective. This update tests two physical interpretations of the
nuisance parameters and retains their negative results.

## Problem

A shared receiver drift can miss differences between CH1–4 and CH5–8. Also,
querying ECEF states at a shifted time changes both satellite orbital phase and
Earth rotation. An orbital-phase perturbation at a fixed reception time has a
different transformation. Neither interpretation establishes a measured clock
error. Published signal measurements distinguish frame, carrier and sample
clocks; they do not establish a constant carrier correction throughout these
five-minute captures. See [Qin et al., 2026](https://www.nature.com/articles/s44459-026-00075-6).

## Solution and result

Two optional variants now permit an explicit comparison. Defaults retain the
previous model. Band drift adds an upper-minus-lower slope per receiver, with
a 1 Hz/s Gaussian prior. Fixed-reception-frame orbital phase rotates the queried
ECEF position and velocity by the additional Earth angle, holding reception-time
Earth rotation fixed. Both have component-owned synthetic and derivative checks.

**The accuracy objective remains unmet.** Band drift improves the frequency
score at the reference, but leaves the fitted-c preferred development positions
about 1.1–1.3 km away. The orbital-phase variant improves one development score
gap and worsens the other. These are bounded probes, not certified minima.

## Method

Keep the same frozen observations, original candidate alternatives, prepared
past-only TLEs, candidate pools, two nuisance starts, priors and iteration budgets.
Both c=0 and fitted-c use each variant at every position. The baseline and each
variant evaluate the identical seven points: the reference, both previous arm
minima, and four 500 m cardinal neighbors. Each position receives three outer
iterations, 20 nuisance steps per iteration and 60 EM steps per weight solve.
The report rejects mismatched evidence, starts, priors, budgets or point sets.

The reference remains 37.84903264307456°, −122.4856541910174°, height 0 m.
This is the configured pipeline reference, not a surveyed antenna position.
The wrapped-Cauchy scale is 250 Hz, satellite penalty 30, common phase prior
3 s and individual phase prior 1 s. The receiver drift prior is 10 Hz/s and
the c prior is 2,000 Hz/GHz. No new RF collection was made.

## Frequency gain and position effects

Positive score gain means improved frequency fit at the reference. Reference
gap is the best sampled score minus the reference score. Both quantities include
the declared penalties; neither is a calibrated position confidence interval.

| Development scan | Variant | Fitted-c reference gain | Best sampled distance | Reference gap |
|---|---|---:|---:|---:|
| `bf660cb5` | Baseline | 0 | 1.25 km | 27.86 |
| `bf660cb5` | Band drift | +6.99 | 1.27 km | 26.15 |
| `bf660cb5` | Fixed reception frame | +16.73 | 1.25 km | 14.43 |
| `862e4fbd` | Baseline | 0 | 1.12 km | 11.31 |
| `862e4fbd` | Band drift | +2.00 | 1.12 km | 10.77 |
| `862e4fbd` | Fixed reception frame | −7.37 | 1.12 km | 12.30 |

![Matched frequency and position effects](physical-model-comparison.png)

The [paired comparison](paired-comparison.json) includes the matched c=0 results.
A further 15-point fixed-frame probe uses east offsets −500, 0 and 500 m and
north offsets −1,000 to 0 m at 250 m spacing. On `bf660cb5`, the union of those
points and the original seven prefers (0, −1,000 m), with fitted-c gap 16.65.
On `862e4fbd`, the union still prefers (−1,000, −500 m), gap 12.30. Its finer
grid alone prefers a 559 m point, but that score is lower than the known feasible
1.12 km point. Restricting the grid would falsely suggest improved accuracy.

## Retrospective checks on the four original validation scans

The four validation labels were already inspected in the prior report. These
new seven-point checks are **retrospective**, not fresh randomized validation,
and do not replace the completed 5 km searches or their 0/4 result.

| Scan | Fixed-frame fitted-c best sampled distance | Reference gap |
|---|---:|---:|
| `4b6c9cc2` | 0.71 km | 0.90 |
| `5bc39e5c` | 1.00 km | 29.48 |
| `84dbe119` | 1.41 km | 24.56 |
| `e557fbf8` | 1.28 km | 17.42 |

One small probe reaches the numerical 1 km / one-unit criterion. It has not
passed a full surface search, and three others fail even the small probe.
There is no basis to promote this variant as an accurate localization method.
All four original validation assignments remain in the denominator.

## Other measured diagnostics

At fixed reference fits, extra quadratic receiver terms improve fitted-c scores
by less than one unit each. A frequency-dependent drift term improves them by
0.25 and 1.08 units. Individual constant satellite biases also show little gain
for the principal supported candidates. These limited conditional profiles do
not prove that transmitter clock errors are absent; they provide little reason
to add many unconstrained clock parameters now. Height probes from −25 to 150 m
also do not explain the reported horizontal displacement. These short-budget
profiles are retained as diagnostics, not convergence certificates.

For 25 selected development candidates, compare the newest eligible element
set with the next older distinct-epoch set from the **same provider**. Both epoch
and collection precede the capture. Keep the newest set as the nominal orbit.
After empirical time alignment and removal of a constant, linear drift and
frequency timing derivative, the older-minus-newer predicted frequency has
median residual RMS 62.6 Hz and 38.1 Hz for the two scans, with maxima 337.4 Hz
and 144.7 Hz. This is forecast disagreement, **not measured error of the newest
orbit**. The alignment shifts ECEF query time and is a consistency diagnostic,
not an exact orbital-element perturbation. The residual motivates testing a
causal orbit-uncertainty model before claiming overly precise location scores.

![Past forecast curvature disagreement](past-forecast-shape-disagreement.png)

A joint-score sanity check exposed a numerical hazard: adding one retained
surface per scan makes the reference appear best among 29 common points.
Taking the envelope of previously computed compatible fits at each point instead
prefers (0, −1,000 m), with a fitted-c reference gap of 54.14 units. The first
sum discards known feasible fits. Neither sum certifies a joint minimum; the
envelope is a diagnostic using historical scalar scores, not a newly optimized
joint result. A future joint fit must preserve and re-evaluate feasible states.

## Evidence and reproduction

Each scan directory retains paired evaluations, result and protocol files,
including the c=0 arm, selected identities, activity weights and nuisance values.
Source hashes in those protocols identify execution versions; the separate
[publication hashes](publication-source-digests.json) identify the current code.
The one-off conditional profiles and past-forecast calculations retain their
numeric outputs and declared protocols; they are not packaged as a complete
standalone replay of the protected archive. Original GLRT exports and orbital
arrays remain on local bulk storage. No golden fixture was modified.

The focused likelihood, orbit, initialization, solver and report checks pass
**38 tests**, and Ruff passes for changed files. Existing defaults remain the
legacy ECEF time-shift model with no additional band drift. Example paired run:

```bash
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 python -m tools.evaluate_wrapped_fast_scan sweep \
  --bundle <frozen-scan-bundle> --initial <two-known-initial.json> \
  --candidate-pool <warm-local-pool.json> --positions-json <paired-positions.json> \
  --output <local-output> --phase --relative-phase-sigma-s 1 \
  --iterations 3 --nuisance-iterations 20 --seconds 300
```

For the band variant add `--band-drift-sigma-hz-s 1`; for the frame variant add
`--inertial-phase`. Use identical inputs, starts, points and other settings.
Regenerate this report with `python -m tools.report_wrapped_physical_diagnostics
--data-root <frozen-data-root> --output <report-directory>`.
